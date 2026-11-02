"""Observe the native finite-statistics submission without supplying completions."""
import argparse
from pathlib import Path
from types import SimpleNamespace

import trace_z62_capture_setup as capture
import run_z62_raw_stream as host

POINTS = {
    0x10239734: 'raw-buffer-descriptor',
    0x10239EA2: 'statistics-config',
    0x1020C8B2: 'statistics-format',
    0x1020C8BE: 'statistics-layout',
    0x1020C8F0: 'statistics-select-bank',
    0x1023C38A: 'finite-batch-consumer',
    0x1022F986: 'finite-result-task',
    0x102301BC: 'capture-result-task',
}
STATE = {
    0xC26A0468: 16, 0xC26A04A0: 98, 0xC26A060C: 17*5,
    0xC1887CB0: 48, 0xC269F9F4: 12,
    0x2006A200: 93,
}
for ch in range(1, 5):
    base = 0x2006A400 + ch*0x100
    for offset, count in ((0x14,2),(0x24,1),(0x3c,6),(0x60,1),(0x80,1)):
        STATE[base+offset] = count


def run(output, duration, wall_limit):
    # Reuse the validated original-image trace harness, with a fixed passive
    # point set. Each run starts in a fresh process. No private methods patched.
    original_points, original_state = capture.POINTS, capture.STATE
    capture.POINTS, capture.STATE = POINTS, {**capture.STATE, **STATE}
    args = SimpleNamespace(output=output, qemu=host.DEFAULT_QEMU,
        native_source=True, input_drain=True, frame_start=True,
        boundary_experiment=False, boundary_line=136, ready_bit_experiment=False,
        ready_set_experiment=False, lifecycle=False, frame_objects=False,
        ownership=False, metadata_event_experiment=False, startup_waits=False,
        virtual_limit=duration, wall_limit=wall_limit, menu_at=1000, poll=2, max_stops=600)
    def hit(remote, reg):
        if reg['pc'] == 0x10239EA2:
            data = remote.read(reg['r0'], 0x44)
            headers = {}
            for offset in (0x2c, 0x30, 0x34, 0x38, 0x3c, 0x40):
                pointer = int.from_bytes(data[offset:offset+4], 'little')
                if 0xC0000000 <= pointer < 0xCFFFFFF0-0x80:
                    headers[hex(offset)] = {'pointer': hex(pointer), 'bytes': remote.read(pointer, 0x80).hex()}
            return {'config_68': data.hex(), 'output_headers': headers}
        if reg['pc'] in (0x1020C8B2, 0x1020C8BE):
            return {'descriptor_32': remote.read(reg['r1'], 32).hex()}
        return {}
    try:
        return capture.run(args, extra_hit_hook=hit)
    finally:
        capture.POINTS, capture.STATE = original_points, original_state


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=12)
    parser.add_argument('--wall-limit', type=float, default=600)
    args = parser.parse_args()
    if not 10 <= args.duration <= 30 or not 60 <= args.wall_limit <= 900:
        parser.error('duration must be 10..30, wall-limit 60..900')
    result = run(args.output, args.duration, args.wall_limit)
    print('observed=',result['capture_setup_observed'], 'stop=',result.get('stop_reason'))
    raise SystemExit(0 if result['capture_setup_observed'] else 1)
