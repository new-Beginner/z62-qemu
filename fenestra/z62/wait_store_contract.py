"""Original Z62 single-STR/object-head contract, not a full wait/task ABI."""
from collections import Counter
import struct
from startup_contract import BASE, require, read_inputs
from pool_calls import REGISTERS
from task_context import bounded_ram, words
from task_wait_provenance import collect as wait_collect

TOOL = 'fenestra-z62-wait-store/0.1.0'


def collect():
    original = wait_collect()
    images = read_inputs()
    roles = {}
    for role, p in original['roles'].items():
        checkpoint = p['registrar'] + 0x20
        require(images[role][checkpoint - BASE:checkpoint - BASE + 4] == bytes.fromhex('340081e5'),
                'Original STR handle anchor differs')
        calls = {}
        for kind in ('bit_test', 'linked_receive'):
            rows = [i for i in p[kind]['instructions'] if i['mnemonic'] == 'bl' and
                    i['operands'] == f'#{p["wrapper"]:#x}']
            require(len(rows) == 1, 'Ambiguous original wait call')
            calls[kind] = rows[0]['address'] + 4
        roles[role] = dict(p, role=role, checkpoint=checkpoint, call_returns=calls,
                           object_bytes=24, tcb_bytes=256, call_stack_bytes=64)
    return dict(schema=1, tool=TOOL, inputs=original['inputs'], roles=roles,
        imports_equivalent=original['imports_equivalent'],
        wait_registration_completed=False, task_identity_verified=False,
        complete_task_abi_verified=False, hardware_root_cause_identified=False)


def check_event(row, p):
    r = row['registers']
    require(row['role'] == p['role'] and row['thread'] in
            {'master': ('01', '02'), 'slave': ('03', '04')}[row['role']], 'CPU/engine mismatch')
    local = (int(row['thread'], 16) - 1) % 2
    require(set(r) == set(REGISTERS) and r['pc'] == p['checkpoint'] and r['cpsr'] & 0x3F == 0x13,
            'Not original ARM SVC STR checkpoint')
    require(r['r5'] == local and r['r6'] == p['context']['current'] and
            len(row['current']) == 2 and row['current'][local] == r['r1'], 'Original current TCB relation differs')
    for address, size in ((r['r1'], 256), (r['r4'], 24), (r['sp'], 80)):
        require(bounded_ram(p['context'], address, size), 'Read outside bounded original heap')
    before = bytes.fromhex(row['tcb_before'])
    after = bytes.fromhex(row['tcb_after'])
    block = words(before, 256)
    obj = words(bytes.fromhex(row['object_before']), 24)
    require(row['object_after'] == row['object_before'], 'Original STR changed object header')
    require(r['r0'] == obj[2], 'Object+8/loaded handle mismatch')
    expected = bytearray(before)
    struct.pack_into('<I', expected, 0x34, r['r0'])
    require(after == expected, 'STR changed bytes beyond original TCB+34 word')
    require(row['after_registers'] == dict(r, pc=r['pc'] + 4), 'Single STR changed general registers')
    require(row['call_stack_address'] == r['sp'] + 16 == block[0x40 // 4],
            'Original caller SP/current stack relation differs')
    stack = words(bytes.fromhex(row['call_stack']), 64)
    kind = next((k for k, a in p['call_returns'].items() if a == r['lr']), 'unmapped')
    args = {}
    if kind == 'bit_test':
        require(block[0x44 // 4] == r['r7'] and block[0x4C // 4] == r['r10'],
                'Original bit-test saved arguments differ')
        # Registrar pushes r4/r5/r6/lr, so caller r6 is at current SP+8.
        # The explicit 64-byte caller stack is NOT that saved register bank.
        args = dict(mask=block[0x44 // 4], options=block[0x48 // 4], output_pointer=block[0x4C // 4])
    elif kind == 'linked_receive':
        require(block[0x44 // 4] == r['r11'] == stack[3] and r['r0'] == stack[2],
                'Original receive saved arguments differ')
        args = dict(output_pointer=block[0x44 // 4])
    return dict(kind=kind, object_address=r['r4'], control_block=r['r1'], object_handle=obj[2],
        object_raw_words=obj, arguments=args, timeout_raw_word=r['r2'],
        tcb_raw_word08=block[2], tcb_raw_word14=block[5],
        handle_word_changed=block[0x34 // 4] != obj[2], original_str_relation_verified=True,
        wait_registration_completed=False, task_identity_verified=False,
        complete_task_abi_verified=False, hardware_root_cause_identified=False)


def summarize(events, contract):
    output = {}
    for role, p in contract['roles'].items():
        rows = [check_event(e, p) for e in events if e['role'] == role]
        counts = Counter((r['kind'], r['object_handle'], r['object_address']) for r in rows)
        output[role] = dict(events=len(rows), changed_words=sum(r['handle_word_changed'] for r in rows),
            observed_control_block_addresses=len({r['control_block'] for r in rows}),
            observed_object_addresses=len({r['object_address'] for r in rows}),
            objects=[dict(kind=k[0], handle=k[1], address=k[2], samples=n) for k, n in sorted(counts.items())],
            wait_registration_completed=False, task_identity_verified=False,
            complete_task_abi_verified=False, hardware_root_cause_identified=False)
    return output
