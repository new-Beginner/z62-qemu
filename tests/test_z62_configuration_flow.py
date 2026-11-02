"""Shared continuation sites alone must not prove a configuration call."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))


def event(sequence, pc, *, thread='01', sp='0xc51c1fd0'):
    return {'sequence':sequence,'thread':thread,'registers':{'pc':hex(pc),'sp':sp},
            'state':{'virtual_seconds':sequence/10},
            'extra_observation':{'configuration':{'marker':sequence}}}


class ConfigurationFlowTests(unittest.TestCase):
    def api(self):
        try:
            from analyze_z62_configuration_flow import pair_calls
        except ImportError as exc:
            self.fail('The ordered caller-frame correlation is missing: '+str(exc))
        return pair_calls

    def test_shared_return_and_epilogue_are_outside_a_configuration_call(self):
        trace = {'hits':[event(1,0x103226B2),event(2,0x103226BA),
                         event(3,0x103226AE),event(4,0x103226B2),event(5,0x103226BA),
                         event(6,0x103226BA)]}
        original = copy.deepcopy(trace)
        result = self.api()(trace)
        self.assertEqual(len(result['calls']),1)
        self.assertEqual([result['calls'][0][key]['sequence'] for key in ('call','return','control_updated')],
                         [3,4,5])
        self.assertEqual(result['outside_scope_count'],3)
        self.assertEqual(result['incomplete'],[])
        self.assertEqual(trace,original)

    def test_other_cpu_or_stack_cannot_complete_the_original_call(self):
        trace = {'hits':[event(1,0x103226AE),event(2,0x103226B2,thread='02'),
                         event(3,0x103226B2,sp='0xc51c1fc0'),event(4,0x103226B2),
                         event(5,0x103226BA,thread='02'),event(6,0x103226BA)]}
        result = self.api()(trace)
        self.assertEqual(len(result['calls']),1)
        self.assertEqual(result['calls'][0]['return']['sequence'],4)
        self.assertEqual(result['calls'][0]['control_updated']['sequence'],6)
        self.assertEqual(result['outside_scope_count'],3)

    def test_overlapping_incomplete_or_unordered_records_do_not_prove_completion(self):
        result = self.api()({'hits':[event(1,0x103226AE),event(2,0x103226B2),
                                    event(3,0x103226AE),event(4,0x103226BA)]})
        self.assertEqual(result['calls'],[])
        self.assertEqual(len(result['incomplete']),2)
        self.assertFalse(result['all_observed_calls_paired'])
        with self.assertRaises(ValueError):
            self.api()({'hits':[event(2,0x103226AE),event(1,0x103226B2)]})


if __name__=='__main__':
    unittest.main()
