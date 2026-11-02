"""Recompute input-route research conclusions; never certify camera firmware."""
import argparse
import hashlib
import json
from pathlib import Path

from decompile_z62 import audit_exports
from probe_z62_liveview import expected_raw_prefix

ROOT = Path(__file__).resolve().parents[1]


def load_trace(relative):
    path = ROOT/relative/'trace.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    if (data.get('camera_accessed') is not False or data.get('guest_state_patched') is not False or
            data.get('live_anchors_verified') is not True or data.get('process_closed') is not True or
            data.get('detach') != 'OK' or data.get('failure') or data.get('cleanup_error')):
        raise ValueError('Trace evidence incomplete: '+str(path))
    return data, {'path': relative+'/trace.json', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def paired_input_waits(data):
    hits = {hit['sequence']: hit for hit in data['hits']}
    result = []
    for wait in data['summary']['waits']:
        entry = hits.get(wait['entry_hit'])
        if entry and entry['registers']['pc'] == '0x10238804':
            if int(entry['registers']['r1'], 16) != 0x05B00000:
                raise ValueError('Unexpected input wait mask')
            result.append(wait)
    return result


def check():
    result = {'schema': 1, 'complete_emulator': False, 'camera_safety_verified': False,
              'r8_binary_built': False, 'evidence': {}, 'readiness': {}}
    for name in ('baseline', 'ready-bit', 'ready-set'):
        trace, evidence = load_trace('analysis/z62-input-ready-r8/'+name)
        result['evidence']['ready-'+name] = evidence
        waits = paired_input_waits(trace)
        passed = [w for w in waits if w['result'] != 0]
        if not waits or len(passed) != (1 if name == 'ready-set' else 0):
            raise ValueError('Ready-route result changed: '+name)
        result['readiness'][name] = {'paired_waits': len(waits), 'successes': len(passed),
            'timeouts': sum(w['result'] == 0 for w in waits), 'success_records': passed}
        if name != 'baseline':
            experiments = trace['device_experiments']
            if len(experiments) != 1 or experiments[0]['raw_prefix'] != expected_raw_prefix().hex():
                raise ValueError('Missing actual RAW readback')
    trace, evidence = load_trace('analysis/z62-input-lifecycle-r8/baseline')
    result['evidence']['lifecycle'] = evidence
    relevant = [h for h in trace['hits'] if h['label'] == 'stop-selected-channels']
    if not relevant or relevant[0]['registers']['r0'] != '0x2eb':
        raise ValueError('Selected-channel stop missing')
    reopen = next(k for k in trace['keys'] if k['label'] == 'reopen-1')
    first_menu = next(s for s in trace['observations'] if s['stage'] == 'after-reopen' and
                      s['cycle'] == 1 and s['index'] == 1)
    result['lifecycle'] = {'stop_virtual_seconds': relevant[0]['state']['virtual_seconds'],
        'first_reopen_index1_delay': round(first_menu['virtual_seconds']-reopen['virtual_seconds'], 6),
        'stop_reason': trace['stop_reason'], 'strict_menu_acceptance': False,
        'drain_bitmap_before_stop': relevant[0]['state']['extra_words']['0xc269f9f4'][5],
        'upper_drain_041a0004_hits': trace['summary']['counts'].get('upper-drain-041a0004', 0),
        'upper_drain_041a0006_hits': trace['summary']['counts'].get('upper-drain-041a0006', 0)}
    baseline, evidence = load_trace('analysis/z62-frame-objects-r8/baseline')
    result['evidence']['frame-baseline'] = evidence
    if baseline['summary']['counts'].get('metadata-consumer', 0):
        raise ValueError('Passive baseline unexpectedly consumed metadata')
    trace, evidence = load_trace('analysis/z62-frame-objects-r8/metadata-bit')
    result['evidence']['metadata-bit'] = evidence
    events = trace.get('device_experiments', [])
    if len(events) != 1 or events[0].get('lines') != [6] or events[0].get('statistics_data_verified') is not False:
        raise ValueError('Metadata event provenance missing')
    callbacks = [h for h in trace['hits'] if h['label'] == 'capture-result-callback' and
                 h['registers']['r0'] == '0x41a0002']
    if len(callbacks) != 1 or callbacks[0]['registers']['r1'] == '0x0':
        raise ValueError('Expected nonnull native metadata object not observed')
    callback = callbacks[0]
    producers = [h for h in trace['hits'] if h['label'] == 'capture-frame-object-return' and
                 h['registers']['r0'] == callback['registers']['r1'] and h['sequence'] < callback['sequence']]
    if not producers:
        raise ValueError('Metadata object was not observed in original producer')
    result['metadata'] = {'native_object': callback['registers']['r1'],
        'producer_hit': producers[0]['sequence'], 'consumer_hit': callback['sequence'],
        'native_raw_batches_before_event': events[0]['native_raw_batches'],
        'metadata_consumer_hits': trace['summary']['counts'].get('metadata-consumer', 0),
        'pixel_processing_verified': False}
    trace, evidence = load_trace('analysis/z62-frame-objects-r8/ownership-metadata2')
    result['evidence']['ownership'] = evidence
    records = [h for h in trace['hits'] if h.get('extra_observation', {}).get('frame_object') == '0xc2cf2c40']
    produced = next(h for h in records if h['label'] == 'capture-frame-object-return')
    stored = [h for h in records if h['label'] == 'frame-release-stored']
    release = next(h for h in records if h['label'] == 'metadata-release-call')
    masks = [produced['extra_observation']['pending_mask']] + [h['extra_observation']['pending_mask'] for h in stored]
    if masks != ['0x40001', '0x40000', '0x0'] or release['registers']['r1'] != '0x40000':
        raise ValueError('Native frame ownership transition not reproduced')
    result['ownership'] = {'object': '0xc2cf2c40', 'mask_transitions': masks,
        'metadata_release_mask': release['registers']['r1'],
        'record_sequences': [produced['sequence']] + [h['sequence'] for h in stored],
        'function_1023594e_hits': trace['summary']['counts'].get('frame-processing-submit', 0),
        'this_does_not_prove_all_isp_paths_were_traced': True}
    functions = (0x10239128, 0x1023926E, 0x102392B8, 0x10239314, 0x1023935C, 0x102390CA, 0x102391C4)
    audit = audit_exports(ROOT/'analysis/z62-ghidra/input-lifecycle-tbb', functions)
    if not audit['all_exports_structurally_usable']:
        raise ValueError('Corrected callback decompilation has structural errors')
    result['decompilation'] = audit
    result['research_evidence_verified'] = True
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = check()
    if args.output:
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))
