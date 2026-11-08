"""Saved boot diagnostics replay; not physical camera acceptance tests."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'fenestra/z62'))
import observe_boot_wait as observer
import verify_boot_wait as verifier

NAMES = ('run-3-minimal-final.json', 'run-4-controller-final.json',
         'run-5-controller-link-final.json', 'run-6-minimal-long.json',
         'run-7-controller-link-long.json')


class BootWaitVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = [json.loads((ROOT / 'analysis/fenestra-z62-boot-r6' / n).read_text(encoding='utf-8'))
                       for n in NAMES]

    def test_saved_profile_records(self):
        for record in self.records:
            with self.subTest(profile=record['profile'], pid=record['owned_pid']):
                result = verifier.check_run(record)
                self.assertFalse(result['firmware_integrated'])
                self.assertFalse(result['waiting_task_objects_identified'])
                self.assertTrue(result['default_completion_logic_present'])
                self.assertEqual(result['samples'][-1]['idle_engine_cpus'], 4)

    def test_twelve_mutations_rejected(self):
        variants = verifier.mutations(self.records[0])
        self.assertEqual(len(variants), 12)
        for name, record in variants.items():
            with self.subTest(name=name), self.assertRaises((ValueError, KeyError, TypeError, IndexError)):
                verifier.check_run(record)

    def test_default_and_experimental_completions_are_distinct(self):
        for record in self.records:
            for name in verifier.EXPERIMENTAL:
                self.assertEqual(verifier.flags(record['model_tree'], name), ['false', 'false'])
            for name in verifier.DEFAULT_COMPLETIONS:
                self.assertEqual(verifier.flags(record['model_tree'], name), ['true', 'true'])
            self.assertFalse(record['default_model_completion_logic_disabled'])
            self.assertNotIn('completion_helpers_enabled', record)

    def test_initial_schema_cannot_be_promoted(self):
        record = json.loads((ROOT / 'analysis/fenestra-z62-boot-r6/run-1-minimal.json').read_text())
        self.assertNotEqual(record['tool'], observer.TOOL)
        with self.assertRaises(ValueError):
            verifier.check_run(record)


if __name__ == '__main__':
    unittest.main()
