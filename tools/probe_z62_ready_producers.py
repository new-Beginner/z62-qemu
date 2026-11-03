"""Read actual firmware posts at the five recovered input-ready producer sites."""
import argparse
from collections import Counter
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_prepare_control as parent
from record_z62_action_evidence import workspace, digest, require

PRODUCERS = {0x10239080: (3, 0x100000), 0x1023909E: (4, 0x200000),
             0x102392B2: (96, 0x1000000), 0x102392FC: (101, 0x800000),
             0x10239180: (135, 0x4000000)}


def run(url, session, output):
    output = workspace(output)
    points = {**parent.POINTS, **{pc: 'ready-post-'+str(line) for pc, (line, _) in PRODUCERS.items()}}
    original = parent.ControlTracer
    class ProducerTracer(original):
        def initialize(self):
            super().initialize()
            for pc in PRODUCERS: self.arm(pc)
    before = digest(Path(__file__))
    profile = {'version': '2026.11.03-ready-producers-r81', 'driver_sha256': before,
        'base_source_sha256': digest(Path(parent.__file__)), 'scope': 'same-vm-no-controls',
        'points': {hex(k): v for k, v in points.items()}, 'packets': 2,
        'producer_map': {hex(k): {'line': v[0], 'event_mask': hex(v[1])} for k, v in PRODUCERS.items()},
        'object_first_word_is_event_pattern': False, 'functional_acceptance_eligible': False}
    with output.with_suffix('.profile.json').open('x', encoding='utf-8') as handle:
        json.dump(profile, handle, indent=2)
    with patch.object(parent, 'POINTS', points), patch.object(parent, 'ControlTracer', ProducerTracer):
        result = parent.run(url, session, output, packets=2)
    posts = [hit for hit in result['hits'] if hit['label'].startswith('ready-post-')]
    for hit in posts:
        expected = PRODUCERS[int(hit['registers']['pc'], 16)][1]
        require(hit['registers']['r0'] == '0xc188808c' and int(hit['registers']['r1'], 16) == expected,
                'Observed producer arguments differ from the recovered original call')
    receipt = {'profile_sha256': digest(output.with_suffix('.profile.json')),
        'result_sha256': digest(output/'result.json'), 'driver_unchanged': digest(Path(__file__)) == before,
        'completed_observation': result['completed_observation'],
        'post_counts': dict(Counter(hit['label'] for hit in posts)), 'post_sequences': [hit['sequence'] for hit in posts],
        'scope': 'bounded observed producer calls; no global absence claim',
        'kernel_event_flags_read': False}
    with output.with_suffix('.driver-result.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    print(json.dumps(receipt), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8688')
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = run(args.url, args.session, args.output)
    raise SystemExit(0 if result['completed_observation'] and result.get('detach') == 'OK' and
                     result.get('sources_unchanged') and not result.get('cleanup_error') else 1)
