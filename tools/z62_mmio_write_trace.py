"""Strict QEMU10.2.4 log reader: attempted writes, never implicit success."""
import re

VERSION = '2026.11.03-mmio-write-r64'
EVENT = 'memory_region_ops_write'
BODY = re.compile(r"cpu (-?\d+) mr ((?:0x)?[0-9a-fA-F]+) addr (0x[0-9a-fA-F]+) "
                  r"value (0x[0-9a-fA-F]+) size (1|2|4|8) name '([^'\r\n]+)'")


def parse_line(line):
    if type(line) is not str: raise ValueError('Trace line must be text')
    if EVENT not in line: return None
    if line.count(EVENT) != 1: raise ValueError('Ambiguous memory write event')
    prefix, body = line.rstrip('\r\n').split(EVENT, 1)
    match = BODY.fullmatch(body.strip())
    if match is None: raise ValueError('Malformed known memory write event')
    cpu = int(match[1]); pointer = int(match[2], 16); address = int(match[3], 16)
    value = int(match[4], 16); size = int(match[5])
    if cpu < -1 or cpu > 0x7fffffff or not 0 < pointer < 1 << 64 or not 0 <= address < 1 << 64 or value >= 1 << (size*8):
        raise ValueError('Memory write event field outside its numeric domain')
    return {'cpu': cpu, 'region_pointer': hex(pointer), 'address': address, 'value': value, 'size': size,
            'region_name': match[6], 'host_prefix_opaque': prefix, 'qemu_virtual_ns': None,
            'board_view': 'master' if cpu in (0, 1) else 'slave' if cpu in (2, 3) else 'controller' if cpu == 4 else None,
            'accepted_write_verified': False, 'event_is_before_device_callback': True}


def parse_lines(lines):
    result = []
    for number, line in enumerate(lines, 1):
        row = parse_line(line)
        if row is not None:
            row.update(file_line=number, trace_entry=len(result)+1)
            result.append(row)
    return result


def pair_controls(events, histories):
    addresses = {0x20068000+x for x in (0, 4, 8, 12, 16, 20, 24, 0x100)}
    grouped = {'master': [], 'slave': []}; unknown = []
    for event in events:
        if event['address'] not in addresses: continue
        role = event['board_view']
        if role not in grouped: unknown.append(event)
        else: grouped[role].append(event)
    result = {'pairs': {}, 'tail_after_last_ring_sample': {}, 'unattributed_control_writes': unknown,
              'entire_debugger_cleanup_interval_verified': False}
    for role in grouped:
        expected = histories[role]; actual = grouped[role]
        if len(actual) < len(expected): raise ValueError('Missing '+role+' control write attempts')
        paired = []
        for event, row in zip(actual, expected):
            if (event['address'], event['value'], event['size'], event['cpu']) != (
                    int(row['address'], 16), int(row['value'], 16), 4, row['cpu']):
                raise ValueError('Control trace/ring mismatch at '+role+' sequence '+str(row['sequence']))
            paired.append({**row, 'trace_entry': event['trace_entry'], 'file_line': event.get('file_line')})
        result['pairs'][role] = paired
        result['tail_after_last_ring_sample'][role] = actual[len(expected):]
    return result
