"""The menu-cycle CLI must not report success for a failed reopen."""
import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import probe_reference_menu_cycle as probe


class MenuCycleExitTests(unittest.TestCase):
    def invoke(self, record):
        with patch.object(sys, 'argv', ['probe', '--output', 'unused']), \
                patch.object(probe, 'run', return_value=record), \
                contextlib.redirect_stdout(io.StringIO()):
            try:
                probe.main()
            except SystemExit as exc:
                return exc.code
        return 0

    def test_complete_cycle_succeeds(self):
        self.assertEqual(self.invoke(dict(menu_ready=True, left_menu=True,
                                          reopened_menu=True)), 0)

    def test_each_failed_or_missing_stage_fails(self):
        for name in ('menu_ready', 'left_menu', 'reopened_menu'):
            for value in (False, None):
                with self.subTest(stage=name, value=value):
                    record = dict(menu_ready=True, left_menu=True, reopened_menu=True)
                    if value is None:
                        del record[name]
                    else:
                        record[name] = value
                    self.assertNotEqual(self.invoke(record), 0)

    def test_recorded_experiment_failure_is_not_success(self):
        self.assertNotEqual(self.invoke(dict(menu_ready=True, left_menu=True,
                                             reopened_menu=False)), 0)


if __name__ == '__main__':
    unittest.main()
