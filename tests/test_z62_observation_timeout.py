"""Missing monitor reads remain evidence gaps; controls are never replayed."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from trace_z62_upper_waits import observe_with_timeout_evidence as observe


class ObservationTimeoutTests(unittest.TestCase):
    def test_default_preserves_failure(self):
        record={}
        with self.assertRaises(TimeoutError):
            observe(Mock(side_effect=TimeoutError('read missing')),record,enabled=False,consecutive=0,
                    gdb_ready=lambda:True,monitor_diagnostics=lambda:{},wall_seconds=1)
        self.assertEqual(record,{})

    def test_missing_read_yields_to_gdb_and_fresh_read_resets_streak(self):
        snapshot=Mock(side_effect=[TimeoutError('query-status missing'),{'virtual_seconds':7}])
        record={'observations':[]}
        row,count=observe(snapshot,record,enabled=True,consecutive=0,gdb_ready=lambda:True,
                          monitor_diagnostics=lambda:{'replayed_commands':0},wall_seconds=2)
        self.assertIsNone(row)
        self.assertEqual(count,1)
        self.assertEqual(record['observations'],[])
        self.assertTrue(record['observation_timeouts'][0]['gdb_packet_waiting'])
        self.assertFalse(record['observation_timeouts'][0]['control_commands_replayed'])
        row,count=observe(snapshot,record,enabled=True,consecutive=count,gdb_ready=lambda:False,
                          monitor_diagnostics=lambda:{},wall_seconds=3)
        self.assertEqual(row,{'virtual_seconds':7})
        self.assertEqual(count,0)
        self.assertEqual(snapshot.call_count,2)

    def test_three_consecutive_timeouts_remain_failure_with_records(self):
        record={}
        snapshot=Mock(side_effect=TimeoutError('no reply'))
        for index in (0,1):
            _,count=observe(snapshot,record,enabled=True,consecutive=index,gdb_ready=lambda:False,
                            monitor_diagnostics=lambda:{},wall_seconds=index)
            self.assertEqual(count,index+1)
        with self.assertRaises(TimeoutError):
            observe(snapshot,record,enabled=True,consecutive=2,gdb_ready=lambda:False,
                    monitor_diagnostics=lambda:{},wall_seconds=3)
        self.assertEqual(len(record['observation_timeouts']),3)


if __name__=='__main__':
    unittest.main()
