"""Read component 0x47/0x50 descriptors and original initialization notices."""
import argparse
import struct
from pathlib import Path
from unittest.mock import patch

import trace_z62_shutter_route as route
import run_z62_capture_contacts as host


def context(remote, registers):
    if registers['pc'] != 0x10239734:
        return {}
    rows = []
    for component in (0x0B, 0x47, 0x50):
        address = 0xC185EBA8 + component * 0x1C
        data = remote.read(address, 28)
        words = struct.unpack('<7I', data)
        if data[0] != component:
            raise ValueError('Original component directory identity mismatch')
        if words[5] >= 0x40:
            raise ValueError('Unexpected component implementation index')
        implementation_address = 0xC185E5FC + words[5] * 44
        implementation = struct.unpack('<11I', remote.read(implementation_address, 44))
        literals = {}
        for value in (*words, *implementation):
            if 0x10020000 <= value <= 0x123FFF80:
                literals[hex(value)] = remote.read(value, 128).hex()
        rows.append({'component': hex(component), 'address': hex(address),
                     'words': [hex(v) for v in words], 'rom_targets_128': literals,
                     'implementation_address': hex(implementation_address),
                     'implementation_words': [hex(v) for v in implementation]})
    return {'component_directory': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=2)
    args = parser.parse_args()
    if not 2 <= args.duration <= 40:
        parser.error('duration must be 2..40 seconds')
    host.verify_build(host.DEFAULT_QEMU)
    state = {0xC1868490: 48, 0xC1869780: 22, 0xC23E3F24: 16}
    state.update({0xC20A3348 + n * 0x30: 12 for n in (0x0B, 0x47, 0x50)})
    with patch.object(route.host, 'DEFAULT_QEMU', host.DEFAULT_QEMU):
        result = route.run(args.output, args.card,
                           only_points={0x10239734: 'raw-buffer-descriptor',
                                        0x1026E794: 'capture-component-notice'},
                           extra_state=state, extra_hit_hook=context,
                           duration=args.duration, max_stops=100)
    print(result['summary'])
    ok = result.get('capture_setup_observed') and result.get('stop_reason') == 'virtual limit'
    raise SystemExit(0 if ok else 1)
