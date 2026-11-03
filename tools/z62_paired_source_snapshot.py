"""Original paired parameter packets, not guessed hardware or image outputs."""
import hashlib
import struct

import z62_mode_pipeline_snapshot as memory

VERSION = '2026.11.03-paired-source-r56'
DISPATCH, FORMAT_ENTRY, FORMAT_RETURN = 0x102e750e, 0x1036c3b0, 0x1036c3dc
POINTS = {DISPATCH: 'original-paired-parameter-dispatch',
          FORMAT_ENTRY: 'original-paired-geometry-entry',
          FORMAT_RETURN: 'original-paired-geometry-written'}


def read_packet(remote, address, size):
    result = {'pointer': hex(address), 'requested_bytes': size, 'captured': False, 'raw': None}
    if address == 0:
        return {**result, 'reason': 'absent-pointer'}
    candidate = memory.candidate_ram(address & ~3, size+(address & 3)) or (
        0xc4000000 <= address and address+size <= 0xc5f00000)
    if not candidate:
        return {**result, 'reason': 'outside-bounded-master-ram-candidates'}
    try:
        raw = memory.read(remote, address, size)
        result.update(captured=True, raw=raw.hex(), sha256=hashlib.sha256(raw).hexdigest())
    except (OSError, RuntimeError, ValueError) as exc:
        result['error'] = {'type': type(exc).__name__, 'message': str(exc)}
    return result


def core_packet(remote, address):
    result = {**read_packet(remote, address, 68), 'layout_argument': None, 'origin_argument': None}
    if result['captured']:
        x, y, width, height = struct.unpack_from('<4H', bytes.fromhex(result['raw']), 44)
        result.update(layout_argument=[width, height], origin_argument=[x, y])
    return result


def source_packet(remote, address):
    result = {**read_packet(remote, address, 80), 'stride_argument': None, 'first_ring_argument': None}
    if result['captured']:
        data = bytes.fromhex(result['raw'])
        result.update(stride_argument=struct.unpack_from('<H', data, 76)[0],
                      first_ring_argument=[hex(p) for p in struct.unpack_from('<4I', data, 12)])
    return result


def environment(remote, object_address):
    obj = read_packet(remote, object_address, 8)
    if not obj['captured']:
        raise ValueError('Cannot read the original paired object')
    bank = bytes.fromhex(obj['raw'])[4]
    if bank not in (0, 1):
        raise ValueError('Unknown original paired object bank')
    formatter = memory.words(memory.read(remote, 0x20069500, 52))
    raw_stride = memory.words(memory.read(remote, 0x20069a08, 4))[0]
    base = 0x20380000+bank*0x40000
    dimensions = memory.words(memory.read(remote, base+0x48, 4))[0]
    stride = memory.words(memory.read(remote, base+0x30c, 4))[0]
    return {'object': obj, 'bank_byte4': bank,
            'upstream': {'layout_fields': [formatter[6] >> 16, formatter[7] >> 16, raw_stride]},
            'paired': {'layout_fields': [dimensions >> 16, dimensions & 65535, stride],
                       'register_base': hex(base)}}


def dispatch(remote, object_address, root_address):
    root = read_packet(remote, root_address, 208)
    if not root['captured']:
        raise ValueError('Cannot read the original 52-pointer parameter array')
    pointers = memory.words(bytes.fromhex(root['raw']))
    before = environment(remote, object_address)
    return {'schema': 1, 'version': VERSION, 'kind': 'dispatch-entry', 'root': root,
            'pointer_arguments': [hex(p) for p in pointers], 'object': before['object'],
            'bank_byte4': before['bank_byte4'], 'core': core_packet(remote, pointers[0]),
            'source': source_packet(remote, pointers[3]),
            'outputs': read_packet(remote, pointers[9], 156),
            'upstream_before': before['upstream'], 'paired_before': before['paired'],
            'configuration_has_already_been_written': False,
            'snapshots_atomic': False, 'actual_pixel_production_verified': False}


def format_packet(remote, object_address, geometry_address, *, after):
    core = core_packet(remote, geometry_address-44)
    observed = environment(remote, object_address)
    matches = bool(core['captured'] and core['layout_argument'] == observed['paired']['layout_fields'][:2])
    return {'schema': 1, 'version': VERSION, 'kind': 'geometry-written' if after else 'geometry-entry',
            'core': core, 'object': observed['object'], 'bank_byte4': observed['bank_byte4'],
            'upstream_observed': observed['upstream'], 'paired_observed': observed['paired'],
            'geometry_argument_matches_observed': matches if after else None,
            'source_stride_has_been_written_by_geometry_setter': False,
            'snapshots_atomic': False, 'actual_pixel_production_verified': False}
