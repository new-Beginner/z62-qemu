"""Bounded stock-pool observations, not a general allocator ABI certificate."""
from memory_contract import collect as memory_collect, literal
from startup_contract import read_inputs, require, sha, ROOT
from pathlib import Path

REGISTERS = tuple(f'r{i}' for i in range(13)) + ('sp', 'lr', 'pc', 'cpsr')
CALLEE_SAVED = tuple(f'r{i}' for i in range(4, 12))
SYSTEM = ('TTBR0_S', 'TTBCR_S', 'DACR_S', 'SCTLR_EL1_S', 'VBAR_EL1_S',
          'DFSR_S', 'IFSR_S', 'DFSR', 'IFSR')
FALSE_FIELDS = ('firmware_integrated', 'flash_safety_verified', 'camera_accessed',
                'debugger_guest_registers_written', 'debugger_guest_memory_written',
                'injected_calls', 'original_firmware_patched', 'parameters_loaded',
                'card_attached', 'controller_loaded', 'earlier_camera_loader_executed',
                'allocator_call_abi_verified', 'allocation_lifetime_verified',
                'plugin_execution_in_heap_verified')


def collect():
    result = memory_collect()
    images = read_inputs()
    for role, p in result['roles'].items():
        api = p['static_pool_api_candidates']
        a = api['allocate_entry']
        # Original final address calculation: pool_data + index*2048 - 2048.
        offset = literal(images[role], a + 0x174, 1)
        require(offset == 0xFFFFF800, 'Pool data offset changed')
        p['observed_api'] = dict(allocate=api['allocate_entry'], release=api['release_entry'],
                                 data_index_bias=-1, address_literal=offset)
    result['pool_observer_sources'] = {
        Path(__file__).relative_to(ROOT).as_posix(): sha(Path(__file__).read_bytes())}
    result['tool'] = 'fenestra-z62-stock-pool-calls/0.1'
    result['imports_equivalent'] = ('Raw ARM/Thumb: original direct calls, ARM pool wrappers, '
                                    'pool-state literals and original return addresses; no PE IAT')
    return result


def header_index(geometry, pointer):
    g = geometry
    if not isinstance(pointer, int) or not g['pool_end'] <= pointer < g['end']:
        return None
    if (pointer - g['pool_end']) % g['block_bytes']:
        return None
    return (pointer - g['pool_end']) // g['block_bytes'] + 1


def sample_indices(g, pointer=None, blocks=None):
    indices = {0, 1, 2, g['count']}
    i = header_index(g, pointer)
    if i is not None:
        indices.update((i - 1, i, i + 1))
        if isinstance(blocks, int) and 0 < blocks <= g['count']:
            indices.update((i + blocks - 1, i + blocks))
    return sorted(i for i in indices if 0 <= i <= g['count'])


def extent(snapshot, g, pointer):
    i = header_index(g, pointer)
    if i is None:
        return None
    rows = {r['index']: r['words'] for r in snapshot['headers']}
    if i not in rows or not rows[i][0] & 2:
        return None
    if rows[i][0] & 1:
        require(i + 1 in rows, 'Missing length header')
        return rows[i + 1][0] >> 2
    return 1


class Ledger:
    """Pair on CPU, role, restored stack, PC and ISA, not CPU identity alone.

    RSP CPU threads are NOT RTOS task IDs. Migration or unmatched returns remain
    unpaired; overlapping calls are reported, never assigned isolated deltas.
    """
    def __init__(self):
        self.calls = []
        self.pending = {}

    def enter(self, event):
        require(event['kind'] in ('allocate', 'release'), 'Bad call kind')
        r = event['registers']
        require(r['cpsr'] & 32 == 0, 'Pool entry is not ARM')
        call_id = len(self.calls)
        overlaps = [i for i, c in self.pending.items() if c['entry']['role'] == event['role']]
        call = dict(id=call_id, entry=event, overlaps=overlaps, return_event=None)
        for i in overlaps:
            self.calls[i]['overlaps'].append(call_id)
        self.calls.append(call)
        self.pending[call_id] = call
        return call_id

    def match(self, event):
        r = event['registers']
        matches = []
        for i, c in self.pending.items():
            e, er = c['entry'], c['entry']['registers']
            if (e['role'] == event['role'] and e['thread'] == event['thread'] and
                    er['sp'] == r['sp'] and (er['lr'] & ~1) == r['pc'] and
                    bool(er['lr'] & 1) == bool(r['cpsr'] & 32)):
                matches.append(i)
        require(len(matches) <= 1, 'Ambiguous original return')
        return matches[0] if matches else None

    def returned(self, call_id, event):
        require(self.match(event) == call_id, 'Wrong return context')
        self.pending.pop(call_id)['return_event'] = event

    def return_addresses(self):
        return {c['entry']['registers']['lr'] & ~1 for c in self.pending.values()}


def check_snapshot(snapshot, p, pointer=None, blocks=None):
    g = p['geometry']
    state = snapshot['state']
    require(state[0] == g['count'] and 0 <= state[1] <= g['count'] and
            state[2:] == [g['start'], g['pool_end']], 'Pool state geometry changed')
    indices = sample_indices(g, pointer, blocks)
    require([r['index'] for r in snapshot['headers']] == indices, 'Header sample set changed')
    for row in snapshot['headers']:
        require(row['address'] == g['start'] + row['index'] * 8 and
                len(row['words']) == 2 and all(0 <= w < 2**32 for w in row['words']),
                'Invalid bounded header sample')


def check_event(event, contract):
    p = contract['roles'][event['role']]
    r, s = event['registers'], event['system_registers']
    require(set(r) == set(REGISTERS), 'Missing register evidence')
    require(s['TTBR0_S'] == p['copied_table'] and s['TTBCR_S'] == 0 and
            s['DACR_S'] == 0x55555555 and s['VBAR_EL1_S'] == p['vector'], 'MMU context changed')
    require(s['SCTLR_EL1_S'] & 0x1005 == 0x1005, 'MMU/cache disabled')
    require(all(s[n] == 0 for n in ('DFSR_S', 'IFSR_S', 'DFSR', 'IFSR')), 'Observed CPU fault')
    require(event['thread'] in ('01', '02', '03', '04'), 'Unknown CPU')
    require(int(event['thread'], 16) in ((1, 2) if event['role'] == 'master' else (3, 4)),
            'CPU/image role differs')


def check_pair(call, contract):
    e, ret = call['entry'], call['return_event']
    if ret is None:
        return dict(paired=False)
    er, rr = e['registers'], ret['registers']
    p = contract['roles'][e['role']]
    g = p['geometry']
    require(e['kind'] in p['observed_api'] and er['pc'] == p['observed_api'][e['kind']], 'Entry PC changed')
    require(er['cpsr'] & 32 == 0, 'Pool entry ISA changed')
    require(all(er[n] == rr[n] for n in CALLEE_SAVED) and er['sp'] == rr['sp'],
            'Original callee-saved registers/stack not restored')
    require(er['cpsr'] & 31 == rr['cpsr'] & 31, 'Original processor mode not restored')
    isolated = not call['overlaps']
    if e['kind'] == 'allocate':
        n, ptr = er['r0'], rr['r0']
        check_snapshot(e['pool'], p)
        check_snapshot(ret['pool'], p, ptr, n)
        if ptr:
            i = header_index(g, ptr)
            require(i is not None and 0 < n <= g['count'] and ptr + n * 0x800 <= g['end'],
                    'Returned allocation out of bounds')
            if isolated:
                require(extent(ret['pool'], g, ptr) == n, 'Allocation extent differs from block request')
                h = next(h['words'] for h in ret['pool']['headers'] if h['index'] == i)
                require(h[1] & 3 == int(bool(er['r1'] & 0x10000)), 'Observed allocation bit16 tag differs')
        if isolated:
            require(ret['pool']['state'][1] - e['pool']['state'][1] == (-n if ptr else 0),
                    'Isolated observed allocation count delta differs')
        return dict(paired=True, isolated_observed=isolated, successful=bool(ptr), blocks=n,
                    pointer=ptr, flags=er['r1'])
    ptr = er['r0']
    n = extent(e['pool'], g, ptr)
    check_snapshot(e['pool'], p, ptr, n)
    check_snapshot(ret['pool'], p, ptr, n)
    if isolated and rr['r0'] == 0 and n is not None:
        require(ret['pool']['state'][1] - e['pool']['state'][1] == n, 'Release block count delta differs')
        i = header_index(g, ptr)
        h = next(h['words'] for h in ret['pool']['headers'] if h['index'] == i)
        require(not h[0] & 2, 'Released observed header still in-use')
    return dict(paired=True, isolated_observed=isolated, successful=rr['r0'] == 0,
                blocks=n, pointer=ptr, original_return=rr['r0'])


def analyze_events(events, contract):
    ledger = Ledger()
    for number, event in enumerate(events):
        require(event['sequence'] == number, 'Event sequence gap')
        check_event(event, contract)
        if event['kind'] in ('allocate', 'release'):
            p = contract['roles'][event['role']]
            require(event['registers']['pc'] == p['observed_api'][event['kind']], 'Wrong entry address')
            ledger.enter(event)
        elif event['kind'] == 'return':
            i = ledger.match(event)
            require(i is not None, 'Unpaired recorded return')
            ledger.returned(i, event)
        else:
            raise ValueError('Unknown event kind')
    results = [dict(id=c['id'], role=c['entry']['role'], kind=c['entry']['kind'],
                    **check_pair(c, contract)) for c in ledger.calls]
    return ledger, results


def summarize(results):
    return {role: {kind: dict(entries=sum(r['role'] == role and r['kind'] == kind for r in results),
                             paired=sum(r['role'] == role and r['kind'] == kind and r['paired'] for r in results),
                             isolated_success=sum(r['role'] == role and r['kind'] == kind and
                                                  r.get('isolated_observed', False) and r.get('successful', False)
                                                  for r in results))
                   for kind in ('allocate', 'release')} for role in ('master', 'slave')}
