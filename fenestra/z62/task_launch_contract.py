"""r15: local stock index3 input/publish/return/first-entry contract."""
from collections import Counter
import struct
from startup_contract import ROOT, BASE, PROFILES, require, sha, read_inputs, instructions
from pool_calls import REGISTERS
from task_entry_contract import collect as entry_contract, check_prepared, check_pair as entry_pair
from task_context import bounded_ram, words
from task_create_contract import bounded_read

TOOL = 'fenestra-z62-task-launch/0.1.1'
LIMITATIONS = ('complete_task_abi_verified', 'business_task_completed', 'task_lifetime_verified',
               'startup_failure_matrix_verified', 'system_mode_verified', 'stable_task_identity_verified',
               'descriptor_ownership_verified', 'r10_pending_explained')
SAVED = tuple('r'+str(i) for i in range(4, 13)) + ('lr',)


def collect():
    c = entry_contract()
    for role, image in read_inputs().items():
        p = c['roles'][role]; a = p['start']; off = a-BASE
        p['returns'] = [a+n for n in (0x5C, 0x9C, 0x26C)]
        require(all(image[x-BASE:x-BASE+4] == bytes.fromhex('f09fbde8') for x in p['returns']),
                'Original return POP changed')
        p['instructions'] = instructions(image, a, 0x270, False)
        table_literal = a+0xA0+8+(struct.unpack_from('<I', image, off+0xA0)[0] & 0xFFF)
        p['table_global'] = struct.unpack_from('<I', image, table_literal-BASE)[0]
        count_literal = a+0x28+8+(struct.unpack_from('<I', image, off+0x28)[0] & 0xFFF)
        require(struct.unpack_from('<I', image, count_literal-BASE)[0] == p['table_global']+4,
                'Original table/count relation changed')
        needle = struct.pack('<I', a); ref = image.find(needle)
        require(ref >= 12 and image.find(needle, ref+1) < 0, 'Ambiguous original service table')
        p['service_table_address'] = BASE+ref-12
        p['service_table_words'] = list(struct.unpack_from('<11I', image, ref-12))
        p['literal_bytes'] = image[off+0x270:off+0x2C4].hex()
    c.update(tool=TOOL, imports_equivalent='Raw ARM/Thumb; original kernel service table index3, handle-table literal, frame stores and original PUSH/three POP exits. No conventional import table.',
             **{n: False for n in LIMITATIONS})
    return c


def bounded_stack(p, address, size):
    """Native RAM address guard, not heap allocation or stack ownership proof."""
    return bounded_read(p, address, size) and address >= 0xC0000000


def check_input(e, p):
    r = e['registers']; base, count = e['table_words']; index = r['r0'] & 0xFFFF
    require(r['pc'] == p['start'] and r['cpsr'] & 0x3F == 0x13, 'Outside natural SVC input sample')
    require(0 < index <= count <= 65535, 'Outside natural valid table index sample')
    tb = base+(index-1)*216
    require(bounded_ram(p['context'], tb, 216) and e['tcb_address'] == tb,
            'Original index-to-TCB relation differs')
    w = words(bytes.fromhex(e['tcb']), 216)
    require(w[2] == r['r0'] and 0 < r['r0'] < 0x80000000, 'Original input handle/TCB differs')
    require(bounded_stack(p, r['sp']-40, 40) and
            BASE+16 <= (r['lr'] & ~1) < BASE+PROFILES[p['role']]['size']-18,
            'Unbounded original input stack/return')
    return dict(tcb_address=tb, handle=r['r0'], argument=r['r1'], configured_entry=w[5])


def check_push(e):
    b, a = e['registers'], e['after_registers']
    require(a == dict(b, sp=b['sp']-40, pc=b['pc']+4), 'Original PUSH register effects differ')
    require(e['after_stack'] == struct.pack('<10I', *[b[n] for n in SAVED]).hex(),
            'Original PUSH stack writes differ')


def check_pop(e, original):
    b, a, start = e['registers'], e['after_registers'], original['registers']
    saved = list(struct.unpack('<10I', bytes.fromhex(e['saved_stack'])))
    require(b['sp'] == start['sp']-40 and saved == [start[n] for n in SAVED],
            'Original return saved registers/LR differ')
    target = saved[-1]
    expected = dict(b, **dict(zip(SAVED[:-1], saved[:-1])), sp=start['sp'],
                    pc=(target & (~1 if target & 1 else ~3)),
                    cpsr=(b['cpsr'] & ~32) | (32 if target & 1 else 0))
    require(a == expected, 'Original POP restoration/interworking differs')


def stack_matches(pairs, e):
    out = [s for s in pairs if s['role'] == e['role'] and s['returned'] is None and
           s['input']['registers']['sp'] == e['registers']['sp']+40]
    require(len(out) <= 1, 'Ambiguous live invocation stack')
    return out


def classify(pairs, e, p):
    pc = e['registers']['pc']
    if pc == p['start']:
        require(not any(s['role'] == e['role'] and s['returned'] is None and
                        s['input']['registers']['sp'] == e['registers']['sp'] for s in pairs),
                'Overlapping live invocation stack')
        return 'input', len(pairs)
    if pc == p['checkpoint'] or pc in p['returns']:
        matched = stack_matches(pairs, e)
        require(len(matched) == 1, 'Unmatched original publish/return')
        s = matched[0]
        phase = 'prepared' if pc == p['checkpoint'] else 'returned'
        require(s[phase] is None, 'Duplicate original API phase')
        return phase, s['sequence']
    matched = [s for s in pairs if s['role'] == e['role'] and s['prepared'] is not None and
               s['entered'] is None and s['prepared']['tcb_address'] == e['current'][e['local_cpu']] and
               words(bytes.fromhex(s['prepared']['frame']), 76)[18] == pc]
    require(len(matched) <= 1, 'Ambiguous natural first entry')
    return ('entered', matched[0]['sequence']) if matched else ('unmatched-entry', None)


def ingest(pairs, e, p):
    phase, pi = classify(pairs, e, p)
    require((e['phase'], e['pair_index']) == (phase, pi), 'Phase/pair differs')
    if phase == 'input':
        check_input(e, p); check_push(e)
        pairs.append(dict(sequence=pi, role=e['role'], input=e, prepared=None, returned=None, entered=None))
    elif phase != 'unmatched-entry':
        s = pairs[pi]
        if phase == 'prepared':
            a = check_prepared(e, p); i = check_input(s['input'], p)
            require(e['tcb_address'] == i['tcb_address'] and a['native_handle_word08'] == i['handle'] and
                    a['expected_arguments'][0] == i['argument'] and
                    a['configured_entry'] == i['configured_entry'] and
                    e['saved_stack'] == s['input']['after_stack'], 'Same-call input/publish relation differs')
            require(e['after_registers'] == dict(e['registers'], pc=p['checkpoint']+4, r0=e['registers']['r4']),
                    'Original publish MOV differs')
        elif phase == 'returned':
            require(s['prepared'] is not None and e['registers']['r0'] == 0 and
                    e['registers']['pc'] == p['returns'][-1], 'Outside natural successful return sample')
            check_pop(e, s['input'])
        else:
            entry_pair(dict(role=s['role'], prepared=s['prepared'], entered=e), p)
        s[phase] = e
    return phase, pi


def complete(s):
    return all(s[n] is not None for n in ('prepared', 'returned', 'entered'))


def ready(pairs, maximum):
    return len(pairs) >= maximum and {s['role'] for s in pairs} == {'master', 'slave'} and all(map(complete, pairs))


def summarize(pairs):
    out = {}
    for role in ('master', 'slave'):
        rows = [s for s in pairs if s['role'] == role]
        require(rows and all(map(complete, rows)), 'Incomplete engine call chains')
        out[role] = dict(calls=len(rows), returned_zero=len(rows),
            entry_before_return=sum(s['entered']['sequence'] < s['returned']['sequence'] for s in rows),
            return_before_entry=sum(s['returned']['sequence'] < s['entered']['sequence'] for s in rows),
            caller_return_pcs=[dict(address=a, samples=n) for a,n in sorted(Counter(s['returned']['after_registers']['pc'] for s in rows).items())],
            nonzero_argument=sum(s['input']['registers']['r1'] != 0 for s in rows))
    return out
