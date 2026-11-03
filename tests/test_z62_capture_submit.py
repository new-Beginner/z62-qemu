"""Keep r77 execution probes inside one original capture call frame."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import probe_z62_capture_submit as probe


class FakeRemote:
    def __init__(self):
        self.commands = []
        self.points = set()

    def breakpoint(self, pc, add=True):
        if add:
            self.points.add(pc)
        else:
            self.points.remove(pc)

    def command(self, command):
        self.commands.append(command)
        if command == 's':
            return 'T05thread:1;'
        if command.startswith('Hc'):
            return 'OK'
        raise AssertionError('Unexpected command: '+command)


class CaptureSubmitTests(unittest.TestCase):
    def test_enqueue_point_and_return_only_armed_for_original_capture_frame(self):
        remote = FakeRemote(); tracer = probe.ScopedTracer(remote); tracer.initialize()
        self.assertEqual(remote.points, {0x10325186, 0x10320018})
        reg = {'r1': 0x103EAE81, 'sp': 0xC2001000}
        self.assertEqual(tracer.transition(0x10325186, reg, '1'), ('open', True))
        self.assertIn(0x1031627E, remote.points)
        self.assertIn(0x103EC564, remote.points)
        self.assertEqual(tracer.transition(0x1031627E, {'sp': 0xC2000F00}, '2'), (None, False))
        self.assertEqual(tracer.transition(0x1031627E, {'sp': 0xC2000F00}, '1'), (None, True))
        self.assertEqual(tracer.transition(0x103EC564, reg, '1'), ('close', True))
        self.assertNotIn(0x1031627E, remote.points)
        self.assertNotIn(0x103EC564, remote.points)
        tracer.cleanup()
        self.assertFalse(remote.points)

    def test_step_selects_stopped_cpu_and_does_not_write_memory_or_registers(self):
        remote = FakeRemote(); tracer = probe.ScopedTracer(remote); tracer.initialize()
        tracer.step(0x10325186, '1')
        self.assertEqual(remote.commands, ['Hc1', 's', 'Hc-1'])
        self.assertIn(0x10325186, remote.points)

    def test_invalid_queue_snapshot_does_not_read_arbitrary_storage(self):
        class Remote:
            def read(self, address, size):
                if address != probe.QUEUE or size != 24:
                    raise AssertionError('Reader escaped invalid queue header')
                return struct.pack('<6I', 0, 92, 60, 60, 0, 0)
        with self.assertRaises(ValueError):
            probe.stopped_snapshot(Remote())


if __name__ == '__main__':
    unittest.main()
