"""Bounded stock byte-heap evidence; not a public allocator or ownership ABI."""
from heap_contract import collect as static_collect, aligned_size, descriptor_for_flags
from pool_calls import Ledger, CALLEE_SAVED, check_event as check_cpu, FALSE_FIELDS
from startup_contract import require

TOOL = 'fenestra-z62-byte-heap-observer/0.1.0'


def collect():
    result = static_collect()
    result['observer'] = TOOL
    for role, p in result['roles'].items():
        p['pool_state'] = result['memory_contract']['roles'][role]['pool_state']
    return result


def valid_header(p, address):
    g = p['geometry']
    return isinstance(address, int) and address % 8 == 0 and g['pool_end'] <= address <= g['end'] - 8


def descriptor(p, entry):
    r = entry['registers']
    value = r['r1'] if entry['kind'] == 'allocate' else descriptor_for_flags(p['descriptor_base'], r['r1'])
    require(value in {v['base'] for v in p['descriptors']}, 'Unknown byte-heap descriptor')
    return value


def node(snapshot, address):
    matches = [n['words'] for n in snapshot['headers'] if n['address'] == address]
    require(len(matches) == 1, 'Required bounded header missing')
    return matches[0]


def check_snapshot(s, p, desc):
    require(s['descriptor'] == desc and len(s['descriptor_words']) == 7, 'Descriptor evidence differs')
    require(len(s['control']) == 2 and s['control'][1] == 0x800, 'Unexpected byte-heap page size')
    rows = s['headers']
    require(len(rows) <= 24 and [r['address'] for r in rows] == sorted({r['address'] for r in rows}),
            'Invalid bounded header set')
    for row in rows:
        require(valid_header(p, row['address']) and len(row['words']) == 2 and
                all(type(w) is int and 0 <= w < 2**32 for w in row['words']), 'Invalid heap node')
    require(all(type(w) is int and 0 <= w < 2**32 for w in s['descriptor_words'] + s['control']),
            'Invalid descriptor/control word')
    state = s['pool_state']
    g = p['geometry']
    require(len(state) == 4 and state[0] == g['count'] and 0 <= state[1] <= g['count'] and
            state[2:] == [g['start'], g['pool_end']], 'Lower pool geometry changed')


def check_pair(call, contract):
    e, ret = call['entry'], call['return_event']
    p = contract['roles'][e['role']]
    desc = descriptor(p, e)
    check_snapshot(e['heap'], p, desc)
    out = dict(call_id=call['id'], role=e['role'], kind=e['kind'], descriptor=desc,
               paired=ret is not None, isolated=not call['overlaps'])
    if ret is None:
        return out
    er, rr = e['registers'], ret['registers']
    require(all(er[n] == rr[n] for n in CALLEE_SAVED) and er['sp'] == rr['sp'], 'Saved registers/stack differ')
    require((er['cpsr'] & 0xDF) == (rr['cpsr'] & 0xDF), 'Mode/IRQ/FIQ state was not restored')
    check_snapshot(ret['heap'], p, desc)
    out['raw_return_r0'] = rr['r0']
    if e['kind'] == 'allocate':
        request = aligned_size(er['r0'])
        pointer = rr['r0']
        out.update(request_bytes=er['r0'], aligned_bytes=request, pointer=pointer, zero_return=pointer == 0)
        if not pointer:
            return out
        h = pointer - 8
        require(valid_header(p, h), 'Allocation outside observed native data bounds')
        nxt, previous = node(ret['heap'], h)
        require(previous & 1 and valid_header(p, nxt) and pointer + request <= nxt and
                nxt - pointer - request < 24, 'Allocation used flag/capacity differs')
        require(node(ret['heap'], nxt)[1] & ~7 == h, 'Next block does not point back')
        if not previous & 2:
            prev = previous & ~7
            require(valid_header(p, prev) and node(ret['heap'], prev)[0] == h, 'Previous block differs')
        out['capacity_bytes'] = nxt - pointer
        out['allocation_header_verified'] = True
    else:
        pointer = er['r0']
        h = pointer - 8
        require(valid_header(p, h), 'Release pointer outside observed data bounds')
        nxt, previous = node(e['heap'], h)
        require(previous & 1 and valid_header(p, nxt), 'Release entry is not a bounded used block')
        out.update(pointer=pointer, release_return_is_status=False, release_evidence='unresolved')
        if call['overlaps']:
            out['release_evidence'] = 'interleaved-not-attributed'
            return out
        owner = h
        if not previous & 2:
            prev = previous & ~7
            require(valid_header(p, prev), 'Invalid previous release node')
            if not node(e['heap'], prev)[1] & 1:
                owner = prev
        target_next = nxt
        nwords = node(e['heap'], nxt)
        if nwords[1] & 5 == 0:
            target_next = nwords[0]
        out.update(candidate_free_header=owner, candidate_next=target_next)
        after = node(ret['heap'], owner)
        free_delta = ret['heap']['pool_state'][1] - e['heap']['pool_state'][1]
        out['lower_free_count_delta'] = free_delta
        if (not after[1] & 1 and after[0] == target_next and valid_header(p, target_next) and
                node(ret['heap'], target_next)[1] & ~7 == owner and free_delta == 0):
            out['release_evidence'] = 'merged-free-header'
            out['merged_previous'] = owner != h
            out['merged_next'] = target_next != nxt
        # A pool return can invalidate byte headers. Preserve it as unresolved, not a false failure/success.
    return out


def analyze_events(events, contract):
    ledger = Ledger()
    for sequence, e in enumerate(events):
        require(e['sequence'] == sequence, 'Event sequence differs')
        check_cpu(e, contract)
        p, r = contract['roles'][e['role']], e['registers']
        if e['kind'] in ('allocate', 'release'):
            require(r['pc'] == p[e['kind']], 'Wrong original byte-heap entry')
            ledger.enter(e)
        else:
            require(e['kind'] == 'return', 'Unexpected event kind')
            found = ledger.match(e)
            require(found is not None, 'Unpaired original heap return')
            ledger.returned(found, e)
    results = [check_pair(c, contract) for c in ledger.calls]
    return ledger, results


def summarize(calls, results):
    summary = {role: dict(allocations=0, zero_returns=0, release_returns=0, release_metadata=0,
                         release_unresolved=0, exact_pointer_reuses=0, matched_prior_allocations=0,
                         merges_previous=0, merges_next=0, overlaps=0) for role in ('master', 'slave')}
    by_id = {r['call_id']: r for r in results}
    live, freed = {}, {}
    # Return order, not entry order, determines observed pointer lifetime.
    for call in sorted((c for c in calls if c['return_event'] is not None),
                       key=lambda c: c['return_event']['sequence']):
        r = by_id[call['id']]
        s = summary[r['role']]
        s['overlaps'] += not r['isolated']
        key = (r['role'], r['descriptor'], r.get('pointer'))
        if r['kind'] == 'allocate':
            s['allocations'] += 1
            s['zero_returns'] += r['zero_return']
            if not r['zero_return']:
                if key in freed:
                    s['exact_pointer_reuses'] += 1
                    freed.pop(key)
                live[key] = call['id']
        else:
            s['release_returns'] += 1
            s['matched_prior_allocations'] += key in live
            if r['release_evidence'] == 'merged-free-header':
                s['release_metadata'] += 1
                s['merges_previous'] += r['merged_previous']
                s['merges_next'] += r['merged_next']
                if key in live:
                    freed[key] = live[key]
            else:
                s['release_unresolved'] += 1
            live.pop(key, None)
    return summary
