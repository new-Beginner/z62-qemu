"""Fresh control probes keep waits scoped and reject incomplete hardware reads."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import probe_z62_prepare_control as probe
from test_z62_capture_submit import FakeRemote


class PrepareControlTests(unittest.TestCase):
    def test_only_target_packet_arms_ready_wait(self):
        remote = FakeRemote(); tracer = probe.ControlTracer(remote); tracer.initialize()
        self.assertEqual(remote.points, {0x10315624})
        tracer.transition(0x10315624, {'r1': 0x10320019, 'sp': 0xC2001000}, '1')
        self.assertNotIn(0x10238804, remote.points)
        tracer.transition(0x10315624, {'r1': 0x10322449, 'sp': 0xC2001000}, '1')
        self.assertIn(0x10238804, remote.points)
        tracer.transition(0x10315626, {'sp': 0xC2001000}, '1')
        self.assertEqual(remote.points, {0x10315624})
        tracer.cleanup()

    def test_short_status_read_is_unknown_not_zero(self):
        class Remote:
            def read(self, address, size): return b'\0\0'
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            probe.words(Remote(), (0x20068210,))


if __name__ == '__main__':
    unittest.main()
