"""Preparation timing is scoped by the actual work ID and original clock."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import probe_z62_prepare_packet as probe
from test_z62_capture_submit import FakeRemote


class PreparePacketTests(unittest.TestCase):
    def test_unrelated_work_does_not_arm_high_volume_inner_waits(self):
        remote = FakeRemote(); tracer = probe.PrepareTracer(remote); tracer.initialize()
        self.assertEqual(remote.points, {0x10315624})
        tracer.transition(0x10315624, {'r1': 0x10320019, 'sp': 0xC2001000}, '1')
        self.assertEqual(remote.points, {0x10315624})
        tracer.transition(0x10315624, {'r1': 0x10322449, 'sp': 0xC2001000}, '1')
        self.assertIn(0x1023382C, remote.points)
        tracer.transition(0x10315626, {'sp': 0xC2001000}, '1')
        self.assertEqual(remote.points, {0x10315624})
        tracer.cleanup()

    def test_clock_uses_full_counter_and_frequency_without_host_time(self):
        class Remote:
            def read(self, address, size):
                self.assertion = address == 0x04266008 and size == 12
                return struct.pack('<3I', 7, 1, 1000000)
        remote = Remote()
        self.assertEqual(probe.clock(remote), ((1 << 32)+7)*1000)
        self.assertTrue(remote.assertion)


if __name__ == '__main__':
    unittest.main()
