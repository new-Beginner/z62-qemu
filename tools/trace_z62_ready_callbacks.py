"""Observe original shared-work callbacks inside a ready full-press frame.

Frozen C1.70/r9 only. No firmware/register/flag writes. The virtual SD uses
snapshot mode. These calls are not presumed to be exposure submissions.
"""
import argparse
from pathlib import Path

from trace_z62_shutter_route import run


BODY = {
    0x10487120: 'marked-object-callback',
    0x10526024: 'work-table-callback',
    0x1055D544: 'work-change-predicate-return',
    0x10524626: 'work-notification-entry',
    0x1052462E: 'work-notification-gate-return',
    0x105246C8: 'work-notification-submit',
    0x1052918C: 'work-special-operation',
    0x10557AEA: 'work-flags-reset',
}
POINTS = {0x10239734: 'raw-buffer-descriptor',
          0x104E97AC: 'mode-action-entry',
          0x1054512A: 'mode-action-caller-return', **BODY}
WINDOW = {'entry': 0x104E97AC, 'return_pc': 0x1054512A,
          'register': 'r0', 'equals': 0x14, 'points': list(BODY)}


def context(remote, registers):
    pc = registers['pc']
    if pc == 0x10487120:
        pointer = registers['r0']
        if not 0xC0000000 <= pointer <= 0xDFFFFF60:
            raise ValueError('Unexpected marked-object pointer')
        return {'object': hex(pointer), 'callback': hex(registers['r2']),
                'object_160': remote.read(pointer, 160).hex()}
    if pc == 0x10526024:
        return {'callback': hex(registers['r0'])}
    if pc in (0x1055D544, 0x10524626, 0x10557AEA):
        return {'current_context_900': remote.read(0xC202BF40, 900).hex(),
                'previous_context_900': remote.read(0xC202C2C4, 900).hex()}
    return {}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output, args.card, only_points=POINTS,
                 extra_state={0xC1821EB8: 1, 0xC1868AE8: 1}, max_stops=500,
                 wait_for_ready=True, duration=36,
                 breakpoint_window=WINDOW, extra_hit_hook=context)
    print(result['summary'])
    print(result.get('breakpoint_window_events'))
    raise SystemExit(0 if result['shutter_route_observation_completed'] and
                     not result.get('breakpoint_window_active', True) else 1)
