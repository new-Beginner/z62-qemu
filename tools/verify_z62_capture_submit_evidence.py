"""Verify original capture rejection and bounded preparation timings, never success."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from probe_z62_capture_submit import MASTER_SHA
from record_z62_action_evidence import workspace, digest, require


def pair_preparation(record):
    pending = {}; pairs = []; outside = []
    for hit in record['hits']:
        label = hit['label']; reg = hit['registers']
        if label in ('packet-entry', 'packet-return'):
            name, entry = 'packet', label == 'packet-entry'
        else:
            require(label.endswith(('-call','-return')), 'Unknown preparation phase')
            entry = label.endswith('-call'); name = label.rsplit('-', 1)[0]
        key = (hit['packet_index'], hit['thread'], reg['sp'], name)
        if entry:
            require(key not in pending, 'Ambiguous nested timing frame')
            pending[key] = hit
        elif key not in pending:
            outside.append({'sequence': hit['sequence'], 'label': label})
        else:
            before = pending.pop(key); delta = hit['virtual_time_ns']-before['virtual_time_ns']
            require(delta >= 0, 'Original clock moved backwards')
            pairs.append({'packet_index': hit['packet_index'], 'name': name, 'duration_ns': delta,
                'entry_sequence': before['sequence'], 'return_sequence': hit['sequence'],
                'arguments': [before['registers']['r'+str(i)] for i in range(4)], 'return_r0': reg['r0']})
    return {'pairs': pairs, 'unpaired_return_sites': outside,
            'unreturned_calls': [hit['sequence'] for hit in pending.values()]}


def verify(session, case, output):
    session, case, output = map(workspace, (session, case, output))
    paths = {}
    def read(path):
        paths[str(path)] = digest(path)
        return json.loads(path.read_text(encoding='utf-8'))
    capture_path = case/'trace-2/result.json'; capture = read(capture_path)
    require(capture['completed_observation'] and not capture.get('failure') and
            capture.get('detach') == 'OK' and not capture.get('cleanup_error') and not capture.get('control_errors'),
            'Capture trace is incomplete')
    require(capture['sources_unchanged'] and capture['reader_sources_unchanged'] and capture['bound_before_shutter_send'],
            'Capture source binding is incomplete')
    require(capture['functional_acceptance_eligible'] is False and capture['guest_memory_written'] is False and
            capture['guest_registers_written'] is False, 'Diagnostic boundary differs')
    binding = read(case/'trace-2/source-binding.json')
    require(digest(case/'trace-2/source-binding.json') == capture['source_binding_sha256'], 'Binding changed')
    for table in (binding['source_sha256'], capture['source_sha256']):
        require(all(digest(Path(p)) == sha for p, sha in table.items()), 'Capture observer source changed')
    require([event['payload']['pressed'] for event in capture['events']] == [True, False] and
            all(event['outcome'] == 'accepted' for event in capture['events']), 'Full/release control scope differs')
    hits = capture['hits']; require([h['label'] for h in hits] ==
        ['capture-submit-entry','capture-enqueue-return','capture-submit-return'], 'Wrong capture call sequence')
    entry, enqueue, returned = hits
    require(entry['thread'] == enqueue['thread'] == returned['thread'] and
            entry['registers']['sp'] == returned['registers']['sp'] and
            int(entry['registers']['sp'], 16)-4096 <= int(enqueue['registers']['sp'], 16) <=
            int(entry['registers']['sp'], 16), 'Capture call frame differs')
    require(enqueue['registers']['r4'] == '0x10320019' and enqueue['registers']['r7'] == '0x103eae81' and
            enqueue['registers']['r0'] == returned['registers']['r0'] == '0x0', 'Original enqueue result differs')
    queue = enqueue['state']['queue']
    require(queue['count'] == queue['capacity'] == 60 and '0x10320019' not in queue['work_ids_in_order'],
            'Rejected work queue snapshot differs')
    master_path = session/'inputs/master.bin'; master = master_path.read_bytes()
    require(digest(master_path) == MASTER_SHA, 'Original master changed')
    engine = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    static = []
    for pc in (0x1022572E, 0x10225730, 0x10225756, 0x10225762,
               0x1031627A, 0x1031627E, 0x1032518A, 0x10325298, 0x1032529C):
        instruction = next(engine.disasm(master[pc-0x10020000:pc-0x10020000+4], pc))
        static.append({'pc': hex(pc), 'bytes': instruction.bytes.hex(),
                       'mnemonic': instruction.mnemonic, 'operands': instruction.op_str})
    lookup = {int(row['pc'], 16): row for row in static}
    for pc, mnemonic, operand in ((0x1022572E,'cmp','r1, r0'), (0x10225730,'bls','#0x10225756'),
            (0x10225756,'movs','r6, #0'), (0x10225762,'mov','r0, r6'),
            (0x1031627A,'bl','#0x10225714'), (0x1032518A,'movs','r6, #0'),
            (0x10325298,'bl','#0x1031624c'), (0x1032529C,'mov','r0, r6')):
        require((lookup[pc]['mnemonic'], lookup[pc]['operands']) == (mnemonic, operand), 'Original instruction contract differs')
    require(lookup[0x1031627E]['mnemonic'] == 'ldr' and
            lookup[0x1031627E]['operands'].startswith('r0, [pc,'), 'Queue result is not overwritten as reviewed')
    preparation = {}
    for name in ('prepare-after-reject-1', 'prepare-details-1', 'prepare-drain-1', 'prepare-ready-1'):
        path = case/name/'result.json'; row = read(path)
        require(row['completed_observation'] and row['completed_packets'] == 3 and row['window_active'] is False and
                row.get('detach') == 'OK' and not row.get('failure') and not row.get('cleanup_error') and
                row['sources_unchanged'] and not row['controls_sent'] and row['functional_acceptance_eligible'] is False,
                'Preparation observation is incomplete: '+name)
        require(row['prior_trace_sha256'] == digest(capture_path) and
                row['owner']['ProcessId'] == capture['owner']['ProcessId'], 'Preparation used another VM')
        require(all(digest(Path(p)) == sha for p, sha in row['source_sha256'].items()), 'Preparation observer changed')
        for anchor in row['live_anchors']:
            pc = int(anchor['pc'], 16)
            require(master[pc-0x10020000:pc-0x10020000+4].hex() == anchor['bytes'], 'Live preparation anchor differs')
        if name != 'prepare-after-reject-1':
            driver = read(case/(name+'.driver-result.json')); profile = read(case/(name+'.profile.json'))
            require(driver['driver_unchanged'] and driver['completed_observation'] and
                    driver['result_sha256'] == digest(path) and
                    driver['profile_sha256'] == digest(case/(name+'.profile.json')), 'Explicit driver identity differs')
            expected_points = {anchor['pc'] for anchor in row['live_anchors']}
            require(set(profile['points']) == expected_points, 'Explicit preparation point configuration differs')
            driver_name = {'prepare-details-1': 'probe_z62_prepare_details.py',
                'prepare-drain-1': 'probe_z62_prepare_drain.py', 'prepare-ready-1': 'probe_z62_prepare_ready.py'}[name]
            require(digest(Path(__file__).with_name(driver_name)) == profile['driver_sha256'] and
                    digest(Path(__file__).with_name('probe_z62_prepare_packet.py')) == profile['base_source_sha256'],
                    'Explicit driver or base source changed')
        pairs = pair_preparation(row)
        require(not pairs['unreturned_calls'], 'Preparation call has no matching return')
        groups = defaultdict(list)
        for pair in pairs['pairs']:
            groups[pair['name']].append(pair['duration_ns'])
        preparation[name] = {**pairs, 'timing_ns': {key: {'count': len(values), 'minimum': min(values),
            'maximum': max(values)} for key, values in groups.items()}}
        if name == 'prepare-ready-1':
            extra = driver['wait_samples']
            wait_hits = [h for h in row['hits'] if h['label'].startswith('input-ready-wait-')]
            require(len(extra) == len(wait_hits) == 6 and all(e['virtual_time_ns'] == h['virtual_time_ns'] and
                    all(e['registers'][key] == h['registers'][key] for key in ('pc','sp','r0','r1','r2','r3'))
                    for e, h in zip(extra, wait_hits)), 'Additional wait snapshots do not match stopped call sites')
            preparation[name]['wait_samples'] = extra
    record = {'schema': 1, 'completed_evidence_check': True, 'master_sha256': MASTER_SHA,
        'verifier_sha256': digest(Path(__file__)),
        'capture_enqueue_return': 0, 'capture_work_rejected_by_full_queue': True,
        'queue_count': 60, 'queue_capacity': 60, 'work_id': '0x10320019',
        'upper_submit_return': 0, 'upper_submit_return_is_enqueue_success': False,
        'original_instructions': static, 'preparation': preparation, 'artifact_sha256': paths,
        'hardware_cause_of_slow_preparation_verified': False, 'factory_capture_verified': False,
        'functional_acceptance_eligible': False, 'AF_verified': False, 'flash_safety_verified': False,
        'camera_accessed': False}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in record.items() if k not in
        ('preparation','artifact_sha256','original_instructions')}, ensure_ascii=False))
    print(json.dumps({name: row['timing_ns'] for name, row in preparation.items()}, ensure_ascii=False))
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    verify(args.session, args.case, args.output)
