"""Host debugger ownership checks must reject another or exited process."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))


class HostCaptureGuardTests(unittest.TestCase):
    def api(self):
        try:
            import z62_host_timeout_capture as module
        except ImportError as exc:
            self.fail('Owned host-timeout capture is missing: '+str(exc))
        return module

    def test_mismatched_owner_pid_rejected_before_any_debugger_launch(self):
        process = type('Process', (), {'pid': 123, 'args': ['qemu-system-arm.exe'], 'poll': lambda self: None})()
        with self.assertRaisesRegex(ValueError, 'owner'):
            self.api().guard_owner(process, 456, Path('qemu-system-arm.exe'), 'unused')

    def test_exited_owner_rejected_before_any_debugger_launch(self):
        process = type('Process', (), {'pid': 123, 'args': ['qemu-system-arm.exe'], 'poll': lambda self: 0})()
        with self.assertRaisesRegex(ValueError, 'exited'):
            self.api().guard_owner(process, 123, Path('qemu-system-arm.exe'), 'unused')
