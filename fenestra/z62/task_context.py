"""Z62 stock context-save anchors; not a public RTOS/task ABI."""
from collections import Counter
import struct

from startup_contract import ROOT, BASE, PROFILES, read_inputs, require, sha, instructions
from memory_contract import collect as memory_collect
from observe_boot_wait import scheduler_points

TOOL = 'fenestra-z62-task-context/0.1.0'


def profile(image, role, geometry):
    require(len(image) == PROFILES[role]['size'] and sha(image) == PROFILES[role]['sha256'],
            'Requires original C1.70 member')
    p = scheduler_points(image, role)
    p['checkpoint'] = p['loop'] - 0x1C
    at = p['checkpoint'] - BASE
    require(image[at - 16:at + 4] == bytes.fromhex('dc409fe50e4184e0008094e5bcd088e5c8d09fe5'),
            'Context-save/store-SP anchor changed')
    require(image[p['loop'] - BASE + 0x3C:p['loop'] - BASE + 0x40] == bytes.fromhex('bcd098e5'),
            'Context-restore/load-SP anchor changed')
    p.update(geometry=geometry, saved_sp_offset=0xBC, restore_branch_word_offset=0x24,
             tcb_bytes=256, frame_bytes=96,
             save_instructions=instructions(image, p['checkpoint'] - 0x3C, 0x50, False),
             restore_instructions=instructions(image, p['loop'] + 0x68, 0x4C, False))
    return p


def collect():
    images, memory = read_inputs(), memory_collect()
    return dict(schema=1, tool=TOOL, inputs=PROFILES,
                imports_equivalent='Raw ARM/Thumb: original MPIDR/literal current-slot load, STR SP at TCB+BC, original matching LDR SP and restore sequence; task ABI NOT established.',
                roles={r: profile(d, r, memory['roles'][r]['geometry']) for r, d in images.items()})


def bounded_ram(p, address, size):
    g = p['geometry']
    return (type(address) is int and type(size) is int and 0 < size <= 4096 and
            address % 4 == 0 and g['start'] <= address and address + size <= g['end'])


def words(raw, expected):
    require(len(raw) == expected and expected % 4 == 0, 'Truncated bounded context')
    return list(struct.unpack('<' + 'I' * (expected // 4), raw))


def check_event(row, p):
    r = row['registers']
    require(row['thread'] in {'master': ('01', '02'), 'slave': ('03', '04')}.get(row['role'], ()),
            'CPU is outside the original engine role')
    local = (int(row['thread'], 16) - 1) % 2
    require(row['role'] in ('master', 'slave') and r['pc'] == p['checkpoint'], 'Wrong checkpoint')
    require(r['cpsr'] & 0x3F == 0x13 and r['lr'] == local, 'Not original ARM SVC context-save CPU')
    require(r['r4'] == p['current'] + 4 * local, 'Current CPU-slot address differs')
    pointer = r['r8']
    require(bounded_ram(p, pointer, p['tcb_bytes']), 'Control block outside original heap bounds')
    require(row['current'][local] == pointer and len(row['current']) == 2, 'Current slot/control-block mismatch')
    block = words(bytes.fromhex(row['tcb']), p['tcb_bytes'])
    frame = words(bytes.fromhex(row['frame']), p['frame_bytes'])
    require(block[0xBC // 4] == r['sp'] and row['frame_address'] == r['sp'], 'Saved SP/current SP mismatch')
    require(bounded_ram(p, r['sp'], p['frame_bytes']), 'Frame outside original heap bounds')
    # Preserve branch-specific raw frames. Only the non-special restore path
    # statically pops CPSR at +64 and PC at +72; this does not identify a task id.
    result = dict(control_block=pointer, restore_branch_word=block[0x24 // 4],
                  saved_call_lr=frame[15], resume_pc_candidate=None, resume_cpsr_candidate=None,
                  waiting_object_identified=False, task_identity_verified=False)
    if block[0x24 // 4] != 1:
        result.update(resume_pc_candidate=frame[18], resume_cpsr_candidate=frame[16])
    return result


def summarize(events, contract):
    output = {}
    for role, p in contract['roles'].items():
        rows = [check_event(e, p) for e in events if e['role'] == role]
        counts = Counter(r['resume_pc_candidate'] for r in rows if r['resume_pc_candidate'] is not None)
        output[role] = dict(events=len(rows), observed_control_blocks=len({r['control_block'] for r in rows}),
            resume_pc_candidates=[dict(address=a, count=n) for a, n in counts.most_common()],
            waiting_objects_identified=False, task_names_mapped=False, complete_task_abi_verified=False)
    return output
