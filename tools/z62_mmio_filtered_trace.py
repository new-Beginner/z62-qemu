"""Read the selected-address event separately; keep the r64 reader immutable."""
import z62_mmio_write_trace as base
from z62_mmio_filter_device import EVENT

pair_controls = base.pair_controls


def parse_line(line):
    if type(line) is not str: raise ValueError('Trace line must be text')
    if EVENT not in line: return None
    if line.count(EVENT) != 1 or base.EVENT in line: raise ValueError('Ambiguous selected memory event')
    return base.parse_line(line.replace(EVENT, base.EVENT, 1))


def parse_lines(lines):
    result = []
    for number, line in enumerate(lines, 1):
        row = parse_line(line)
        if row is not None:
            row.update(file_line=number, trace_entry=len(result)+1)
            result.append(row)
    return result
