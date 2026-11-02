"""A multiword original store must advance past both watched destinations."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import trace_z62_upper_waits as trace


class MultiStore:
    def __init__(self, addresses):
        self.watches = set(addresses)
        self.pointer = 0xC2D1A9C0
        self.memory = {}

    def step_original_stm(self):
        destinations = range(self.pointer, self.pointer+16, 4)
        if any(address in self.watches for address in destinations):
            return 'another-watch-trap'
        for address in destinations:
            self.memory[address] = 0
        self.pointer += 16
        return 'single-step-complete'


class WatchStepTests(unittest.TestCase):
    def test_two_writes_in_one_stm_do_not_recursively_trap_the_step(self):
        points = {0xC2D1A9C0, 0xC2D1A9CC}
        model = MultiStore(points)
        suspended = trace.step_suspended_watch_addresses(points, 0xC2D1A9C0, 'write')
        model.watches.difference_update(suspended)
        self.assertEqual(model.step_original_stm(), 'single-step-complete')
        self.assertEqual(model.pointer, 0xC2D1A9D0)
        self.assertEqual(len(model.memory), 4)
        model.watches.update(suspended)
        self.assertEqual(model.watches, points)

    def test_single_write_and_multiple_read_observations_stay_supported(self):
        for access, points in (('write', {0xC2D1A9C0}),
                               ('read', {0xC2D1A9C0, 0xC2D1A9CC})):
            with self.subTest(access=access):
                self.assertEqual(set(trace.step_suspended_watch_addresses(points, 0xC2D1A9C0, access)), points)
        with self.assertRaises(ValueError):
            trace.step_suspended_watch_addresses({1}, 2, 'write')

    def test_nested_memory_trap_is_not_accepted_as_an_executed_instruction(self):
        trace.validate_single_step_reply('T05thread:01;')
        for stop in ('T05thread:01;watch:c2d1a9cc;',
                     'T05thread:01;rwatch:c2d1a9cc;', 'T02thread:01;'):
            with self.subTest(stop=stop), self.assertRaises(RuntimeError):
                trace.validate_single_step_reply(stop)


if __name__ == '__main__':
    unittest.main()
