"""The descriptor carrier before paired parameter serialization (read-only)."""
import struct

from z62_paired_source_snapshot import read_packet, core_packet, source_packet

VERSION = '2026.11.03-frame-source-r57'
CONSTRUCTORS = {0x102c1d98: 0x102c1e1c, 0x102c1e1e: 0x102c1ea2}
POINTS = {pc: 'original-paired-constructor-entry' for pc in CONSTRUCTORS}
POINTS.update({pc: 'original-paired-constructor-written' for pc in CONSTRUCTORS.values()})
MASTER_ROOT = 0xc2379584


def capture(remote, context_address, root_address, *, after):
    context = read_packet(remote, context_address, 0x388)
    if not context['captured']:
        raise ValueError('Cannot read original paired frame context')
    raw = bytes.fromhex(context['raw'])
    count = struct.unpack_from('<I', raw, 4)[0]
    supported = 0 <= count <= 4
    descriptors = []
    if supported:
        for index in range(count):
            address = struct.unpack_from('<I', raw, 8+index*4)[0]
            item = {**read_packet(remote, address, 64), 'layout_fields': None,
                    'dma_address': None, 'format_byte24': None}
            if item['captured']:
                data = bytes.fromhex(item['raw'])
                stride, width, height = struct.unpack_from('<3H', data, 0x26)
                item.update(layout_fields=[width, height, stride],
                            dma_address=hex(struct.unpack_from('<I', data, 0x34)[0]),
                            format_byte24=data[0x24])
            descriptors.append(item)
    template_address = struct.unpack_from('<I', raw, 0x35c)[0]
    template = core_packet(remote, template_address)
    root = read_packet(remote, root_address, 212) if after else None
    flags, serialized_core, serialized_source = None, None, None
    if root and root['captured']:
        words = struct.unpack('<53I', bytes.fromhex(root['raw']))
        flags = {'word51_cc': words[51], 'word52_d0': words[52]}
        serialized_core = core_packet(remote, words[0])
        serialized_source = source_packet(remote, words[3])
    core_match = None
    if template['captured'] and serialized_core and serialized_core['captured']:
        core_match = template['layout_argument'] == serialized_core['layout_argument']
    return {'schema': 1, 'version': VERSION, 'after_serialization': after,
            'context': context, 'root_address': hex(root_address),
            'is_master_root': root_address == MASTER_ROOT,
            'descriptor_count': count, 'descriptor_count_supported': supported,
            'descriptors': descriptors, 'template_core': template,
            'all_source_descriptors_captured': bool(supported and count and
                all(d['captured'] for d in descriptors)),
            'context_flags': {hex(offset): struct.unpack_from('<I', raw, offset)[0]
                              for offset in (0x368, 0x370, 0x374, 0x37c)},
            'serialized_root': root, 'serialized_root_flags': flags,
            'serialized_core': serialized_core, 'serialized_source': serialized_source,
            'template_matches_serialized_geometry': core_match,
            'read_only': True, 'snapshots_atomic': False,
            'descriptor_is_a_fresh_dma_generation': False,
            'actual_pixel_production_verified': False}
