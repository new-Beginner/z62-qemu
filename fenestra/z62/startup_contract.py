"""Read-only Z6II C1.70 startup contract. Not an installation/space allocator."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = 0x10020000
PROFILES = {
    'master': dict(size=38750138, sha256='bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4',
                   runtime=0x104393A4, scatter_count=20),
    'slave': dict(size=8832194, sha256='3fd8c2cbdf57fadb03f6d69b596b58a8703efdd61ae82572d5afeea0241a9ed5',
                  runtime=0x10167090, scatter_count=15),
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def u32(data, offset):
    require(0 <= offset <= len(data)-4, 'Word outside image')
    return struct.unpack_from('<I', data, offset)[0]


def arm_branch(data, offset):
    word = u32(data, offset)
    require(word >> 24 == 0xEA, 'Expected unconditional ARM B')
    imm = word & 0xFFFFFF
    if imm & 0x800000:
        imm -= 0x1000000
    return BASE + offset + 8 + 4*imm


def arm_literal(data, offset, register):
    word = u32(data, offset)
    require(word & 0xFF7FF000 == 0xE51F0000 | register << 12, 'Expected ARM literal LDR')
    delta = word & 0xFFF
    at = offset + 8 + (delta if word & 0x800000 else -delta)
    return u32(data, at)


def section(data, address):
    require(0 <= address < 2**32, 'Address outside ARM32')
    desc = u32(data, 0x10000 + (address >> 20)*4)
    require(desc & 3 == 2 and not desc & (1 << 18), 'Expected ordinary short section')
    return dict(virtual_address=address, descriptor=desc,
                physical_address=(desc & 0xFFF00000) | (address & 0xFFFFF),
                domain=(desc >> 5) & 15, ap_bits=((desc >> 10) & 3) | ((desc >> 13) & 4),
                xn=bool(desc & 16), pxn=bool(desc & 1), tex=(desc >> 12) & 7,
                cacheable=bool(desc & 8), bufferable=bool(desc & 4),
                shareable=bool(desc & (1 << 16)))


def scatter(data, start=0x14000, max_records=64):
    records = []
    for i in range(max_records + 1):
        at = start + 16*i
        require(0 <= at <= len(data)-18, 'Truncated scatter table')
        src, dst, size, handler = struct.unpack_from('<4I', data, at)
        if not any((src, dst, size, handler)):
            return records
        require(i < max_records, 'Unterminated scatter table')
        require(handler in (BASE+0x6C, BASE+0x88), 'Unknown scatter handler')
        require(size > 0 and size % 4 == dst % 4 == 0, 'Invalid scatter alignment')
        require(dst+size <= 2**32, 'Scatter destination overflow')
        kind = 'copy' if handler == BASE+0x6C else 'zero'
        if kind == 'copy':
            require(BASE <= src and src+size <= BASE+len(data)-2, 'Copy outside member payload')
        record = dict(table_offset=at, source=src, destination=dst, size=size,
                      handler=handler, kind=kind)
        if kind == 'copy':
            record['source_sha256'] = sha(data[src-BASE:src-BASE+size])
        records.append(record)
    raise ValueError('Unterminated scatter table')


def instructions(data, address, size, thumb):
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
    offset = address-BASE
    require(0 <= offset and offset+size <= len(data)-2, 'Code window outside payload')
    rows = list(Cs(CS_ARCH_ARM, CS_MODE_THUMB if thumb else CS_MODE_ARM).disasm(data[offset:offset+size], address))
    require(sum(i.size for i in rows) == size, 'Incomplete instruction window')
    return [dict(address=i.address, bytes=i.bytes.hex(), mnemonic=i.mnemonic, operands=i.op_str) for i in rows]


def analyze(data, role):
    p = PROFILES[role]
    require(len(data) == p['size'] and sha(data) == p['sha256'], 'Requires original Z62 C1.70 '+role)
    require(data[0x20:0x2C] == b'Ver.01.70.02', 'Version mismatch')
    require(arm_branch(data, 0) == BASE+0xBC88, 'Reset branch changed')
    require(arm_branch(data, 0xBF98) == p['runtime'], 'Runtime branch changed')
    require(data[p['runtime']-BASE:p['runtime']-BASE+8] == bytes.fromhex('01c08fe21cff2fe1'), 'ARM/Thumb veneer changed')
    ttbr = arm_literal(data, 0xBCF0, 0)
    require(ttbr == BASE+0x10000, 'Unexpected original TTBR base')
    records = scatter(data)
    require(len(records) == p['scatter_count'], 'Scatter count mismatch')
    # The Thumb dispatcher uses offsets relative to its literal pair at +0x64.
    table_start = BASE + 0x64 + u32(data, 0x64)
    table_end = BASE + 0x64 + u32(data, 0x68)
    require(table_start == BASE+0x14000 and table_end == table_start+len(records)*16, 'Dispatcher bounds mismatch')
    early = []
    for index, offset in enumerate((0xBE74, 0xBED0, 0xBF2C)):
        src = arm_literal(data, offset, 0)
        dst = arm_literal(data, offset+4, 1)
        size = arm_literal(data, offset+8, 2)
        require(src == records[index]['source'] and dst == records[index]['destination'], 'Inline/table address mismatch')
        require(size == (records[index]['size'] if index < 2 else 0), 'Unexpected inline length')
        early.append(dict(entry=BASE+offset, stop=BASE+offset+0x58, source=src,
                          destination=dst, size=size, rounded_size=(size+3)&~3,
                          source_sha256=sha(data[src-BASE:src-BASE+size])))
    vectors = arm_literal(data, 0xBD20, 0)
    stacks = [arm_literal(data, o, 13) for o in (0xBD38,0xBD48,0xBD58,0xBD68,0xBD78,0xBD88)]
    addresses = sorted({BASE, BASE+0xBC88, ttbr, vectors, p['runtime'], BASE+len(data)-3,
                        0x10000088, 0x13C00000, *(s-4 for s in stacks),
                        *(r['source'] for r in records if r['kind']=='copy'),
                        *(r['destination'] for r in records),
                        *(r['destination']+r['size']-1 for r in records)})
    windows = dict(reset=instructions(data, BASE, 4, False),
                   dispatcher=instructions(data, BASE+0x38, 0x2C, True),
                   copy_handler=instructions(data, BASE+0x6C, 0x1A, True),
                   zero_handler=instructions(data, BASE+0x88, 0x1C, True),
                   runtime_veneer=instructions(data, p['runtime'], 8, False),
                   runtime_calls=instructions(data, p['runtime']+8, 0x12, True),
                   kernel_entry=instructions(data, BASE+0xAC, 0x28, False))
    return dict(role=role, file_size=len(data), sha256=sha(data), base=BASE,
                member_payload_end_exclusive=BASE+len(data)-2, trailing_crc_bytes=2,
                imports_equivalent=dict(format='raw ARM/Thumb member; no ELF/PE import directory',
                    anchors=['original literal loads and direct branches', 'Thumb scatter dispatch through r3',
                             'original C runtime calls and ARM kernel entry'],
                    capability_absence_not_inferred=True),
                startup=dict(entry=BASE+0xBC88, ttbr0=ttbr, dacr=arm_literal(data,0xBCF8,0),
                             vbar=vectors, core0_stack_tops=dict(zip(('UND','ABT','FIQ','IRQ','SYS','SVC'),stacks)),
                             secondary_release_address=u32(data,0xC038),
                             secondary_release_value=u32(data,0xC03C),
                             early_copies=early, runtime_veneer=p['runtime'], runtime_thumb=p['runtime']+8,
                             kernel_entry=BASE+0xAC),
                scatter=dict(table_start=table_start, table_end_exclusive=table_end,
                             records=records, copy_bytes=sum(r['size'] for r in records if r['kind']=='copy'),
                             zero_bytes=sum(r['size'] for r in records if r['kind']=='zero'),
                             full_dispatch_execution_verified=False),
                sections=[section(data, a) for a in addresses], instruction_windows=windows,
                placement=dict(executable_space_reserved=False,
                    mapped_after_member_is_not_loaded_space=True,
                    zero_table_targets_are_owned_not_free=True,
                    runtime_allocator_and_lifetime_unverified=True,
                    earlier_camera_loader_not_executed=True),
                firmware_integrated=False, flash_safety_verified=False)


def read_inputs():
    return {role: (ROOT/'artifacts/z62-reference-1.70'/f'{role}.bin').read_bytes() for role in PROFILES}


def collect():
    import capstone
    return dict(schema=1, tool='fenestra-z62-startup-contract/0.1',
                sources={Path(__file__).relative_to(ROOT).as_posix():sha(Path(__file__).read_bytes())},
                tools=dict(python=sys.version, capstone=capstone.__version__),
                roles={role:analyze(data, role) for role,data in read_inputs().items()},
                camera_accessed=False, firmware_integrated=False, flash_safety_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT/'analysis') and not output.exists(), 'Use a new analysis output')
    result = collect()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2); f.write('\n')
    print(json.dumps({role:dict(scatter_records=len(r['scatter']['records']), copy_bytes=r['scatter']['copy_bytes'],
                               runtime_thumb=hex(r['startup']['runtime_thumb'])) for role,r in result['roles'].items()},indent=2))
