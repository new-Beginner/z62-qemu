"""Read both virtual input engines without changing their completion sources.

CPU0/CPU2 are this board's address views, not a physical EXPEED topology claim.
The snapshot is deliberately non-atomic; failed reads remain unknown.
"""
import json
import re

VERSION = '2026.11.03-statistics-observe-r60'
CONTROL_ADDRESSES = tuple(0x20068000+x for x in (0, 4, 8, 12, 16, 20, 24, 0x100))
DMA_OFFSETS = (0x14, 0x18, 0x24, 0x3c, 0x40, 0x44, 0x48, 0x4c, 0x50, 0x60, 0x80)
PLANE_OFFSETS = (0x54, 0x58, 0x5c, 0x64, 0x68, 0x6c)
BOOT_BOOLS = ('statistics-model-started', 'statistics-model-enable', 'statistics-model-support')
BOOT_COUNTS = ('statistics-control-count', 'statistics-frame-calls', 'statistics-frame-pulses',
               'statistics-commit-pulses', 'frame-sync-count')
INPUT_BOOLS = ('continuous-enabled', 'continuous-active', 'continuous-rearm', 'continuous-clock-level',
               'functional-continuous-stats', 'functional-finite-stats', 'functional-raw')
INPUT_COUNTS = ('continuous-attempts', 'continuous-frames', 'continuous-batches', 'continuous-rejected',
                'continuous-blocked', 'continuous-bytes', 'continuous-index', 'continuous-source',
                'finite-attempts', 'finite-frames', 'finite-batches', 'finite-rejected',
                'raw-accepted', 'raw-rejected')


def parse_control_trace(rows):
    if type(rows) is not list or len(rows) > 256:
        raise ValueError('Invalid statistics control ring')
    previous = 0
    result = []
    for row in rows:
        if type(row) is not dict:
            raise ValueError('Invalid statistics control record')
        for name in ('sequence', 'qemu_virtual_ns', 'frame_count', 'cpu'):
            if type(row.get(name)) is not int or row[name] < (-1 if name == 'cpu' else 0):
                raise ValueError('Invalid control integer: '+name)
        if row['sequence'] <= previous:
            raise ValueError('Control sequences must increase; gaps are retained')
        previous = row['sequence']
        for name in ('address', 'value', 'mask_after', 'pc'):
            if type(row.get(name)) is not str or not re.fullmatch(r'0x[0-9a-fA-F]{1,8}', row[name]):
                raise ValueError('Invalid control hex word: '+name)
        if int(row['address'], 16) not in CONTROL_ADDRESSES:
            raise ValueError('Address outside observed control family')
        for name in ('started_before', 'started_after', 'model_supported', 'model_enable', 'pc_valid'):
            if type(row.get(name)) is not bool:
                raise ValueError('Invalid control bool: '+name)
        if row['pc_valid'] != (row['cpu'] >= 0):
            raise ValueError('Inconsistent control CPU/PC availability')
        result.append(dict(row))
    return result


def _discover(qmp, cache):
    if 'statistics_roles' in cache:
        return cache['statistics_roles']
    cpus = qmp.command('query-cpus-fast')
    if not {0, 2} <= {r['cpu-index'] for r in cpus}:
        raise ValueError('Expected board CPU0 and CPU2 views')
    roles = {}
    for obj in qmp.command('qom-list', {'path': '/machine/unattached'}):
        if obj.get('type') != 'child<nikon-z72-boot-config>':
            continue
        path = '/machine/unattached/'+obj['name']
        master = qmp.command('qom-get', {'path': path, 'property': 'master-role'})
        if type(master) is not bool:
            raise ValueError('Invalid engine role type')
        role = 'master' if master else 'slave'
        if role in roles:
            raise ValueError('Duplicate statistics engine role: '+role)
        roles[role] = path
    if set(roles) != {'master', 'slave'}:
        raise ValueError('Expected exactly one engine per role')
    cache['statistics_roles'] = roles
    return roles


def _words(qmp, cpu, address, count):
    response = qmp.command('human-monitor-command', {
        'command-line': 'x /'+str(count)+'wx '+hex(address), 'cpu-index': cpu})
    if type(response) is not str:
        raise ValueError('Invalid HMP response')
    words = []
    for line in response.splitlines():
        if ':' not in line:
            if line.strip():
                raise ValueError('HMP memory read failed: '+line)
            continue
        _, data = line.split(':', 1)
        tokens = data.split()
        if any(not re.fullmatch(r'0x[0-9a-fA-F]{1,8}', token) for token in tokens):
            raise ValueError('Invalid HMP memory words')
        words.extend(int(token, 16) for token in tokens)
    if len(words) != count:
        raise ValueError('Incomplete HMP read at '+hex(address))
    return words


def collect(machine, cache):
    result = {'schema': 1, 'version': VERSION, 'read_only': True, 'snapshots_atomic': False,
              'memory_view': 'board-master-cpu0-slave-cpu2', 'engines': {}}
    with machine.io:
        roles = _discover(machine.qmp, cache)
        for role, cpu in (('master', 0), ('slave', 2)):
            row = {'boot_path': roles[role], 'cpu_index': cpu, 'errors': [], 'boot': {},
                   'input': {}, 'controls': {}, 'control_trace': None, 'dma': []}

            def attempt(label, operation):
                try:
                    return operation()
                except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
                    row['errors'].append({'field': label, 'type': type(exc).__name__, 'message': str(exc)})
                    return None

            def prop(path, name, kind):
                value = machine.qmp.command('qom-get', {'path': path, 'property': name})
                if type(value) is not kind or (kind is int and value < 0):
                    raise ValueError('Unexpected QOM property type: '+name)
                return value

            for name in (*BOOT_BOOLS, *BOOT_COUNTS):
                row['boot'][name] = attempt(name, lambda: prop(roles[role], name, bool if name in BOOT_BOOLS else int))
            for name in (*INPUT_BOOLS, *INPUT_COUNTS, 'continuous-reason', 'finite-reason', 'raw-last-reason'):
                kind = bool if name in INPUT_BOOLS else str if name.endswith('reason') else int
                row['input'][name] = attempt(name, lambda: prop('/machine/'+role+'-input', name, kind))
            row['control_trace'] = attempt('control_trace', lambda: parse_control_trace(json.loads(
                prop(roles[role], 'statistics-control-trace', str))))
            for address in (*CONTROL_ADDRESSES, 0x20068270, 0x20068290):
                row['controls'][hex(address)] = attempt(hex(address), lambda: _words(machine.qmp, cpu, address, 1)[0])
            row['formatter_words'] = attempt('formatter', lambda: _words(machine.qmp, cpu, 0x20069500, 13))
            row['geometry_words'] = attempt('geometry', lambda: _words(machine.qmp, cpu, 0x2006a200, 93))
            for channel in range(5):
                fields = DMA_OFFSETS+(PLANE_OFFSETS if channel >= 2 else ())
                base = 0x2006a400+channel*0x100
                values = {hex(offset): attempt(hex(base+offset),
                    lambda offset=offset: _words(machine.qmp, cpu, base+offset, 1)[0]) for offset in fields}
                row['dma'].append({'channel': channel, 'base': hex(base), 'fields': values})
            row['known'] = not row['errors']
            result['engines'][role] = row
    result['known'] = all(row['known'] for row in result['engines'].values())
    return result
