"""Decode existing snapshots without treating programmed storage as new pixels.

The two output ring groups follow original Z62 1036CC9C/CE56; enables follow
1036CC0A. MAIN dimensions come from the captured committed gate slot8. Numerical
formats and active phase ownership require separate evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

VERSION = '2026.11.03-paired-contract-r55'


def decode(capture):
    data = bytes.fromhex(capture.get('paired_raw_800', ''))
    if len(data) != 0x800:
        raise ValueError('Require the complete 0x800-byte paired capture')
    word = lambda offset: struct.unpack_from('<I', data, offset)[0]
    array = lambda offset: [word(offset+i*4) for i in range(4)]

    def enabled(a, b, name):
        values = [word(a), word(b)]
        if values not in ([0, 0], [1, 1]):
            raise ValueError(name+' enable pair disagrees or is not boolean')
        return values == [1, 1]

    def rings(first, second, stride):
        def rows(base):
            return [{'phase_index': i, 'first': hex(a), 'second': hex(b), 'plane_delta': b-a}
                    for i, (a, b) in enumerate(zip(array(base), array(base+16)))]
        one, two = rows(first), rows(second)
        return {'first_ring': one, 'second_ring': two,
                'stride_field': word(stride),
                'second_ring_matches_first': one == two,
                'unique_first_ring_pairs': len({(r['first'], r['second']) for r in one}),
                'all_four_indices_are_independent_frames': False,
                'active_phase_verified': False}

    raw = capture['raw']
    raw_layout = [raw['width_field_high16'], raw['height_field_high16'], raw['dma_fields']['0x8']]
    dimensions = word(0x48)
    source_layout = [dimensions >> 16, dimensions & 65535, word(0x30c)]
    slots = array(0x310)
    upstream_slots = [int(p, 16) for p in raw['selected_destinations']]
    port = next((p for p in capture['ports'] if p['index'] == 8), None)
    if port is None or len(port['words']) != 13:
        raise ValueError('Missing complete committed slot8')
    p = port['words']
    slot_layout = [p[8] & 0x7fff, p[8] >> 16, p[4]]
    main = rings(0x488, 0x4a8, 0x4c8)
    special = all(r['first'] == '0x40000000' and r['second'] == '0x40008000'
                  for r in main['first_ring']+main['second_ring'])
    main.update(enabled=enabled(0x420, 0x428, 'MAIN'),
                selector_field=word(0x424), slot_format_field=hex(p[0]),
                slot_layout_fields=slot_layout, slot_uv_offset=p[10],
                all_uv_deltas_match_slot=all(r['plane_delta'] == p[10]
                    for r in main['first_ring']+main['second_ring']),
                address_kind='shared-port' if special else 'ordinary-address-candidates',
                ram_backing_verified=False)
    work = rings(0x430, 0x450, 0x470)
    work.update(enabled=enabled(0x408, 0x410, 'WORK'),
                registers_retained=any(word(o) for o in range(0x430, 0x474, 4)),
                active_history_verified=False, physical_plane_format_verified=False)
    # Normalize a presence observation to a boolean, never to an enable bit.
    work['registers_retained'] = bool(work['registers_retained'])
    return {'schema': 1, 'version': VERSION, 'read_only': True,
            'upstream_raw': {'layout_fields': raw_layout, 'addresses': [hex(v) for v in upstream_slots]},
            'paired_source': {'layout_fields': source_layout, 'addresses': [hex(v) for v in slots]},
            'source_address_sets_equal': len(upstream_slots) == 4 and set(slots) == set(upstream_slots),
            'source_layouts_equal': source_layout == raw_layout,
            'main': main, 'work': work,
            'scheduling_fields': {hex(o): word(o) for o in (0x88, 0x8c, 0x94, 0x9c, 0xa8, 0x10c, 0x138, 0x13c, 0x140)},
            'actual_pixel_production_verified': False,
            'physical_pixel_format_verified': False,
            'guest_or_device_state_written': False}


def run(pipeline, output):
    if output.exists():
        raise FileExistsError('Existing paired contract evidence is immutable')
    data = pipeline.read_bytes()
    source = json.loads(data)
    rows, errors = [], []
    for capture in source['captures']:
        try:
            value = decode(capture)
            rows.append({'virtual_seconds': capture['virtual_seconds'],
                         'selector_phase_observed': capture['selector_phase_observed'], **value})
        except (KeyError, ValueError, TypeError) as exc:
            errors.append({'virtual_seconds': capture.get('virtual_seconds'),
                           'type': type(exc).__name__, 'message': str(exc)})
    result = {'schema': 1, 'version': VERSION, 'completed_decode': bool(rows and not errors),
              'pipeline': str(pipeline.resolve()), 'pipeline_sha256': hashlib.sha256(data).hexdigest(),
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'captures': rows, 'decode_errors': errors, 'new_device_implemented': False,
              'actual_pixel_production_verified': False, 'whole_camera_verified': False}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({'completed_decode': result['completed_decode'], 'captures': len(rows),
                      'decode_errors': errors,
                      'layouts': [{'phase': r['selector_phase_observed'],
                          'paired': r['paired_source']['layout_fields'],
                          'main': r['main']['slot_layout_fields'], 'work': r['work']['enabled']}
                          for r in rows]}, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pipeline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.pipeline, args.output)['completed_decode'] else 1)
