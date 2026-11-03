"""Observe the original post-settings drain calls inside the same r78 frame."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_prepare_packet as parent
from record_z62_action_evidence import workspace, digest


def run(session, output, previous):
    output = workspace(output)
    calls = {0x103225C4: 'prepare-frame', 0x10321BD0: 'submit-frame',
        0x102339EE: 'apply-frame-settings', 0x10233B14: 'drain-one',
        0x10233B1C: 'drain-two', 0x10233B38: 'drain-two-alternate',
        0x10232026: 'drain-buffer'}
    points = {0x10315624: 'packet-entry', 0x10315626: 'packet-return'}
    points.update({pc: label+'-call' for pc, label in calls.items()})
    points.update({pc+4: label+'-return' for pc, label in calls.items()})
    plan = {**parent.PLAN, 'points': [p for pc in calls for p in (pc, pc+4)]}
    before = digest(Path(__file__))
    profile = {'version': '2026.11.03-prepare-drain-r78c', 'driver_sha256': before,
        'base_source_sha256': digest(Path(parent.__file__)), 'points': {hex(k): v for k, v in points.items()},
        'window': plan, 'scope': 'post-r77-capture-rejection', 'functional_acceptance_eligible': False}
    with output.with_suffix('.profile.json').open('x', encoding='utf-8') as handle:
        json.dump(profile, handle, indent=2)
    with patch.object(parent, 'CALLS', calls), patch.object(parent, 'POINTS', points), patch.object(parent, 'PLAN', plan):
        result = parent.run(session, output, previous)
    with output.with_suffix('.driver-result.json').open('x', encoding='utf-8') as handle:
        json.dump({'profile_sha256': digest(output.with_suffix('.profile.json')),
            'result_sha256': digest(output/'result.json'), 'driver_unchanged': digest(Path(__file__)) == before,
            'completed_observation': result['completed_observation']}, handle, indent=2)
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
