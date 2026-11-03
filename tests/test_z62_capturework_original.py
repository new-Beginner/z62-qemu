"""Original-window MAIN eligibility must not manufacture geometry or time."""
import importlib
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))


class OriginalMainTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('probe_z62_capturework_original'),'Original-window driver missing')
        return importlib.import_module('probe_z62_capturework_original')

    def test_supported_register_readback_keeps_actual_dimensions(self):
        self.assertEqual(self.module().main_geometry([1342<<16,2020<<16]),(2020,1342))

    def test_unqualified_dimensions_never_fall_back_to_r86_constants(self):
        for words in ([0,0],[1342<<16|1,2020<<16],[1342<<16,2019<<16],[4032<<16,6048<<16]):
            with self.subTest(words=words),self.assertRaises(ValueError): self.module().main_geometry(words)

    def test_hardware_clock_uses_full_counter_and_rejects_unknown_frequency(self):
        m=self.module()
        self.assertEqual(m.virtual_ns(0x1_00000001,1_000_000),4_294_967_297_000)
        for ticks,frequency in ((-1,1),(1,0),(True,1),(1,False)):
            with self.assertRaises(ValueError): m.virtual_ns(ticks,frequency)


if __name__=='__main__': unittest.main()
