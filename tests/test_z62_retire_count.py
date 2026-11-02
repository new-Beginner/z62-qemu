"""A queue-count write is a full native u32, not a byte or a guessed event."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class RetireCountTests(unittest.TestCase):
    def api(self):
        try:
            import trace_z62_retire_count as api
        except ImportError as exc:
            self.fail('Native retirement-count observation is missing: ' + str(exc))
        return api

    def hit(self, before='51000000', after='50000000'):
        return {'sequence': 4, 'thread': '01', 'state': {'virtual_seconds': 31.2},
                'watch_address': '0xc237a8bc', 'watch_before': before, 'watch_after': after,
                'watch_instruction_4': 'a0607047',
                'registers': {'pc': '0x1034c0a0', 'sp': '0xc53357a0', 'lr': '0x103cee01'}}

    def test_each_native_u32_delta_keeps_the_cpu_and_instruction_identity(self):
        extract = self.api().extract_writes
        other = dict(self.hit(), watch_address='0xc1864cd0')
        rows = extract({'hits': [other, self.hit(), self.hit('02010000', '03010000')]})
        self.assertEqual([(x['before_count'], x['after_count'], x['delta']) for x in rows],
                         [(81, 80, -1), (258, 259, 1)])
        self.assertEqual(rows[0]['pc'], '0x1034c0a0')
        self.assertEqual(rows[0]['thread'], '01')

    def test_missing_or_partial_write_values_are_not_zero_retirements(self):
        extract = self.api().extract_writes
        for after in [None, '', '5000', 'xyz']:
            with self.subTest(after=after), self.assertRaises(ValueError):
                extract({'hits': [self.hit(after=after)]})

    def test_stack_context_is_read_only_ram_and_must_be_complete(self):
        capture = self.api().stack_context
        class Memory:
            def read(self, address, size):
                if address != 0xC53357A0 or size != 96:
                    raise AssertionError('Unexpected stack read')
                return b'\x12' * 96
        row = capture(Memory(), {'sp': 0xC53357A0})
        self.assertTrue(row['available'])
        self.assertEqual(len(bytes.fromhex(row['raw_60'])), 96)
        self.assertFalse(capture(Memory(), {'sp': 0x20068000})['available'])
        class Short(Memory):
            def read(self, address, size):
                return b'\0' * 4
        with self.assertRaises(ValueError):
            capture(Short(), {'sp': 0xC53357A0})


if __name__ == '__main__':
    unittest.main()
