"""Read-only Thumb literal-pool candidates in bounded original master ranges.

Linear disassembly may miss functions or decode embedded data as instructions.
The results are candidate anchors for instruction/runtime verification only.
"""
import argparse
import hashlib
import json
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from capstone.arm import ARM_OP_MEM, ARM_REG_PC

ROOT = Path(__file__).resolve().parents[1]
BASE = 0x10020000
SHA = 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4'


def inspect(value, start, end):
    data = (ROOT / 'artifacts/z62-reference-1.70/master.bin').read_bytes()
    if hashlib.sha256(data).hexdigest() != SHA:
        raise ValueError('Original master identity mismatch')
    if not (0 <= value <= 0xFFFFFFFF and BASE <= start < end <= BASE + len(data) and
            start % 2 == 0 and end-start <= 0x400000):
        raise ValueError('Require aligned bounded master scan of at most 4 MiB')
    needle = value.to_bytes(4, 'little')
    pools = set()
    offset = data.find(needle)
    while offset >= 0:
        if offset % 4 == 0:
            pools.add(BASE + offset)
        offset = data.find(needle, offset+1)
    decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    decoder.detail = True
    decoder.skipdata = True
    refs = []
    for insn in decoder.disasm(data[start-BASE:end-BASE], start):
        if not insn.id or not insn.mnemonic.startswith('ldr'):
            continue
        for op in insn.operands:
            if op.type == ARM_OP_MEM and op.mem.base == ARM_REG_PC:
                pool = ((insn.address+4) & ~3) + op.mem.disp
                if pool in pools:
                    refs.append({'pc': hex(insn.address), 'pool': hex(pool), 'bytes': insn.bytes.hex(),
                                 'instruction': insn.mnemonic + ' ' + insn.op_str})
    return {'value': hex(value), 'start': hex(start), 'end': hex(end), 'input_sha256': SHA,
            'candidate_pools': [hex(p) for p in sorted(pools)], 'candidate_references': refs,
            'complete_xref_analysis': False, 'firmware_modified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('value', type=lambda x: int(x, 16))
    parser.add_argument('--start', required=True, type=lambda x: int(x, 16))
    parser.add_argument('--end', required=True, type=lambda x: int(x, 16))
    args = parser.parse_args()
    print(json.dumps(inspect(args.value, args.start, args.end), indent=2))
