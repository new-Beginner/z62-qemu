"""Guest-clock queue tests against independently transcribed MCU edge rules."""
from collections import deque
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import z62_encoder_input as physical
import z62_encoder_queue as queue


class Machine(queue.EncoderInputMixin):
    def __init__(self):
        self.io = threading.Lock()
        self.ticks = 0
        self._encoder_ports = {0x40021400: {'path': '/gpio-f'}, 0x40021000: {'path': '/gpio-e'}}
        self._encoder_phases = {0: 0, 1: 0}
        self._encoder_events = deque()
        self._encoder_due = self._encoder_edges = self._encoder_cancel_requests = 0
        self.sampled = [0, 0]
        self.counts = [0, 0]
        self.commands = []

    def _ready(self):
        pass

    def _advance_button_keys(self):
        pass

    def _key_clock(self):
        return self.ticks, 1000

    def _qtest(self, command):
        self.commands.append(command)
        _, path, _, pin, level = command.split()
        pin, level = int(pin), int(level)
        index = 0 if path == '/gpio-f' else 1
        config = physical.ENCODERS[index]
        bit = 1 if pin == config['a_pin'] else 0
        before = self.sampled[index]
        after = (before & ~(1 << bit)) | (level << bit)
        # Original instruction conditions, independent of queued sequences.
        if index == 0:
            self.counts[index] += int(before == 2 and after == 0) - int(before == 0 and after == 2)
        else:
            self.counts[index] += int(before == 0 and after == 1) - int(before == 1 and after == 0)
        self.sampled[index] = after

    def drain(self):
        for _ in range(1000):
            if not self._encoder_events:
                return
            self.ticks += 20
            self._advance_keys()
        raise AssertionError('Encoder queue did not drain')


class EncoderQueueTests(unittest.TestCase):
    def test_multiple_directions_are_exact_and_isolated(self):
        m = Machine()
        for index, steps in ((0,3), (1,-2), (0,-1), (1,1)):
            m.rotate(index, steps)
        m.drain()
        self.assertEqual(m.counts, [2, -1])
        self.assertEqual(m.sampled, [0, 0])
        self.assertEqual(m._encoder_edges, 28)

    def test_cancel_at_each_phase_never_introduces_an_extra_step(self):
        for index in (0,1):
            for direction in (-1,1):
                for prefix in range(1,5):
                    with self.subTest(index=index,direction=direction,prefix=prefix):
                        m = Machine()
                        m.rotate(index, direction * 3)
                        for _ in range(prefix-1):
                            m.ticks += 20
                            m._advance_keys()
                        before = list(m.counts)
                        m._cancel_encoder_motion()
                        m.drain()
                        self.assertEqual(m.counts, before)
                        self.assertEqual(m.sampled, [0,0])
                        self.assertEqual(m._encoder_phases, {0:0,1:0})

    def test_new_motion_waits_for_noncounting_return_to_rest(self):
        m = Machine()
        m.rotate(0,-4)
        m._cancel_encoder_motion()
        m.rotate(0,2)
        m.drain()
        self.assertEqual(m.counts,[1,0])  # first negative edge was already issued

    def test_deadlines_use_guest_clock_without_host_catchup_burst(self):
        m = Machine()
        m.rotate(0,1)
        self.assertEqual(len(m.commands),1)
        for _ in range(20):
            m._advance_keys()
        self.assertEqual(len(m.commands),1)
        m.ticks = 100000
        m._advance_keys()
        self.assertEqual(len(m.commands),2)
        m._advance_keys()
        self.assertEqual(len(m.commands),2)

    def test_invalid_or_full_requests_do_not_mutate_queue(self):
        m = Machine()
        for index, steps in ((True,1),(2,1),(0,True),(0,0),(0,33),(0,1.5)):
            with self.assertRaises(ValueError):
                m.rotate(index,steps)
        self.assertFalse(m.commands)
        m.rotate(0,32)
        before = list(m._encoder_events)
        with self.assertRaisesRegex(ValueError,'full'):
            m.rotate(1,1)
        self.assertEqual(list(m._encoder_events),before)

    def test_illegal_two_wire_transition_is_rejected(self):
        m = Machine()
        with self.assertRaises(ValueError):
            physical.drive_phase(m,0,3)
        self.assertFalse(m.commands)

    def test_gpio_discovery_rejects_missing_topology(self):
        with self.assertRaisesRegex(ValueError,'eight'):
            physical.discover_gpio_ports(lambda *args: [])


if __name__ == '__main__':
    unittest.main()
