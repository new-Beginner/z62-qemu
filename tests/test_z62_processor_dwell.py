"""A long observation must remain a finite, bounded experiment."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class ProcessorDwellTests(unittest.TestCase):
    def test_nonfinite_or_unbounded_guest_limits_are_rejected(self):
        try:
            from trace_z62_processor_drain_dwell import validate_duration
        except ImportError as exc:
            self.fail('Bounded long-observation duration validation is missing: ' + str(exc))
        self.assertEqual(validate_duration(150), 150.0)
        for value in [True, None, '150', float('nan'), float('inf'), 55, 181]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_duration(value)


if __name__ == '__main__':
    unittest.main()
