"""Read original release requirement bitmaps at the full-request decision."""
import argparse
from pathlib import Path
from unittest.mock import patch

import trace_z62_shutter_route as route
import run_z62_capture_contacts as host
from trace_z62_capture_contact_route import fanout

POINTS = {0x10239734: 'raw-buffer-descriptor',
          0x1022C28A: 'capture-full-request',
          0x1022B630: 'capture-next-state-return',
          0x1022B6BC: 'capture-state-byte-store'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    args = parser.parse_args()
    host.verify_build(host.DEFAULT_QEMU)
    original = route.host.configure_command
    def configure(command, *a, **kw):
        return host.configure_command(original(command, *a, **kw), True)
    with patch.object(route.host, 'DEFAULT_QEMU', host.DEFAULT_QEMU), \
         patch.object(route.host, 'configure_command', configure):
        result = route.run(args.output, args.card, only_points=POINTS,
                           extra_state={0xC1869780: 22, 0xC23E3F24: 64,
                                        0xC1821EB8: 1, 0xC1868AE8: 1},
                           extra_contact_hook=fanout,
                           wait_for_ready=True, duration=36, max_stops=120)
    print(result['summary'])
    raise SystemExit(0 if result['shutter_route_observation_completed'] else 1)
