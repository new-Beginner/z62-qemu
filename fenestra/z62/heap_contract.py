"""Stock byte-heap layer above the 2 KiB pool; not a public malloc/free ABI."""
import argparse
import json
from pathlib import Path

from memory_contract import collect as memory_collect, literal, arm_call, list_groups
from startup_contract import ROOT, BASE, read_inputs, u32, require, instructions, sha

ENTRIES = {
    'master': dict(allocate_flags=0x10108870, release=0x10108908,
                   allocate_default=0x10108A98, release_default=0x10108B44),
    'slave': dict(allocate_flags=0x1003A244, release=0x1003A2DC,
                  allocate_default=0x1003A46C, release_default=0x1003A518),
}


def arm_branch(data, address):
    word = u32(data, address - BASE)
    require(word >> 24 == 0xEA, 'Expected unconditional original ARM tail branch')
    delta = word & 0xFFFFFF
    if delta & 0x800000:
        delta -= 0x1000000
    return address + 8 + 4 * delta


def aligned_size(size):
    # Reject wraparound for receipt interpretation, not a claim about firmware failure behavior.
    require(isinstance(size, int) and 0 <= size <= 0xFFFFFFF8, 'Unverified wrapping byte request')
    return (max(size, 16) + 7) & ~7


def descriptor_for_flags(base, flags):
    require(0 <= base <= 2**32 - 112 and 0 <= flags < 2**32, 'Invalid descriptor arguments')
    return (base + (56 if flags & 0x300 == 0x300 else 0) + (28 if not flags & 0x10 else 0)) & ~7


def profile(data, role, memory):
    e = ENTRIES[role]
    core = arm_branch(data, e['allocate_flags'] + 0x30)
    require(arm_branch(data, e['allocate_default'] + 0x3C) == core, 'Default allocator uses a different core')
    require(arm_branch(data, e['release_default'] + 0xC) == e['release'], 'Default release uses a different core')
    require(data[core - BASE:core - BASE + 16] == bytes.fromhex('f0472de9100050e30160a0e11000a033'),
            'Original byte allocator prologue differs')
    require(data[e['release'] - BASE:e['release'] - BASE + 16] == bytes.fromhex('70402de90040a0e1000300e30100d0e1'),
            'Original byte release prologue differs')
    base = literal(data, e['allocate_flags'] + 4, 3)
    require(literal(data, e['release'] + 0x10, 2) == base and list_groups(base) == memory['list_groups'],
            'Byte heap descriptor base differs from initialized lists')
    require(literal(data, core + 0x28, 8) == memory['heap_control'], 'Byte heap control differs')
    low = memory['static_pool_api_candidates']
    require(arm_call(data, core + 0xF8) == low['allocate_entry'], 'Byte allocator does not call original block pool')
    require(arm_call(data, e['release'] + 0x158) == low['release_entry'], 'Byte release does not call original block pool')
    default = literal(data, e['allocate_default'], 1)
    require(literal(data, e['release_default'], 1) == default, 'Default flags source differs')
    save, restore = arm_call(data, core + 0x18), arm_call(data, core + 0x1EC)
    require(data[save - BASE:save - BASE + 16] == bytes.fromhex('00000fe180c080e30cf021e11eff2fe1'),
            'Original IRQ save sequence differs')
    require(data[restore - BASE:restore - BASE + 24] == bytes.fromhex(
        '803000e200000fe18020c0e3032082e102f021e11eff2fe1'), 'Original IRQ restore sequence differs')
    require(arm_branch(data, e['release'] + 0x18C) == restore, 'Release no longer tail-restores IRQ state')
    return dict(role=role, allocate=core, release=e['release'], wrappers=e,
                instruction_state='ARM', allocate_r0='byte count; minimum16, round up8 in original code',
                allocate_r1='initialized descriptor pointer, NOT public flags',
                release_r0='byte-heap user pointer; no null/invalid-input contract verified',
                release_r1='flag selector used to choose descriptor',
                release_return='raw original IRQ-helper result; NOT a zero-success status ABI',
                descriptor_base=base, descriptors=memory['list_groups'], default_flags_word=default,
                heap_control=memory['heap_control'], geometry=memory['geometry'],
                copied_table=memory['copied_table'], vector=memory['vector'],
                low_allocate=low['allocate_entry'], low_release=low['release_entry'],
                irq_save=save, irq_restore=restore,
                synchronization_calls=dict(enter=arm_call(data, core + 0x24), leave=arm_call(data, core + 0x1E4)),
                code=dict(allocate=instructions(data, core, 0x1F8, False),
                          release=instructions(data, e['release'], 0x190, False),
                          flags_wrapper=instructions(data, e['allocate_flags'], 0x34, False),
                          default_allocate=instructions(data, e['allocate_default'], 0x40, False),
                          default_release=instructions(data, e['release_default'], 0x10, False),
                          irq_save=instructions(data, save, 16, False),
                          irq_restore=instructions(data, restore, 24, False)),
                complete_abi_verified=False, failure_inputs_verified=False,
                synchronization_semantics_verified=False, allocation_lifetime_verified=False,
                firmware_integrated=False, flash_safety_verified=False)


def collect():
    memory, images = memory_collect(), read_inputs()
    return dict(schema=1, tool='fenestra-z62-byte-heap/0.1', memory_contract=memory,
                sources={'fenestra/z62/heap_contract.py': sha(Path(__file__).read_bytes())},
                roles={r: profile(data, r, memory['roles'][r]) for r, data in images.items()},
                imports_equivalent='Raw ARM/Thumb direct calls, initialized descriptors, original tail branches and IRQ helpers',
                camera_accessed=False, firmware_integrated=False, flash_safety_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.resolve()
    require(output.is_relative_to(ROOT / 'analysis') and not output.exists(), 'Use new analysis output')
    result = collect()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps({r: {k: hex(p[k]) for k in ('allocate', 'release', 'descriptor_base', 'irq_save', 'irq_restore')}
                      for r, p in result['roles'].items()}, indent=2))
