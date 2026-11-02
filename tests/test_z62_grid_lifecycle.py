from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))


class GridLifecycleTests(unittest.TestCase):
    def api(self):
        try:
            import trace_z62_grid_lifecycle as lifecycle
        except ImportError as exc:
            self.fail('Grid lifecycle acceptance is missing: ' + str(exc))
        return lifecycle

    def fixture(self):
        def sample(t, grid, preview):
            return {'virtual_seconds': t, 'known': True, 'index': 3,
                    'display_enabled': True, 'ready_join': 3, 'input_inhibit': 0,
                    'grid_groups': grid, 'preview_batches': preview}
        return [sample(8, 10, 10), sample(9, 11, 11),
                sample(24, 20, 30), sample(25, 21, 31)], \
               [{'level': 0, 'virtual_seconds': 10}, {'level': 1, 'virtual_seconds': 18}]

    def test_recovery_requires_original_ready_and_two_advancing_outputs(self):
        module = self.api()
        samples, events = self.fixture()
        result = module.assess(samples, events)
        self.assertTrue(result['initial_ready'])
        self.assertTrue(result['recovery_observed'])
        self.assertEqual(result['advancing_pair_seconds'], [24, 25])

    def test_static_screen_or_only_one_pipeline_cannot_pass(self):
        module = self.api()
        original, events = self.fixture()
        for field in ('grid_groups', 'preview_batches'):
            samples = deepcopy(original)
            samples[-1][field] = samples[-2][field]
            with self.subTest(field=field):
                self.assertFalse(module.assess(samples, events)['recovery_observed'])

    def test_unknown_late_state_and_early_screen_are_not_recovery(self):
        module = self.api()
        samples, events = self.fixture()
        for field, value in (('known', False), ('display_enabled', False),
                             ('ready_join', 1), ('input_inhibit', 1)):
            changed = deepcopy(samples)
            changed[-1][field] = value
            with self.subTest(field=field):
                self.assertFalse(module.assess(changed, events)['recovery_observed'])
        early = deepcopy(samples)
        early[-2]['virtual_seconds'], early[-1]['virtual_seconds'] = 19, 20
        self.assertFalse(module.assess(early, events)['recovery_observed'])

    def test_unverified_input_sequence_and_reversed_time_are_rejected(self):
        module = self.api()
        samples, events = self.fixture()
        self.assertFalse(module.assess(samples, events[:1])['recovery_observed'])
        samples[-1]['virtual_seconds'] = 23
        with self.assertRaises(ValueError):
            module.assess(samples, events)
