"""Verify no-control waits and notification calls without inventing kernel flags."""
import argparse
from collections import Counter
import json
from pathlib import Path

from probe_z62_capture_submit import MASTER_SHA
from record_z62_action_evidence import workspace, digest, require
from verify_z62_capture_submit_evidence import pair_preparation


def validate_no_capture(row):
    require(not row['controls_sent'] and all(r['method'] == 'GET' for r in row['http_requests']),
            'Observation sent a control')
    states = [row['initial']['capture'], row['final']['capture'], row['initial_gate']['capture_flow'],
              row['after_detach']['capture_flow'], *[h['state']['capture'] for h in row['hits']]]
    require(all(state['active_word'] == 0 for state in states), 'Capture was active in the no-control scope')
    for software in (row['software_before'], row['software_after']):
        require(not software['half_pressed'] and not software['full_pressed'] and
                software['card']['present'] and not software['card']['images'], 'Control scope created media or held a key')


def verify(session, case, output):
    session, case, output = map(workspace, (session, case, output)); hashes = {}
    def read(path):
        hashes[str(path)] = digest(path)
        return json.loads(path.read_text(encoding='utf-8'))
    master_path = session/'inputs/master.bin'; master = master_path.read_bytes()
    require(digest(master_path) == MASTER_SHA, 'Original master changed')
    controls = {}
    for name, expected in (('no-shutter-1', 3), ('ready-producers-1', 2)):
        row = read(case/name/'result.json'); validate_no_capture(row)
        require(row['completed_observation'] and row['completed_packets'] == expected and not row['window_active'] and
                row.get('detach') == 'OK' and not row.get('failure') and not row.get('cleanup_error') and
                row['sources_unchanged'] and row['functional_acceptance_eligible'] is False, 'Incomplete control: '+name)
        require(all(digest(Path(p)) == sha for p, sha in row['source_sha256'].items()), 'Observer source changed')
        binding = read(case/name/'source-binding.json')
        require(binding['bound_before_shutter_send'] and
                all(digest(Path(p)) == sha for p, sha in binding['source_sha256'].items()), 'Generated source binding differs')
        for anchor in row['live_anchors']:
            pc = int(anchor['pc'], 16)
            require(master[pc-0x10020000:pc-0x10020000+4].hex() == anchor['bytes'], 'Original live anchor differs')
        filtered = {**row, 'hits': [h for h in row['hits'] if not h['label'].startswith('ready-post-')]}
        timing = pair_preparation(filtered)
        require(not timing['unreturned_calls'] and not timing['unpaired_return_sites'], 'Unpaired no-control timing')
        waits = [pair for pair in timing['pairs'] if pair['name'] == 'input-ready-wait']
        indexed = {hit['sequence']: hit for hit in row['hits']}
        require(len(waits) == expected and all(pair['arguments'] ==
            ['0xc188808c','0x5b00000',indexed[pair['entry_sequence']]['registers']['sp'],'0xc8'] and
            pair['return_r0'] == '0x0' for pair in waits),
            'Observed wait contract differs')
        require(row['initial']['queue']['count'] == row['initial']['queue']['capacity'] == 60,
                'Initial no-control queue is not saturated')
        for hit in row['hits']:
            if hit['label'] == 'input-ready-wait-return':
                require(hit['output_at_sp'] == '0x0', 'Failed wait output differs')
        controls[name] = {'record': row, 'timings': timing, 'wait_duration_ns': [p['duration_ns'] for p in waits]}
    first = controls['no-shutter-1']['record']; observed = controls['ready-producers-1']['record']
    require(first['owner']['ProcessId'] == observed['owner']['ProcessId'] and first['profile'] == observed['profile'],
            'No-control observers used different VMs')
    driver = read(case/'ready-producers-1.driver-result.json'); profile = read(case/'ready-producers-1.profile.json')
    require(driver['driver_unchanged'] and driver['completed_observation'] and
            driver['result_sha256'] == digest(case/'ready-producers-1/result.json') and
            driver['profile_sha256'] == digest(case/'ready-producers-1.profile.json') and
            profile['driver_sha256'] == digest(Path(__file__).with_name('probe_z62_ready_producers.py')) and
            profile['base_source_sha256'] == digest(Path(__file__).with_name('probe_z62_prepare_control.py')),
            'Producer driver changed')
    posts = [hit for hit in observed['hits'] if hit['label'].startswith('ready-post-')]
    require(dict(Counter(hit['label'] for hit in posts)) == driver['post_counts'], 'Producer count differs')
    for hit in posts:
        expected = profile['producer_map'][hit['registers']['pc']]
        require(hit['registers']['r0'] == '0xc188808c' and hit['registers']['r1'] == expected['event_mask'],
                'Producer call arguments differ')
    counters = read(case/'input-counters-1/result.json')
    require(counters['completed_observation'] and counters.get('detach') == 'OK' and not counters['read_errors'] and
            counters['sources_unchanged'] and counters['owner']['ProcessId'] == first['owner']['ProcessId'] and
            counters['prior_trace_sha256'] == digest(case/'no-shutter-1/result.json'), 'Input counter observation differs')
    require(all(digest(Path(p)) == sha for p, sha in counters['source_sha256'].items()), 'Counter source changed')
    props = {key: row['value'] for key, row in counters['properties'].items()}
    require(props['functional-continuous-stats'] is True and props['continuous-frames'] > 0 and
            props['continuous-rejected'] == props['continuous-blocked'] == 0 and
            props['continuous-reason'] == 'success', 'Continuous model output is not established')
    later = read(case/'input-counters-2/result.json')
    require(later['completed_observation'] and later.get('detach') == 'OK' and not later['read_errors'] and
            later['sources_unchanged'] and later['owner']['ProcessId'] == first['owner']['ProcessId'] and
            all(digest(Path(p)) == sha for p, sha in later['source_sha256'].items()), 'Later input snapshot differs')
    later_props = {key: row['value'] for key, row in later['properties'].items()}
    require(later_props['continuous-frames'] > props['continuous-frames'] and
            later_props['continuous-bytes'] > props['continuous-bytes'] and
            later_props['continuous-rejected'] == later_props['continuous-blocked'] == 0 and
            later_props['continuous-reason'] == 'success', 'Continuous output did not advance between snapshots')
    boundary = read(case/'event-object-boundary-1.json')
    require(boundary['master_sha256'] == MASTER_SHA and
            boundary['control_sha256'] == digest(case/'no-shutter-1/result.json') and
            boundary['analyzer_sha256'] == digest(Path(__file__).with_name('analyze_z62_event_object.py')) and
            boundary['object_first_word_is_event_pattern_proven'] is False and
            boundary['kernel_event_pattern_read'] is False, 'Opaque object boundary differs')
    for block in boundary['blocks']:
        offset = int(block['start'], 16)-0x10020000
        require(master[offset:offset+len(bytes.fromhex(block['bytes']))].hex() == block['bytes'], 'Boundary bytes changed')
    masks = first['initial_words']
    routes = {3:(0x20068200,3), 4:(0x20068200,4), 96:(0x20068260,0),
              101:(0x20068260,5), 135:(0x20068280,7)}
    enabled = {str(line): bool(int(masks[hex(address)],16) & (1 << bit)) for line,(address,bit) in routes.items()}
    result = {'schema': 1, 'completed_evidence_check': True, 'verifier_sha256': digest(Path(__file__)),
        'master_sha256': MASTER_SHA, 'artifact_sha256': hashes,
        'no_shutter_timeout_before_capture_observed': True,
        'no_shutter_wait_duration_ns': controls['no-shutter-1']['wait_duration_ns'],
        'producer_window_wait_duration_ns': controls['ready-producers-1']['wait_duration_ns'],
        'input_irq_mask_bits_enabled': enabled, 'producer_call_counts': driver['post_counts'],
        'continuous_model_counters': props,
        'later_continuous_model_counters': later_props,
        'kernel_event_pattern_read': False, 'object_first_word_is_event_pattern_proven': False,
        'producer_call_return_success_proven': False, 'unobserved_producers_globally_absent_proven': False,
        'hardware_cause_complete': False, 'functional_acceptance_eligible': False,
        'factory_capture_verified': False, 'AF_verified': False, 'camera_accessed': False}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != 'artifact_sha256'}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); verify(args.session, args.case, args.output)
