"""r64b adds an opt-in diagnostic event; existing event and callbacks stay intact."""
from pathlib import Path
import reference_updates as reference

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.11.03-r64b'
WORK = ROOT/'.build'/('z62-mmio-filter-'+VERSION)
EVENT = 'nikon_z62_mmio_write'
INPUTS = {'system/memory.c': '1706bc565c96fc6c8dcb465aa28cd2e273fdf243e762c1dd4ac00f6c73569d7d',
          'system/trace-events': '29b58bd8adc5150b6c99d71b5ae8df0ce15139594181cd8615e1c2e24f303d58'}
WINDOWS = ((0x20060000, 0x2006c000), (0x20100000, 0x20110000), (0x20380000, 0x20381000))


def identity():
    return {'schema': 1, 'version': VERSION, 'input_sha256': INPUTS,
            'adapter_sha256': reference.sha(Path(__file__).read_bytes()), 'event': EVENT,
            'address_windows_exclusive_end': [list(v) for v in WINDOWS],
            'default_enabled': False, 'legacy_trace_event_preserved': True,
            'guest_or_model_state_changed': False, 'vmstate_version_unchanged': 52,
            'accepted_write_inferred_from_trace': False}


def render(files):
    for name, expected in INPUTS.items():
        if reference.sha(files[name]) != expected: raise ValueError('Filtered trace requires frozen r62 '+name)
    result = {name: data.decode('utf-8') for name, data in files.items()}
    source = result['system/memory.c']
    old = '''    } else if (trace_event_get_state_backends(TRACE_MEMORY_REGION_OPS_WRITE)) {
        hwaddr abs_addr = memory_region_to_absolute_addr(mr, addr);
        trace_memory_region_ops_write(get_cpu_index(), mr, abs_addr, tmp, size,
                                      memory_region_name(mr));
    }'''
    if source.count(old) != 2: raise ValueError('Expected both unchanged memory write accessors')
    source = source.replace(old, '''    } else {
        z62_diagnostic_memory_write(mr, addr, tmp, size);
    }''')
    helper = '''/* Selected diagnostics only. Neither dispatch nor the device result changes. */
static void z62_diagnostic_memory_write(MemoryRegion *mr, hwaddr addr,
                                        uint64_t value, unsigned size)
{
    bool standard = trace_event_get_state_backends(TRACE_MEMORY_REGION_OPS_WRITE);
    bool selected = trace_event_get_state_backends(TRACE_NIKON_Z62_MMIO_WRITE);
    if (!standard && !selected) {
        return;
    }
    hwaddr absolute = memory_region_to_absolute_addr(mr, addr);
    if (standard) {
        trace_memory_region_ops_write(get_cpu_index(), mr, absolute, value, size,
                                      memory_region_name(mr));
    }
    if (selected && ((absolute >= 0x20060000 && absolute < 0x2006c000) ||
                     (absolute >= 0x20100000 && absolute < 0x20110000) ||
                     (absolute >= 0x20380000 && absolute < 0x20381000))) {
        trace_nikon_z62_mmio_write(get_cpu_index(), mr, absolute, value, size,
                                   memory_region_name(mr));
    }
}

'''
    source = reference.replace_once(source, 'static MemTxResult memory_region_write_accessor(',
                                     helper+'static MemTxResult memory_region_write_accessor(')
    result['system/memory.c'] = source
    definitions = result['system/trace-events']
    line = next(v for v in definitions.splitlines() if v.startswith('memory_region_ops_write('))
    new = line.replace('memory_region_ops_write(', EVENT+'(', 1)
    result['system/trace-events'] = reference.replace_once(definitions, line, line+'\n'+new)
    return {name: data.encode('utf-8') for name, data in result.items()}


def apply_source(source):
    root = Path(source)
    result = render({name: (root/name).read_bytes() for name in INPUTS})
    for name, data in result.items(): (root/name).write_bytes(data)
    return result
