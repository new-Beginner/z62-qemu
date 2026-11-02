"""Locate native release requirement producers during initialization only."""
import argparse
from pathlib import Path
from unittest.mock import patch

import trace_z62_shutter_route as route
import run_z62_capture_contacts as host


def context(remote, registers):
    return {'caller_stack_96': remote.read(registers['sp'], 96).hex()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    args = parser.parse_args()
    host.verify_build(host.DEFAULT_QEMU)
    with patch.object(route.host, 'DEFAULT_QEMU', host.DEFAULT_QEMU):
        result = route.run(args.output, args.card,
                           only_points={0x10239734: 'raw-buffer-descriptor',
                                        0x10229C2C: 'release-requirement-set',
                                        0x10229BC4: 'release-requirement-clear'},
                           extra_state={0xC1869780: 22, 0xC23E3F24: 16},
                           extra_hit_hook=context, duration=2, max_stops=250)
    print(result['summary'])
    ok = (result.get('capture_setup_observed') and result.get('stop_reason') == 'virtual limit'
          and not result['shutter_contacts'])
    raise SystemExit(0 if ok else 1)
