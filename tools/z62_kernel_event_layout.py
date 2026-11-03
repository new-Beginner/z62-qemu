"""Original-C1.70 event CB layout derived from actual ARM load/store operands."""
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
from probe_z62_capture_submit import MASTER_SHA
from record_z62_action_evidence import require
import hashlib

OBJECT = 0xC188808C
BASE = 0x10020000
ARM = {
    0x1011113C: ('ldr', 'r1, [r1, #4]'),
    0x10111140: ('add', 'r0, r1, r0, lsl #5'),
    0x10111144: ('sub', 'r4, r0, #0x20'),
    0x10111198: ('ldr', 'r1, [r4, #8]'),
    0x101111BC: ('ldr', 'r0, [r4, #0x14]'),
    0x101111C0: ('orr', 'r0, r0, r6'),
    0x101111C4: ('str', 'r0, [r4, #0x14]'),
    0x10111314: ('mov', 'r0, r7'),
    0x10111608: ('ldr', 'r3, [r4, #0x14]'),
    0x10111628: ('bics', 'r2, r7, r3'),
}


def contract(image):
    require(hashlib.sha256(image).hexdigest() == MASTER_SHA, 'Original CRC-bearing master required')
    arm = Cs(CS_ARCH_ARM, CS_MODE_ARM); thumb = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    anchors = []
    for pc, expected in {**ARM, 0x1035D446: ('ldr', 'r0, [r0]'),
                         0x1035D44A: ('movs', 'r2, #0'),
                         0x1035D44C: ('blx', '#0x10104a14')}.items():
        raw = image[pc-BASE:pc-BASE+4]
        insn = next((thumb if pc >= 0x10300000 else arm).disasm(raw, pc))
        require((insn.mnemonic, insn.op_str) == expected, 'Kernel layout instruction differs: '+hex(pc))
        anchors.append({'pc': hex(pc), 'bytes': insn.bytes.hex(), 'mnemonic': insn.mnemonic,
                        'operands': insn.op_str, 'mode': 'Thumb' if pc >= 0x10300000 else 'ARM'})
    pc = 0x10111104
    insn = next(arm.disasm(image[pc-BASE:pc-BASE+4], pc))
    require((insn.mnemonic, insn.op_str) == ('ldr', 'r1, [pc, #-0x418]'), 'Kernel global literal load differs')
    literal = pc+8-0x418
    global_address = struct.unpack_from('<I', image, literal-BASE)[0]
    require(0xC0000000 <= global_address <= 0xDFFFFFF8 and global_address % 4 == 0,
            'Event table global is outside original RAM')
    push = struct.unpack_from('<I', image, 0x101110EC-BASE)[0]
    require((push & 0xffff).bit_count() == 10 and next(arm.disasm(push.to_bytes(4,'little'),0x101110EC)).mnemonic == 'push',
            'Kernel setter stack frame differs')
    return {'master_sha256': MASTER_SHA, 'object': OBJECT, 'global_address': global_address,
            'global_literal': literal, 'stride': 32, 'id_offset': 8, 'attribute_offset': 16,
            'pattern_offset': 20, 'setter_stack_bytes': 40, 'anchors': anchors}


def read_words(remote, address, count):
    data = remote.read(address, count*4)
    require(len(data) == count*4, 'Incomplete original kernel structure read')
    return list(struct.unpack('<'+'I'*count, data))


def resolve(remote, layout):
    identifier = read_words(remote, layout['object'], 1)[0]
    index = identifier & 0xffff
    maximum, table = read_words(remote, layout['global_address'], 2)
    require(1 <= index <= maximum <= 65535 and ((identifier >> 24) & 15) == 1,
            'Opaque event identifier does not satisfy the original bounded ID checks')
    size = maximum*layout['stride']
    require(table % 4 == 0 and 0xC0000000 <= table <= 0xE0000000-size,
            'Original event CB table is outside bounded RAM')
    address = table+(index-1)*layout['stride']
    values = read_words(remote, address, 8)
    require(values[layout['id_offset']//4] == identifier, 'Resolved event CB identifier differs')
    return {'object': hex(layout['object']), 'identifier': hex(identifier), 'maximum': maximum,
        'table': hex(table), 'control_block': hex(address), 'raw_words': values,
        'attribute': hex(values[layout['attribute_offset']//4]),
        'pattern_address': hex(address+layout['pattern_offset']),
        'pattern': hex(values[layout['pattern_offset']//4]), 'read_only': True}
