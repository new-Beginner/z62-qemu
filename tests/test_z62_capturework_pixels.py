"""Actual native C packing checks; requires the workspace compiler, never skips."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import z62_capturework_native as native


class CaptureworkPixelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=native.ascii_root(); base=root/'.runtime/tmp'; base.mkdir(parents=True,exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(prefix='capturework-native-',dir=base)
        cls.executable,cls.environment=native.compile_probe(Path(cls.temp.name))

    @classmethod
    def tearDownClass(cls):
        if not Path(cls.temp.name).resolve().is_relative_to(native.ROOT):
            raise ValueError('Refusing cleanup outside workspace')
        cls.temp.cleanup()

    def check(self,case): self.assertTrue(native.run(self.executable,self.environment,case)['completed'])
    def test_literal_raw12(self): self.check('raw12')
    def test_raw14_decoded_bits(self): self.check('raw14')
    def test_literal_raw16(self): self.check('raw16')
    def test_two_materialized_mono_stages(self): self.check('rational-mono')
    def test_cfa_phase_and_nonintegral_stage_composition(self): self.check('rational-cfa')
    def test_lookup_and_invalid_curve_no_write(self): self.check('lookup')
    def test_input_stride_and_output_guards(self): self.check('padding')
    def test_bounds_strides_unsupported_modes_and_overlap_no_write(self): self.check('rejects')


if __name__=='__main__': unittest.main()
