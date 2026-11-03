"""Bounded original control-store and caller observations; no unwinder fiction."""
from functools import lru_cache
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from capstone.arm import ARM_OP_IMM, ARM_OP_REG
from export_z62_body_contract import original

VERSION = '2026.11.03-statistics-control-r61'
BASE = 0x10020000
POINTS = {0x1020a832: 'input-stop-store', 0x1020aafe: 'input-start-store',
          0x1020ae72: 'statistics-stop-entry', 0x1020ae3e: 'statistics-start-entry',
          0x1020ae4a: 'statistics-enable-entry', 0x1020ae66: 'statistics-disable-entry',
          0x1020ae7c: 'statistics-command-stop-entry'}


@lru_cache(maxsize=1)
def image():
    return original('master')


def read(memory, address, size):
    raw = memory.read(address, size)
    if type(raw) is not bytes or len(raw) != size:
        raise ValueError('Short control provenance read at '+hex(address))
    return raw


def caller(memory, registers, firmware):
    link = registers['lr']; ret = link & ~1
    row = {'link': hex(link), 'known': False, 'callsite': None, 'target': None,
           'kind': None, 'is_complete_call_chain': False}
    if not (link & 1 and BASE+4 <= ret <= BASE+len(firmware)):
        return {**row, 'reason': 'link-outside-original-thumb-image'}
    try:
        raw = read(memory, ret-4, 4)
        if raw != firmware[ret-4-BASE:ret-BASE]:
            return {**row, 'reason': 'caller-instruction-differs', 'raw': raw.hex()}
        decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB); decoder.detail = True
        for data, address in ((raw, ret-4), (raw[2:], ret-2)):
            instruction = next(iter(decoder.disasm(data, address, count=1)), None)
            if not instruction or instruction.address+instruction.size != ret:
                continue
            if instruction.mnemonic == 'bl' and len(instruction.operands) == 1 and instruction.operands[0].type == ARM_OP_IMM:
                return {**row, 'known': True, 'callsite': hex(address), 'target': hex(instruction.operands[0].imm & 0xffffffff),
                        'kind': 'thumb-bl', 'raw': instruction.bytes.hex(), 'original_bytes_match': True}
            if instruction.mnemonic == 'blx' and len(instruction.operands) == 1 and instruction.operands[0].type == ARM_OP_REG:
                name = instruction.reg_name(instruction.operands[0].reg)
                return {**row, 'known': True, 'callsite': hex(address), 'kind': 'thumb-blx-register',
                        'raw': instruction.bytes.hex(), 'register': name,
                        'current_register_value': registers.get(name), 'value_at_call_proven': False,
                        'original_bytes_match': True}
        return {**row, 'reason': 'link-not-following-supported-original-call', 'raw': raw.hex()}
    except (OSError, RuntimeError, ValueError) as exc:
        return {**row, 'reason': 'caller-read-failed', 'error': {'type': type(exc).__name__, 'message': str(exc)}}


def capture(memory, registers):
    pc = registers.get('pc')
    if type(pc) is not int or pc not in POINTS:
        raise ValueError('Not a scoped original input control point')
    for name in ('r0', 'r1', 'r2', 'r3', 'sp', 'lr'):
        if type(registers.get(name)) is not int or not 0 <= registers[name] <= 0xffffffff:
            raise ValueError('Invalid control register: '+name)
    firmware, digest = image()
    raw = read(memory, pc, 4)
    matches = raw == firmware[pc-BASE:pc-BASE+4]
    result = {'schema': 1, 'version': VERSION, 'point': POINTS[pc], 'pc': hex(pc),
              'input_sha256': digest, 'source_instruction_4': raw.hex(),
              'source_instruction_matches': matches, 'read_only': True,
              'registers': {name: registers[name] for name in ('r0', 'r1', 'r2', 'r3', 'sp', 'lr')},
              'write_candidate': None, 'caller': {'known': False},
              'stack': {'captured': False, 'raw': None}, 'complete_call_chain_verified': False}
    if not matches:
        return result
    if pc in (0x1020a832, 0x1020aafe):
        base_matches = registers['r0'] == 0x20068000
        result['write_candidate'] = {'base_matches': base_matches,
            'address': hex(registers['r0']+(12 if pc == 0x1020a832 else 8)) if base_matches else None,
            'value': registers['r1'], 'instruction_not_yet_executed': True}
    result['caller'] = caller(memory, registers, firmware)
    sp = registers['sp']
    stack = {'address': hex(sp), 'bytes': 64, 'captured': False, 'raw': None,
             'is_unwound_call_stack': False}
    if not (sp % 4 == 0 and 0xc0000000 <= sp <= 0xe0000000-64):
        stack['reason'] = 'outside-bounded-stack-ram'
    else:
        try:
            data = read(memory, sp, 64)
            stack.update(captured=True, raw=data.hex(), words=list(struct.unpack('<16I', data)))
        except (OSError, RuntimeError, ValueError) as exc:
            stack['error'] = {'type': type(exc).__name__, 'message': str(exc)}
    result['stack'] = stack
    return result
