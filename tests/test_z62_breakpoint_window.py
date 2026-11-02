"""Ensure diagnostic windows cannot mix unrelated actions or RTOS stacks."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from z62_breakpoint_window import BreakpointWindow


class BreakpointWindowTests(unittest.TestCase):
    def setUp(self):
        self.plan = {'entry':0x100,'return_pc':0x200,'register':'r0','equals':0x14,'points':[0x300,0x400]}
        self.window = BreakpointWindow(self.plan,{0x100,0x200,0x300,0x400})
        self.reg = {'r0':0x14,'sp':0xc5408000}

    def test_half_press_does_not_open_full_press_window(self):
        self.assertIsNone(self.window.transition(0x100,{**self.reg,'r0':0x13},'1'))
        self.assertFalse(self.window.active)
        self.assertFalse(self.window.includes(0x300,self.reg,'1'))

    def test_exact_return_frame_closes_window(self):
        self.assertEqual(self.window.transition(0x100,self.reg,'1'),'open')
        self.assertIsNone(self.window.transition(0x200,self.reg,'2'))
        self.assertIsNone(self.window.transition(0x200,{**self.reg,'sp':self.reg['sp']-16},'1'))
        self.assertTrue(self.window.active)
        self.assertEqual(self.window.transition(0x200,self.reg,'1'),'close')
        self.assertFalse(self.window.active)

    def test_other_cpu_and_other_stack_are_excluded(self):
        self.window.transition(0x100,self.reg,'1')
        self.assertTrue(self.window.includes(0x300,{**self.reg,'sp':self.reg['sp']-96},'1'))
        self.assertFalse(self.window.includes(0x300,self.reg,'2'))
        self.assertFalse(self.window.includes(0x300,{**self.reg,'sp':self.reg['sp']-8192},'1'))
        self.assertTrue(self.window.includes(0x100,self.reg,'2'))

    def test_nested_matching_entry_cannot_replace_original_stack(self):
        self.window.transition(0x100,self.reg,'1')
        self.assertIsNone(self.window.transition(0x100,{**self.reg,'sp':0xc5300000},'2'))
        self.assertEqual(self.window.stack,self.reg['sp'])
        self.assertEqual(self.window.thread,'1')

    def test_unverified_or_self_disarming_points_are_rejected(self):
        for changes in ({'points':[0x300,0x999]}, {'points':[0x100]}, {'points':[0x200]},
                        {'points':[]}, {'register':'pc'}, {'entry':0x999}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                BreakpointWindow({**self.plan,**changes},{0x100,0x200,0x300,0x400})

    def test_explicit_tail_frame_offset_closes_only_the_expected_stack(self):
        window = BreakpointWindow({**self.plan, 'return_sp_delta': -16},
                                  {0x100,0x200,0x300,0x400})
        window.transition(0x100,self.reg,'1')
        self.assertIsNone(window.transition(0x200,self.reg,'1'))
        self.assertTrue(window.active)
        self.assertIsNone(window.transition(0x200,{**self.reg,'sp':self.reg['sp']-16},'2'))
        self.assertEqual(window.transition(0x200,{**self.reg,'sp':self.reg['sp']-16},'1'),'close')

    def test_optional_return_gate_is_disarmed_outside_its_original_frame(self):
        window = BreakpointWindow({**self.plan, 'gate_return': True, 'return_sp_delta': -16},
                                  {0x100,0x200,0x300,0x400})
        self.assertTrue(callable(getattr(window,'should_arm',None)),
                        'A gated return must not trap every unrelated queue epilogue')
        self.assertTrue(window.should_arm(0x100))
        self.assertFalse(window.should_arm(0x200))
        self.assertFalse(window.should_arm(0x300))
        window.transition(0x100,self.reg,'1')
        self.assertTrue(window.should_arm(0x200))
        self.assertTrue(window.should_arm(0x300))
        window.transition(0x200,{**self.reg,'sp':self.reg['sp']-16},'1')
        self.assertFalse(window.should_arm(0x200))
        self.assertFalse(window.should_arm(0x300))

    def test_unbounded_unaligned_or_noninteger_tail_offsets_are_rejected(self):
        for delta in (True,-2,-4100,4100,.5,None,'-16'):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                BreakpointWindow({**self.plan,'return_sp_delta':delta},
                                 {0x100,0x200,0x300,0x400})

    def test_return_gate_requires_an_explicit_boolean(self):
        for value in (1,'yes',None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                BreakpointWindow({**self.plan,'gate_return':value},
                                 {0x100,0x200,0x300,0x400})


if __name__ == '__main__':
    unittest.main()
