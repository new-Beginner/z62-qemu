"""Find checked Thumb branches without promoting data candidates to callers."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class ThumbCallReferenceTests(unittest.TestCase):
    def api(self):
        try:
            from inspect_z62_call_refs import find_refs
        except ImportError as exc:
            self.fail('The bounded original-code branch inspector is missing: ' + str(exc))
        return find_refs

    def test_original_bl_reaches_the_independently_decoded_scalar_helper(self):
        # 1038DA2C: BL 103C9276, checked against the original instruction listing.
        refs = self.api()(bytes.fromhex('3bf023fc'), 0x1038DA2C,
                          0x1038DA2C, 0x1038DA30, 0x103C9276)
        self.assertEqual([row['pc'] for row in refs], ['0x1038da2c'])
        self.assertEqual(refs[0]['kind'], 'call')
        self.assertEqual(self.api()(bytes.fromhex('3bf023fc'), 0x1038DA2C,
                                   0x1038DA2C, 0x1038DA30, 0x103C9278), [])

    def test_tail_branch_is_found_without_requiring_a_call_instruction(self):
        # Original 1038DA90 tail B.W to the same helper.
        refs = self.api()(bytes.fromhex('3bf0f1bb'), 0x1038DA90,
                          0x1038DA90, 0x1038DA94, 0x103C9276)
        self.assertEqual([(row['pc'], row['kind']) for row in refs],
                         [('0x1038da90', 'tail-branch')])

    def test_scan_window_excludes_other_and_incomplete_instructions(self):
        data = bytes.fromhex('00bf3bf023fc00bf')
        self.assertEqual(self.api()(data, 0x1038DA2A, 0x1038DA2A,
                                   0x1038DA2E, 0x103C9276), [])
        refs = self.api()(data, 0x1038DA2A, 0x1038DA2C, 0x1038DA32, 0x103C9276)
        self.assertEqual([row['pc'] for row in refs], ['0x1038da2c'])

    def test_invalid_or_unbounded_ranges_are_rejected(self):
        find_refs = self.api()
        for start, end in ((1, 4), (0, 8), (2, 2), (0, 0x400002)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                find_refs(b'\0' * 4, 0, start, end, 0x103C9276)


if __name__ == '__main__':
    unittest.main()
