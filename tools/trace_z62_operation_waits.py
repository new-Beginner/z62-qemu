"""Observe local call durations inside queued work 10322449, before shutter input.

No completion injection or queue modifications. The default 18 second window ends before
the readiness-based shutter schedule; it is not a full capture acceptance run.
"""
import argparse
import json
from pathlib import Path

from probe_z62_no_lens import run

POINTS = {
    0x10315624: 'operation-work-call',
    0x10315626: 'operation-work-return',
}
CALLS = {0x10322572: 'allocate-a', 0x10322590: 'allocate-b',
         0x10322596: 'parameters-a', 0x103225A6: 'compare-a',
         0x103225C4: 'prepare-frame', 0x103225D8: 'allocate-c',
         0x103225DE: 'parameters-b', 0x103225F0: 'compare-b',
         0x10322664: 'compare-c', 0x103226AE: 'change-mode',
         0x103226B6: 'state-machine'}
for address, name in CALLS.items():
    POINTS[address] = 'worker-' + name + '-call'
    POINTS[address+4] = 'worker-' + name + '-return'
WINDOW = {'entry': 0x10315624, 'return_pc': 0x10315626, 'register': 'r1',
          'equals': 0x10322449,
          'points': [p for a in CALLS for p in (a, a+4)]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=18)
    parser.add_argument('--prepare-details', action='store_true')
    args = parser.parse_args()
    if not 2 <= args.duration <= 18:
        parser.error('This pre-shutter observation must be 2..18 virtual seconds')
    if args.prepare_details:
        details = {0x10321BD0: 'submit-frame', 0x102335AC: 'query-frame-settings',
                   0x102335E0: 'frame-event8', 0x1023382C: 'frame-event15',
                   0x102339EE: 'apply-frame-settings'}
        for address, name in details.items():
            POINTS[address] = 'worker-' + name + '-call'
            POINTS[address+4] = 'worker-' + name + '-return'
            WINDOW['points'].extend((address, address+4))
    result, _ = run(args.output, args.card, args.group23, True, True, args.duration,
                    extra_points=POINTS, extra_state={0xC23D9F14: 6, 0xC1868A70: 36},
                    breakpoint_window=WINDOW, max_stops=1800)
    # A trace may end inside one slow call. The tracer must still remove all
    # hardware breakpoints and close its owned instance successfully.
    complete = bool(result.get('capture_setup_observed') and
                    result.get('stop_reason') == 'virtual limit' and
                    result.get('process_closed') and result.get('detach') == 'OK' and
                    not result.get('failure') and not result.get('cleanup_error') and
                    result['observations'][-1]['virtual_seconds'] >= args.duration and
                    not result.get('shutter_contacts'))
    summary = {'observation_completed': complete, 'photo_capture_verified': False,
               'complete_emulator': False, 'ended_inside_window': result.get('breakpoint_window_active'),
               'waits': [{'label': h['label'], 'time': h['state']['virtual_seconds'],
                          'registers': h['registers']} for h in result['hits']
                         if h['label'].startswith('worker-')], 'counts': result['summary']['counts']}
    with (args.output / 'worker-waits.json').open('x', encoding='utf-8') as handle:
        json.dump(summary, handle, indent=2)
    print(json.dumps({k: v for k, v in summary.items() if k != 'waits'}, indent=2))
    raise SystemExit(0 if complete else 1)
