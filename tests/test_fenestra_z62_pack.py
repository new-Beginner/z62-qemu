"""Pure format fixtures; these tests cannot certify camera installation."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fenestra_z62_pack', ROOT / 'fenestra/z62/pack.py')
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)


class FenestraZ62PackTests(unittest.TestCase):
    def package(self, bits=32):
        return pack.make_package(bytes(64), 2 if bits == 32 else 0, 32, 17, bits=bits)

    def test_header_identity_body_digest_and_legacy_entry(self):
        raw = self.package()
        self.assertEqual(raw[:8], b'FENESTRA')
        self.assertEqual(struct.unpack_from('<4I', raw, 8), (1, 128, 1, pack.ISA32))
        self.assertEqual(raw[24:56], pack.FIRMWARE)
        self.assertEqual(raw[56:88], pack.digest(raw[128:]))
        self.assertEqual(struct.unpack_from('<5I', raw, 88), (len(raw),8192,2,2,2))
        self.assertEqual(raw[108:128], bytes(20))

    def test_adjacent_32bit_relocations_preserve_thumb_state(self):
        raw = self.package()
        self.assertEqual(struct.unpack_from('<IIQ', raw, 176), (4096,pack.RELOC32,32))
        self.assertEqual(struct.unpack_from('<IIQ', raw, 192), (4100,pack.RELOC32,17))
        self.assertEqual(raw[-8:], bytes(8))

    def test_default_64bit_format_has_distinct_identity_and_width(self):
        raw = self.package(64)
        self.assertEqual(struct.unpack_from('<I', raw, 20)[0], 1)
        self.assertEqual(struct.unpack_from('<IIQ', raw, 192), (4104,1,17))
        self.assertEqual(raw[-16:], bytes(16))

    def test_reject_ambiguous_architecture_entry_and_targets(self):
        for args in ((b'',2,0,1,32),(bytes(64),1,32,17,32),(bytes(64),64,32,17,32),
                     (bytes(64),2,64,17,32),(bytes(64),2,32,16,32),(bytes(64),0,32,17,16)):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    pack.make_package(*args[:4], bits=args[4])

    def test_negative_cases_pin_outer_digest_except_explicit_untrusted_case(self):
        rows = pack.cases(self.package())
        self.assertEqual(len(rows), 29)
        self.assertEqual(len({row[0] for row in rows}),len(rows))
        for name,data,sha,expected in rows:
            with self.subTest(name=name):
                self.assertEqual(len(sha),32)
                self.assertEqual(expected==0,name=='valid')
                if name!='untrusted-package-digest':
                    self.assertEqual(sha,pack.digest(data))


if __name__ == '__main__':
    unittest.main()
