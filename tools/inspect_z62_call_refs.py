"""Inspect bounded original Thumb BL/B.W candidates for a known target.

Each aligned halfword is considered independently, so embedded data may also
decode as a branch. These are candidate anchors, not proven callers or a full
control-flow analysis. No guest execution or firmware modification occurs.
"""
import argparse
import json
from pathlib import Path
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from capstone.arm import ARM_OP_IMM

from export_z62_body_contract import original


def find_refs(data, base, start, end, target):
    if (not isinstance(data, bytes) or
            any(type(v) is not int for v in (base, start, end, target)) or
            not 0 <= base <= start < end <= base + len(data) <= 0x100000000 or
            start % 2 or end % 2 or target % 2 or not 0 <= target <= 0xFFFFFFFE or
            end - start > 0x400000):
        raise ValueError('Require an aligned in-image scan of at most 4 MiB and an even target')
    decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    decoder.detail = True
    references = []
    for pc in range(start, end - 3, 2):
        offset = pc - base
        first, second = struct.unpack_from('<HH', data, offset)
        if first & 0xF800 != 0xF000 or second & 0xD000 not in (0x9000, 0xD000):
            continue
        for insn in decoder.disasm(data[offset:offset + 4], pc, count=1):
            if (insn.size == 4 and insn.mnemonic in ('bl', 'b.w') and len(insn.operands) == 1 and
                    insn.operands[0].type == ARM_OP_IMM and
                    insn.operands[0].imm & 0xFFFFFFFF == target):
                references.append({'pc': hex(pc), 'bytes': insn.bytes.hex(),
                    'kind': 'call' if insn.mnemonic == 'bl' else 'tail-branch',
                    'instruction': insn.mnemonic + ' ' + insn.op_str})
                if len(references) > 2000:
                    raise ValueError('Too many branch candidates; narrow the scan')
    return references


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=lambda value: int(value, 16))
    parser.add_argument('--start', required=True, type=lambda value: int(value, 16))
    parser.add_argument('--end', required=True, type=lambda value: int(value, 16))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    image, identity = original('master')
    result = {'schema': 1, 'target': hex(args.target), 'start': hex(args.start), 'end': hex(args.end),
              'input_sha256': identity,
              'candidate_references': find_refs(image, 0x10020000, args.start, args.end, args.target),
              'complete_xref_analysis': False, 'data_may_decode_as_code': True,
              'runtime_consumer_verified': False, 'firmware_modified': False}
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))
