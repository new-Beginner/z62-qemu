"""Observe the original 200-parameter input-ready wait inside preparation."""
import argparse
import json
from pathlib import Path
import struct
from unittest.mock import patch

import probe_z62_prepare_packet as parent
from record_z62_action_evidence import workspace, digest


def run(session, output, previous):
    output = workspace(output)
    calls = {0x103225C4: 'prepare-frame', 0x10232026: 'reconfigure-buffer',
             0x1023AE4E: 'input-ready-function', 0x10238804: 'input-ready-wait'}
    points = {0x10315624: 'packet-entry', 0x10315626: 'packet-return'}
    points.update({pc: label+'-call' for pc, label in calls.items()})
    points.update({pc+4: label+'-return' for pc, label in calls.items()})
    plan = {**parent.PLAN, 'points': [p for pc in calls for p in (pc, pc+4)]}
    before = digest(Path(__file__)); extra = []; original_clock = parent.clock
    def clock(remote):
        now = original_clock(remote)
        raw = remote.regs(); pc = remote.get(raw, 'pc')
        if pc in (0x10238804, 0x10238808):
            registers = {name: remote.get(raw, name) for name in ('pc','sp','lr','r0','r1','r2','r3')}
            extra.append({'virtual_time_ns': now, 'registers': {k: hex(v) for k, v in registers.items()},
                          'input_event_word': hex(struct.unpack('<I', remote.read(0xC188808C, 4))[0]),
                          'output_word_at_sp': hex(struct.unpack('<I', remote.read(registers['sp'], 4))[0])})
        return now
    profile = {'version': '2026.11.03-prepare-ready-r78d', 'driver_sha256': before,
        'base_source_sha256': digest(Path(parent.__file__)), 'points': {hex(k): v for k, v in points.items()},
        'window': plan, 'scope': 'post-r77-capture-rejection', 'functional_acceptance_eligible': False}
    with output.with_suffix('.profile.json').open('x', encoding='utf-8') as handle:
        json.dump(profile, handle, indent=2)
    with patch.object(parent, 'CALLS', calls), patch.object(parent, 'POINTS', points), \
         patch.object(parent, 'PLAN', plan), patch.object(parent, 'clock', clock):
        result = parent.run(session, output, previous)
    with output.with_suffix('.driver-result.json').open('x', encoding='utf-8') as handle:
        json.dump({'profile_sha256': digest(output.with_suffix('.profile.json')),
            'result_sha256': digest(output/'result.json'), 'driver_unchanged': digest(Path(__file__)) == before,
            'completed_observation': result['completed_observation'], 'wait_samples': extra}, handle, indent=2)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--previous-trace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.session, args.output, args.previous_trace)
    raise SystemExit(0 if result['completed_observation'] and result.get('detach') == 'OK' and
                     result.get('sources_unchanged') and not result.get('cleanup_error') else 1)
