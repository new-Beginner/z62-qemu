"""Control provenance must retain unknown stack/caller data, not invent a chain."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))


class Memory:
    def __init__(self):
        self.image = (ROOT/'artifacts/z62-reference-1.70/master.bin').read_bytes()
        self.reads = []
        self.bad_stack = False

    def read(self, address, size):
        self.reads.append((address, size))
        if 0x10020000 <= address and address+size <= 0x10020000+len(self.image):
            return self.image[address-0x10020000:address-0x10020000+size]
        if address == 0xc2400000 and not self.bad_stack:
            return bytes(range(size))
        raise ValueError('Unmapped test memory')


class ControlSnapshotTests(unittest.TestCase):
    def api(self):
        try:
            import z62_statistics_control_snapshot as module
        except ImportError as exc:
            self.fail('Control caller observation is missing: '+str(exc))
        return module

    def regs(self, **changed):
        return dict(pc=0x1020a832, r0=0x20068000, r1=0x10, r2=0, r3=0,
                    sp=0xc2400000, lr=0x1020ae89, **changed)

    def test_actual_stop_store_and_direct_original_caller_are_both_checked(self):
        row = self.api().capture(Memory(), self.regs())
        self.assertTrue(row['source_instruction_matches'])
        self.assertEqual(row['write_candidate']['address'], '0x2006800c')
        self.assertEqual(row['write_candidate']['value'], 16)
        self.assertEqual(row['caller']['callsite'], '0x1020ae84')
        self.assertEqual(row['caller']['target'], '0x1020a830')
        self.assertEqual(row['caller']['kind'], 'thumb-bl')
        self.assertEqual(row['stack']['raw'], bytes(range(64)).hex())

    def test_failed_stack_read_is_unknown_but_does_not_discard_verified_store(self):
        memory = Memory(); memory.bad_stack = True
        row = self.api().capture(memory, self.regs())
        self.assertTrue(row['source_instruction_matches'])
        self.assertFalse(row['stack']['captured'])
        self.assertIsNone(row['stack']['raw'])
        self.assertTrue(row['stack']['error'])

    def test_mmio_stack_and_exception_link_are_never_followed_as_ram_or_code(self):
        memory = Memory(); regs = self.regs(); regs.update(sp=0xf8f01000, lr=0xfffffffd)
        row = self.api().capture(memory, regs)
        self.assertFalse(row['stack']['captured'])
        self.assertFalse(row['caller']['known'])
        self.assertEqual(memory.reads, [(0x1020a832, 4)])
