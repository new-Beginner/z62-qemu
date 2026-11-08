"""Replay-only tests for r13 limited baseline; never launch QEMU."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fenestra/z62'))
import observe_model_baseline as baseline


class ModelBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = json.loads((baseline.ROOT / 'analysis/fenestra-z62-model-r13/baseline-1.json').read_text())

    def test_original_saved_baseline_replays(self):
        result = baseline.check_record(self.saved)
        self.assertTrue(result['limited_original_baseline_verified'])
        self.assertFalse(result['full_fenestra_port_verified'])
        self.assertFalse(result['old_r69_reproduced'])

    def test_targeted_record_errors_rejected(self):
        mutations = [
            lambda r: r.update(qemu_sha256='0' * 64),
            lambda r: r.update(build_manifest_sha256='0' * 64),
            lambda r: r.update(completed=False),
            lambda r: r.update(camera_accessed=True),
            lambda r: r['sources'].update({'fenestra/z62/observe_model_baseline.py': '0' * 64}),
            lambda r: r['samples'].pop(),
            lambda r: r['samples'][0]['cpus'][0]['code'].update(matches_original=False),
            lambda r: r['samples'][0]['cpus'][0]['system'].update(DFSR_S=1),
            lambda r: r['samples'][0]['cpus'][0].update(image_head='00'),
            lambda r: r['samples'][1]['cpus'][0].update(model_clock_ticks=0),
            lambda r: r['rsp_commands'].append('M10020000,4:00000000'),
            lambda r: r['command'].__setitem__(13, 'user'),
            lambda r: r['quit_receipt'].update(acknowledged=False),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                record = copy.deepcopy(self.saved)
                mutate(record)
                with self.assertRaises(ValueError):
                    baseline.check_record(record)

    def test_invalid_run_bounds_rejected_before_launch(self):
        for windows in ([], [0, 1], [2, 31], [1, 2, 3]):
            with self.subTest(windows=windows), self.assertRaises(ValueError):
                baseline.run(baseline.ROOT / 'analysis/fenestra-z62-model-r13/uncreated-invalid.json', windows)


if __name__ == '__main__':
    unittest.main()
