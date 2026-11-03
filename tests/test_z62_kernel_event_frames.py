"""Pair the raw result by the original task stack, not a shared kernel PC."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_z62_kernel_events_v2 import task_frame


class KernelEventFrameTests(unittest.TestCase):
    def test_only_bound_task_stack_can_supply_raw_wait_result(self):
        saved={'thread':'01','sp':0xC51C1DD0}
        self.assertTrue(task_frame(0xC51C1DC0,saved,-16))
        self.assertFalse(task_frame(0xC51C1D60,saved,-16))
        self.assertFalse(task_frame(0xC51C1DC0,None,-16))


if __name__=='__main__': unittest.main()
