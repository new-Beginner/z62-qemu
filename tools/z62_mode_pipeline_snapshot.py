"""Read the programmed Z62 r48 data path without assuming its photo geometry.

Offsets are from the frozen local device contracts, not from Z7II addresses.
RAM samples are observations: they prove neither a fresh producer nor execution.
"""
import hashlib
import json
import struct

VERSION = '2026.11.03-mode-pipeline-r50'
INPUT_BASE = 0x20068000
RAW_FIELDS = (8, 0x14, 0x18, 0x24, 0x3c, 0x40, 0x44, 0x48, 0x4c,
              0x50, 0x54, 0x58, 0x5c, 0x60, 0x64, 0x68, 0x6c, 0x80)
DMA_FIELDS = (0x14, 0x18, 0x24, 0x3c, 0x40, 0x44, 0x48, 0x4c,
              0x50, 0x60, 0x74, 0x80)
PLANE_FIELDS = (0x54, 0x58, 0x5c, 0x64, 0x68, 0x6c)
UNIT_OFFSETS = (0xe60, 0x900, 0xde0, 0x8a0, 0x8c0, 0x8e0,
                0x9e0, 0x940, 0xba0, 0x920, 0x9c0)
# Candidate windows already used by the local RAM/pool contracts. Never read an
# arbitrary high pointer as RAM, notably the F8xx GIC/peripheral address space.
RAM_WINDOWS = ((0x82c00000, 0xbed17000), (0xbf700000, 0xbff24a00),
               (0xc1800000, 0xc4000000), (0xcea00000, 0xd4dcb400),
               (0xd4e00000, 0xdd63b000), (0xdd700000, 0xf0000000))


def read(memory, address, size):
    data = memory.read(address, size)
    if not isinstance(data, bytes) or len(data) != size:
        raise ValueError('Incomplete mode pipeline read at '+hex(address))
    return data


def words(data):
    return list(struct.unpack('<' + str(len(data)//4) + 'I', data))


def candidate_ram(address, size):
    return (type(address) is int and type(size) is int and size > 0 and
            not address & 3 and any(start <= address and address+size <= end
                                    for start, end in RAM_WINDOWS))


def sample(memory, address, stride, height, *, full=False):
    result = {'pointer': hex(address), 'stride': stride, 'height': height,
              'captured': False, 'memory_region_type_verified': False}
    size = stride*height
    limit = 1024*1024 if full else 64*1024*1024
    if not (0 < stride <= 65536 and 0 < height <= 8192 and size <= limit):
        return {**result, 'reason': 'geometry-or-budget'}
    if not candidate_ram(address, size):
        return {**result, 'reason': 'outside-bounded-ram-candidates'}
    try:
        if full:
            data = read(memory, address, size)
            result.update(raw=data.hex(), sha256=hashlib.sha256(data).hexdigest(),
                          captured_bytes=len(data), full_span_read=True)
        else:
            count = min(64, stride)
            first = read(memory, address, count)
            last_address = address+(height-1)*stride
            last = first if last_address == address else read(memory, last_address, count)
            result.update(first_row_prefix=first.hex(), last_row_prefix=last.hex(),
                          captured_bytes=len(first)+(len(last) if last_address != address else 0),
                          full_span_read=False)
        result['captured'] = True
    except (OSError, RuntimeError, ValueError) as exc:
        result['error'] = {'type': type(exc).__name__, 'message': str(exc)}
    return result


def capture(memory):
    # Each disjoint input-config read is admitted by input_config_accepts().
    # In particular, the DMA windows contain holes and cannot be dumped whole.
    formatter = read(memory, 0x20069500, 0x34)
    raw_fields = {hex(offset): words(read(memory, 0x20069a00+offset, 4))[0]
                  for offset in RAW_FIELDS}
    stats_geometry = read(memory, 0x2006a200, 0x174)
    stats_dma = []
    for channel in range(5):
        fields = DMA_FIELDS + (PLANE_FIELDS if channel >= 2 else ())
        base = 0x2006a400+channel*0x100
        stats_dma.append({'channel': channel, 'base': hex(base),
                          'fields': {hex(offset): words(read(memory, base+offset, 4))[0]
                                     for offset in fields}})
    descriptors = read(memory, 0x20100400, 0x400)
    unit_registers = read(memory, 0x20100800, 0x800)
    controls = read(memory, 0x20102000, 0x400)
    commands = read(memory, 0x20102600, 0x50)
    paired_raw = read(memory, 0x20380000, 0x440)
    ports = [{'index': i, 'address': hex(0x20100400+i*64),
              'words': words(descriptors[i*64:i*64+52]),
              'raw_40': descriptors[i*64:(i+1)*64].hex()} for i in range(16)]
    tables = [{'address': hex(0x20102200+bank*0x100),
               'rows': [words(controls[0x200+bank*0x100+i*64:
                                      0x200+bank*0x100+(i+1)*64]) for i in range(4)]}
              for bank in range(2)]
    fw = words(formatter)
    width, height = fw[6] >> 16, fw[7] >> 16
    stride = raw_fields['0x8']
    bank = raw_fields['0x3c'] & 1
    raw_destinations = [raw_fields[hex(0x50+bank*16+i*4)] for i in range(4)]
    result = {'schema': 1, 'version': VERSION, 'read_only': True,
              'snapshots_atomic': False, 'physical_layout_verified': False,
              'numerical_execution_verified': False, 'generation_freshness_verified': False,
              'raw': {'formatter_address': '0x20069500', 'formatter_raw': formatter.hex(),
                      'width_field_high16': width, 'height_field_high16': height,
                      'width_field_low16': fw[6] & 65535, 'height_field_low16': fw[7] & 65535,
                      'dma_fields': raw_fields, 'selected_bank_bit0': bank,
                      'selected_destinations': [hex(p) for p in raw_destinations],
                      'buffer_samples': [sample(memory, p, stride, height) for p in raw_destinations]},
              'input_controls': {hex(address): words(read(memory, address, 4))[0]
                                 for address in (0x20068008, 0x20068010, 0x20068018, 0x20068290)},
              'statistics_geometry_raw': stats_geometry.hex(), 'statistics_dma': stats_dma,
              'paired_raw_address': '0x20380000', 'paired_raw_440': paired_raw.hex(),
              'ports': ports, 'map_tables': tables,
              'core_controls_400': controls.hex(), 'unit_registers_800': unit_registers.hex(),
              'command_groups': {'0': words(commands[0x40:0x4c]), '1': words(commands[:12])},
              'unit_parameters': [], 'grid_views': []}
    for offset in UNIT_OFFSETS:
        header = unit_registers[offset-0x800:offset-0x800+24]
        unit = words(header)
        candidate = {'pointer': hex(unit[4]), 'captured': False}
        if candidate_ram(unit[4], 160):
            try:
                raw = read(memory, unit[4], 160)
                candidate.update(captured=True, raw=raw.hex(), sha256=hashlib.sha256(raw).hexdigest())
            except (OSError, RuntimeError, ValueError) as exc:
                candidate['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        result['unit_parameters'].append({'offset': hex(offset), 'registers': unit,
                                         'payload_semantics_verified': False,
                                         'payload_candidate': candidate})
    source_port, output_port = ports[1]['words'], ports[2]['words']
    for table in tables:
        for index, row in enumerate(table['rows']):
            gh, oh = source_port[8] >> 16, output_port[8] >> 16
            result['grid_views'].append({'map_address': table['address'], 'slot': index,
                'width_field_low15': source_port[8] & 0x7fff,
                'height_field_high16': gh,
                'input_planes': [sample(memory, row[1]+delta, source_port[4+c], gh, full=True)
                                 for c, delta in enumerate((0, source_port[10], source_port[11]))],
                'packed_output': sample(memory, row[2], output_port[4], oh)})
    result['register_fingerprint_sha256'] = hashlib.sha256(json.dumps(
        [formatter.hex(), raw_fields, stats_geometry.hex(), stats_dma,
         descriptors.hex(), unit_registers.hex(), controls.hex(), commands.hex(), paired_raw.hex()],
        sort_keys=True).encode('utf-8')).hexdigest()
    return result
