"""Read native GPIO resource bindings after C1.70 initialization on frozen r9.

No GPIO levels are driven during this two-second observation. Resource IDs
come from the original lookup table, not from another camera's pin numbers.
"""
import argparse
import struct
from pathlib import Path

from trace_z62_shutter_route import run


def ram(pointer, length):
    if not 0xC0000000 <= pointer <= 0xE0000000 - length:
        raise ValueError('GPIO resource outside mapped working RAM')
    return pointer


def bindings(remote, registers):
    if registers['pc'] != 0x10239734:
        return {}
    mapping = struct.unpack('<I', remote.read(0xC1800008, 4))[0]
    if not (0x10020000 <= mapping <= 0x12400000 - 354 or
            0xC0000000 <= mapping <= 0xE0000000 - 354):
        raise ValueError('Unexpected logical GPIO mapping location')
    ids = struct.unpack('<177H', remote.read(mapping, 354))
    rows = []
    for logical, resource in enumerate(ids):
        if resource >= 0x200:
            rows.append({'logical': logical, 'resource': resource, 'unsupported': True})
            continue
        pointer = struct.unpack('<I', remote.read(0xC18AEDC8 + resource * 4, 4))[0]
        if pointer == 0:
            rows.append({'logical': logical, 'resource': resource, 'pointer': '0x0'})
            continue
        data = remote.read(ram(pointer, 56), 56)
        words = struct.unpack('<14I', data)
        rows.append({'logical': logical, 'resource': resource, 'pointer': hex(pointer),
                     'bytes_56': data.hex(), 'bit': words[1],
                     'input_register': hex(words[2]), 'irq_field_20': hex(words[8]),
                     'ext_index': words[9], 'callback': hex(words[12]),
                     'edge_mode': data[52]})
    return {'logical_mapping_pointer': hex(mapping), 'gpio_bindings': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output, args.card,
                 only_points={0x10239734: 'raw-buffer-descriptor'},
                 extra_hit_hook=bindings, duration=2, max_stops=10)
    observed = any('gpio_bindings' in h.get('extra_observation', {}) for h in result['hits'])
    print({'bindings_observed': observed, 'stop_reason': result.get('stop_reason'),
           'process_closed': result.get('process_closed')})
    raise SystemExit(0 if observed and result.get('stop_reason') == 'virtual limit' and
                     result.get('process_closed') and not result['shutter_contacts'] else 1)
