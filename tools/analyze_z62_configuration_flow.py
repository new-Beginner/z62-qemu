"""Correlate ordered configuration sites in one observed CPU/caller stack.

Shared return/epilogue hits without an observed call remain outside the scope.
This does not prove an entire input run completed or any hardware accepted work.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

CALL, RETURN, UPDATED = 0x103226AE, 0x103226B2, 0x103226BA


def pair_calls(trace):
    pending, calls, incomplete, outside = {}, [], [], []
    previous_sequence = 0
    observations = 0
    for hit in trace['hits']:
        data = hit.get('extra_observation', {}).get('configuration')
        if data is None:
            continue
        sequence = hit['sequence']
        if type(sequence) is not int or sequence <= previous_sequence or not isinstance(data, dict):
            raise ValueError('Configuration records must have strictly ordered native sequences')
        previous_sequence = sequence
        pc = int(hit['registers']['pc'], 16)
        if pc not in (CALL, RETURN, UPDATED):
            raise ValueError('Unrecognized configuration instruction site')
        thread = hit['thread']
        stack = int(hit['registers']['sp'], 16)
        key = thread, stack
        event = {'sequence': sequence, 'guest_seconds': hit['state']['virtual_seconds'],
                 'registers': deepcopy(hit['registers']), 'configuration': deepcopy(data)}
        observations += 1
        if pc == CALL:
            if key in pending:
                incomplete.append({**pending.pop(key), 'reason': 'new call before previous frame completed'})
            pending[key] = {'thread': thread, 'sp': hex(stack), 'call': event}
            continue
        span = pending.get(key)
        if span is None:
            outside.append({'sequence': sequence, 'pc': hex(pc), 'thread': thread, 'sp': hex(stack)})
        elif pc == RETURN:
            if 'return' in span:
                incomplete.append({**pending.pop(key), 'extra_return': event,
                                   'reason': 'duplicate return before control update'})
            else:
                span['return'] = event
        elif 'return' not in span:
            incomplete.append({**pending.pop(key), 'control_updated': event,
                               'reason': 'control update without observed return'})
        else:
            calls.append({**pending.pop(key), 'control_updated': event})
    incomplete.extend({**span, 'reason': 'input ended before caller frame completed'} for span in pending.values())
    return {'schema': 1, 'configuration_site_observations': observations, 'calls': calls,
            'incomplete': incomplete, 'outside_scope_count': len(outside), 'outside_scope': outside,
            'all_observed_calls_paired': bool(calls) and not incomplete,
            'correlation': 'native sequence, GDB CPU thread and exact caller SP',
            'input_stop_reason': trace.get('stop_reason'),
            'input_process_closed': trace.get('process_closed'),
            'input_trace_complete': trace.get('trace_complete'),
            'global_state_samples_atomic': False, 'hardware_completion_verified': False,
            'mode_recovery_verified': False, 'whole_camera_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.input.read_bytes()
    result = pair_calls(json.loads(source))
    result.update(input_sha256=hashlib.sha256(source).hexdigest(),
                  analyzer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'paired_calls': len(result['calls']), 'incomplete': len(result['incomplete']),
                      'outside_scope': result['outside_scope_count'],
                      'input_stop_reason': result['input_stop_reason']}))
