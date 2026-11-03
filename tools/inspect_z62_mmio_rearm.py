"""Literal DMA/formatter/commit ledger bracketed by observed control writes.

Addresses are not assigned hardware meanings here. Attempts remain attempts.
An absent upper control bracket is kept unknown, including possible cleanup.
"""
import argparse
from bisect import bisect_left
from collections import Counter
import hashlib
import json
from pathlib import Path

VERSION = '2026.11.03-mmio-rearm-ledger-r64b'
BLOCKS = (('frontend0', 0x20068500, 0x20068820), ('formatter1', 0x20069500, 0x20069534),
          ('raw_dma0', 0x20069800, 0x20069900), ('raw_dma1', 0x20069900, 0x20069a00),
          ('raw_dma2', 0x20069a00, 0x20069b00), ('raw_dma3', 0x20069b00, 0x20069c00),
          ('statistics_geometry', 0x2006a200, 0x2006a374), ('statistics_dma', 0x2006a400, 0x2006a900),
          ('sensor_mode', 0x20063000, 0x20065600), ('input_controls', 0x20068000, 0x20068400),
          ('isp', 0x20100000, 0x20110000), ('paired', 0x20380000, 0x20381000))


def require(condition, message):
    if not condition: raise ValueError(message)


def bracket(entry, pairs):
    indices = [p['trace_entry'] for p in pairs]
    position = bisect_left(indices, entry)
    exact = position < len(indices) and indices[position] == entry
    previous = pairs[position-1] if position else None
    following = pairs[position+1] if exact and position+1 < len(pairs) else pairs[position] if not exact and position < len(pairs) else None
    return {'same_control_sequence': pairs[position]['sequence'] if exact else None,
            'previous_control_sequence': previous['sequence'] if previous else None,
            'next_control_sequence': following['sequence'] if following else None,
            'exact_write_virtual_time_inferred': False}


def compact(rows, pairs):
    grouped = {}
    for row in rows:
        key = (row['board_view'], row['address'], row['size'])
        group = grouped.setdefault(key, {'board_view': row['board_view'], 'address': hex(row['address']),
            'size': row['size'], 'attempt_count': 0, 'attempt_values_first_seen': [], 'same_value_repeat_attempts': 0,
            'first_trace_entry': row['trace_entry'], 'first_file_line': row['file_line']})
        if group['attempt_count'] and group['last_value'] == row['value']: group['same_value_repeat_attempts'] += 1
        if row['value'] not in group['attempt_values_first_seen']: group['attempt_values_first_seen'].append(row['value'])
        group.update(attempt_count=group['attempt_count']+1, last_value=row['value'], last_trace_entry=row['trace_entry'],
                     last_file_line=row['file_line'], last_control_bracket=bracket(row['trace_entry'], pairs.get(row['board_view'], [])))
    return list(grouped.values())


def inspect(directory):
    directory = directory.resolve(); path = directory/'mmio-write-lifecycle.json'
    raw = path.read_bytes(); data = json.loads(raw)
    require(data['trace_parse_complete'] is True, 'Trace did not parse completely')
    summary = data['trace_summary']; require(summary['control_pairing_verified'] is True, 'Control/ring pairing not verified')
    log = directory/'mmio-write.log'
    require(hashlib.sha256(log.read_bytes()).hexdigest() == data['log_sha256'], 'Raw log changed')
    source = directory/'statistics-control-lifecycle.json'; control = json.loads(source.read_text(encoding='utf-8'))
    pairs = summary['control_pairing']['pairs']; lookup = {p['sequence']: p for p in pairs['master']}
    low_stores = [c for c in control['calls'] if c['write_candidate'] is not None]
    ring_stores = [r for r in control['control_records']['master'] if int(r['address'], 16) in (0x20068008, 0x2006800c)]
    require(len(low_stores) == len(ring_stores), 'Observed original store count differs from ring')
    mode_stops = []
    for call, record in zip(low_stores, ring_stores):
        write = call['write_candidate']
        require((write['address'], write['value']) == (hex(int(record['address'], 16)), int(record['value'], 16)), 'Original store order differs')
        if (call['pc'] == '0x1020a832' and write['value'] == 0x10 and
                call['caller'].get('callsite') == '0x1023c610'):
            pair = lookup[record['sequence']]
            mode_stops.append({'call_sequence': call['sequence'], 'observer_counter_seconds': call['observer_counter_seconds'],
                'control_sequence': record['sequence'], 'trace_entry': pair['trace_entry'], 'file_line': pair['file_line'],
                'qemu_virtual_ns_at_control': record['qemu_virtual_ns'], 'frame_count_at_control': record['frame_count']})
    attempts = summary['selected_attempts']; intervals = []
    for index, stop in enumerate(mode_stops):
        upper = mode_stops[index+1]['trace_entry'] if index+1 < len(mode_stops) else None
        rows = [r for r in attempts if r['trace_entry'] > stop['trace_entry'] and (upper is None or r['trace_entry'] < upper)]
        groups = {}
        for name, low, high in BLOCKS:
            subset = [r for r in rows if low <= r['address'] < high]
            groups[name] = {'attempt_count': len(subset), 'registers': compact(subset, pairs)}
        intervals.append({'after_stop': stop, 'before_next_stop_trace_entry': upper,
            'unbounded_tail_may_include_cleanup': upper is None, 'blocks': groups,
            'accepted_writes_proven_by_this_ledger': False})
    return {'schema': 1, 'version': VERSION, 'source_data_sha256': hashlib.sha256(raw).hexdigest(),
        'source_control_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'log_sha256': data['log_sha256'],
        'inspector_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'completed_requested_observation': data['completed_observation'],
        'trace_covers_requested_window': data['trace_covers_requested_window'],
        'selected_attempt_count': len(attempts), 'by_board_view': dict(Counter(str(r['board_view']) for r in attempts)),
        'mode_stops': mode_stops, 'intervals': intervals,
        'all_available_samples_control_paired': True, 'physical_register_meanings_verified': False,
        'new_rearm_model_implemented': False, 'camera_accessed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError('Existing ledger is immutable')
    result = inspect(args.directory)
    with args.output.open('x', encoding='utf-8') as handle: json.dump(result, handle, indent=2)
    print(json.dumps({'completed_requested_observation': result['completed_requested_observation'],
        'mode_stops': result['mode_stops'], 'interval_block_counts': [{name: v['attempt_count'] for name, v in i['blocks'].items()}
                                                                  for i in result['intervals']]}, indent=2), flush=True)
