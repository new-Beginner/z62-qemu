# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import trace_z62_mode_producer as producer


class ModeProducerTests(unittest.TestCase):
    def test_adapters_restore_on_failure(self):
        trace = producer.trace
        before = (trace.R1_SHA, dict(trace.POINTS), trace.stage,
                  trace.install_native_process_adapter, subprocess.Popen, list(sys.path),
                  dict(trace.EXTRA_WORDS), set(trace.NOTIFICATIONS))
        with tempfile.TemporaryDirectory() as folder:
            args = SimpleNamespace(output=Path(folder)/'new', qemu=Path('fixture.exe'), async_path=True)
            def fail(args):
                self.assertEqual(trace.R1_SHA, 'fixture-sha')
                self.assertEqual(trace.POINTS[0x10241E88], 'mode-callback-target')
                self.assertIn(0x10241CDE, trace.POINTS)
                self.assertIn(0xC18A790C, trace.EXTRA_WORDS)
                sys.path.insert(0, 'fixture-added-path')
                raise RuntimeError('injected')
            with patch.object(producer.host, 'verify_build', return_value={'binary_sha256': 'fixture-sha'}), \
                    patch.object(trace, 'run', side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, 'injected'):
                    producer.run(args)
        after = (trace.R1_SHA, dict(trace.POINTS), trace.stage,
                 trace.install_native_process_adapter, subprocess.Popen, list(sys.path),
                 dict(trace.EXTRA_WORDS), set(trace.NOTIFICATIONS))
        self.assertEqual(before, after)

    def test_existing_evidence_is_not_touched(self):
        with tempfile.TemporaryDirectory() as folder:
            args = SimpleNamespace(output=Path(folder), qemu=Path('fixture.exe'))
            with patch.object(producer.host, 'verify_build') as verify:
                with self.assertRaises(FileExistsError):
                    producer.run(args)
                verify.assert_not_called()


if __name__ == '__main__':
    unittest.main()
