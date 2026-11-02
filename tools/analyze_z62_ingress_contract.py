#!/usr/bin/env python3
"""固定 C1.70 镜像的离线证据提取；不执行固件、不连接设备、不运行 QEMU。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from capstone.arm import ARM_OP_IMM, ARM_OP_MEM, ARM_REG_PC

BASE = 0x10020000
SHA256 = "bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4"
ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / "artifacts/z62-reference-1.70/master.bin"
OUT = ROOT / "analysis/z62-ingress-contract"
# Exact, half-open code windows. Literal pools deliberately excluded.
WINDOWS = [
    ("geometry_and_channels", 0x1020905A, 0x10209344),
    ("metadata_enable", 0x10209768, 0x10209796),
    ("geometry_wrappers", 0x1020C2C8, 0x1020C2F6),
    ("channel_wrappers", 0x1020C300, 0x1020C37E),
    ("runtime_submit_tail", 0x1023838C, 0x102383D4),
    ("geometry_callers", 0x10239654, 0x1023982C),
    ("stride_and_descriptor", 0x10239850, 0x1023990C),
    ("secondary_channel", 0x1023990C, 0x1023997C),
    ("selector_conversion", 0x1023C640, 0x1023C656),
    ("format_table_lookup", 0x102CF804, 0x102CF830),
    ("unaligned_le32", 0x103C82F6, 0x103C830C),
]
LITERALS = {
    0x10209348: 0x20069500,
    0x10209350: 0x20069A14,
    0x10209354: 0x20069814,
    0x10209358: 0x20069B80,
    0x102097AC: 0x20069F00,
}
# Key instruction assertions supplement (not replace) fixed-image verification.
ANCHORS = {
    0x102090BC: ("str", "r0, [r1]"),
    0x102090CC: ("str", "r0, [r1]"),
    0x102090E2: ("str", "r0, [r1]"),
    0x102090FA: ("str", "r0, [r1]"),
    0x10209160: ("bfi", "r0, r1, #0, #0xa"),
    0x10209164: ("bfi", "r0, r2, #0x10, #0xa"),
    0x10209230: ("ldrh", "r1, [r2, #0xa]"),
    0x10209268: ("ldrh", "r0, [r2, #0xa]"),
    0x1020926A: ("str", "r0, [r4]"),
    0x102092C8: ("str", "r1, [r0]"),
    0x102092D4: ("str", "r1, [r0, #0xc]"),
    0x10239760: ("bl", "#0x1020c340"),
    0x1023976C: ("bl", "#0x1020c358"),
    0x10239778: ("bl", "#0x1020c358"),
    0x1023989A: ("add.w", "r3, r3, r3, lsl #1"),
    0x1023989E: ("add.w", "r2, r8, r3, lsr #1"),
    0x102398A2: ("and.w", "r2, r2, sb"),
    0x102398A6: ("strh", "r2, [r6, #0x1a]"),
}


def verify_image(data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256:
        raise ValueError(f"firmware SHA256 mismatch: {digest}")
    return digest


def decoder():
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    md.detail = True
    return md


def u32(data: bytes, address: int) -> int:
    offset = address - BASE
    if not 0 <= offset <= len(data) - 4:
        raise ValueError(f"address outside image: {address:#x}")
    return struct.unpack_from("<I", data, offset)[0]


def literal_reference(insn, data):
    """Only actual PC-relative LDR consumers, never raw integer matches."""
    if insn.mnemonic not in ("ldr", "ldr.w"):
        return None
    for operand in insn.operands:
        if operand.type == ARM_OP_MEM and operand.mem.base == ARM_REG_PC:
            address = ((insn.address + 4) & ~3) + operand.mem.disp
            return {"instruction": insn.address, "pool": address,
                    "value": u32(data, address)}
    return None


def decode_window(data, start, end):
    instructions = list(decoder().disasm(data[start - BASE:end - BASE], start))
    if not instructions or instructions[-1].address + instructions[-1].size != end:
        raise ValueError(f"incomplete bounded decode: {start:#x}..{end:#x}")
    return instructions


def verify_anchors(data):
    for address, value in LITERALS.items():
        if u32(data, address) != value:
            raise ValueError(f"literal mismatch at {address:#x}")
    for address, expected in ANCHORS.items():
        insn = next(decoder().disasm(data[address - BASE:address - BASE + 4], address))
        if (insn.mnemonic, insn.op_str) != expected:
            raise ValueError(f"instruction mismatch at {address:#x}: {insn}")


def rotate_halves(value):
    return ((value << 16) | (value >> 16)) & 0xFFFFFFFF


def geometry_registers(descriptor: bytes):
    """Host-side transcription of 102090A0, not firmware emulation.

    Unknown field semantics deliberately retain byte-offset names.
    """
    if len(descriptor) != 0x1C:
        raise ValueError("geometry descriptor must be 0x1c bytes")
    w = lambda offset: struct.unpack_from("<I", descriptor, offset)[0]
    h = lambda offset: struct.unpack_from("<H", descriptor, offset)[0]
    return {
        0x20069514: ((descriptor[4] << 3) | (w(0) << 2) |
                     descriptor[5] | (w(0x10) << 5)) & 0xFFFFFFFF,
        0x20069518: rotate_halves(w(6)),
        0x2006951C: rotate_halves(w(0xA)),
        0x20069520: descriptor[0xE],
        0x20069524: rotate_halves(w(0x18)),
        0x20069528: h(0x16) | (descriptor[0x14] << 16),
    }


def stride_from_fields(width: int, selector: int, override=None):
    """10239868..A6/D2: arithmetic only; no claim about pixel packing.

    The actual mask is 0xfff0 (not an unbounded align-up operation).
    selector=2 may bypass calculation with an upstream uint16 field.
    """
    if not 0 <= width <= 0xFFFF:
        raise ValueError("width field must be uint16")
    if selector == 2 and override is not None:
        if not 0 <= override <= 0xFFFF:
            raise ValueError("override must be uint16")
        return override
    amounts = {0: width * 2, 1: (width * 7) >> 2, 2: (width * 3) >> 1}
    if selector not in amounts:
        raise ValueError("no proven stride assignment for selector")
    return (amounts[selector] + 15) & 0xFFF0


def channel_registers(channel, bank, addresses, stride):
    """102091FE/10209296 valid-domain mapping, not a DMA permission check."""
    if channel not in range(4) or bank not in (0, 1):
        raise ValueError("only documented channel/bank domain supported")
    if len(addresses) != 4 or not all(0 <= a <= 0xFFFFFFFF for a in addresses):
        raise ValueError("four uint32 address words required")
    if not 0 <= stride <= 0xFFFF:
        raise ValueError("stride descriptor field must be uint16")
    base = 0x20069800 + channel * 0x100
    return {base + 8: stride, **{base + 0x50 + bank * 0x10 + slot * 4: value
                               for slot, value in enumerate(addresses)}}


def extract(data):
    verify_image(data)
    verify_anchors(data)
    listing = []
    references = []
    branches = []
    for name, start, end in WINDOWS:
        listing.append(f"\n## {name}: [{start:08x}, {end:08x})")
        for insn in decode_window(data, start, end):
            ref = literal_reference(insn, data)
            suffix = ""
            if ref:
                references.append(ref)
                suffix = f" ; literal[{ref['pool']:08x}]={ref['value']:08x}"
            listing.append(f"{insn.address:08x}: {insn.bytes.hex():10s} "
                           f"{insn.mnemonic:8s} {insn.op_str}{suffix}")
            if insn.mnemonic in ("bl", "b.w") and insn.operands[0].type == ARM_OP_IMM:
                branches.append({"instruction": insn.address,
                                 "target": insn.operands[0].imm,
                                 "mnemonic": insn.mnemonic})
    # Raw occurrences are explicitly only candidates. Some are instruction
    # bytes (STR r5,[sp]; MOVS r0,#6), not literal pools or MMIO references.
    needle = struct.pack("<I", 0x20069500)
    candidates = []
    offset = data.find(needle)
    while offset != -1:
        candidates.append(BASE + offset)
        offset = data.find(needle, offset + 1)
    evidence = {
        "image": "artifacts/z62-reference-1.70/master.bin", "sha256": SHA256,
        "base": BASE, "image_bytes": len(data), "firmware_executed": False,
        "windows": [{"name": n, "start": a, "end_exclusive": b}
                    for n, a, b in WINDOWS],
        "literal_consumers": references, "bounded_direct_branches": branches,
        "integer_occurrences_NOT_xrefs": candidates,
        "observation_from_delegation_NOT_measured_here": {
            "20069514": "00000006", "20069518": "05ea0000",
            "2006951c": "03ee0000", "2006952c": "00000002",
            "20069530": "00200040", "20069f00": "00000011"},
        "conditional_arithmetic": {"width_field": 1514, "height_field": 1006,
                                   "selector_2_without_override_stride": 2272},
        "packing": "unknown", "dma_safety": "not established",
        "runtime_stride_addresses_and_consumption": "not observed by this task",
    }
    return evidence, "\n".join(listing) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=IMAGE)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    # Restrict output to the task's authorized evidence subtree.
    if not args.out.resolve().is_relative_to(OUT.resolve()):
        parser.error("--out must be inside analysis/z62-ingress-contract")
    evidence, listing = extract(args.image.read_bytes())
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.out / "disassembly.txt").write_text(listing, encoding="utf-8")
    print(f"SHA256 verified; {len(WINDOWS)} bounded windows; "
          f"{len(evidence['literal_consumers'])} actual LDR consumers; output={args.out}")


if __name__ == "__main__":
    main()
