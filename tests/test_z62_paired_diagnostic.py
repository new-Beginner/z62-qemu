"""Diagnostics preserve raw meanings and never retry a timed-out control."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))


class DiagnosticTests(unittest.TestCase):
    def api(self):
        import z62_paired_diagnostic_console as api
        return api

    def test_selector_fields_keep_halfword_layout(self):
        api=self.api()
        blocks={'scalar':[0x12340002,7],'cache':[0]*16,'decoded':[0x00030000],
                'inhibit':[5],'join':[3],'processor':[0x0400],'groups':[1,2,3,4]}
        blocks['cache'][1]=0x00020000; blocks['cache'][14]=0x00010000
        row=api.decode_selector(blocks)
        self.assertEqual(row['scalar'],{'current':2,'previous':0x1234,'changed':7})
        self.assertEqual(row['cached'],{'current':2,'previous':1})
        self.assertEqual(row['decoded_master'],3)
        self.assertFalse(row['original_observed_gate'])  # inhibit=5 cannot be hidden by a C output
        self.assertEqual(row['processor_state_byte'],4)

    def test_incomplete_or_out_of_range_reads_fail(self):
        api=self.api()
        with self.assertRaises(ValueError):
            api.decode_selector({'scalar':[True,0]})

    def test_observer_does_not_retry_and_captures_only_once(self):
        api=self.api()
        class Owner:
            def __init__(self):
                self.calls=[]
            def _diagnostic_timeout(self,*args):
                self.calls.append(args)
        owner=Owner(); client=object.__new__(api.ObservedQmp)
        client.owner=owner
        count=[]
        def timeout(*args,**kwargs):
            count.append((args,kwargs)); raise TimeoutError('synthetic missing reply')
        with patch.object(api.QmpClient,'command',timeout):
            with self.assertRaises(TimeoutError):
                client.command('qom-set',{'value':1})
        self.assertEqual(len(count),1)
        self.assertEqual(len(owner.calls),1)

    def test_capture_failure_does_not_mask_the_original_timeout(self):
        api=self.api()
        class Owner:
            def _diagnostic_timeout(self,*args):
                raise OSError('test evidence directory unavailable')
        owner=Owner(); client=object.__new__(api.ObservedQmp); client.owner=owner
        with patch.object(api.QmpClient,'command',side_effect=TimeoutError('original QMP deadline')):
            with self.assertRaisesRegex(TimeoutError,'original QMP deadline'):
                client.command('qom-set',{'value':1})

    def test_retained_owner_capture_is_attempted_only_once(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as directory:
            owner=object.__new__(api.PairedDiagnosticMixin)
            owner.work=Path(directory); owner.process=SimpleNamespace(pid=123)
            owner._diagnostic_timeout_events=[]; owner._diagnostic_capture_attempted=False
            owner.diagnostic_profile={'runtime_binary':'qemu-system-arm.exe','binary_sha256':'a'*64,'gdb':'gdb.exe'}
            with patch.object(api.host_capture,'capture',return_value={'completed_capture':True}) as capture:
                owner._diagnostic_timeout('query-status',None,'first missing reply')
                owner._diagnostic_timeout('query-status',None,'second missing reply')
                self.assertEqual(capture.call_count,1)
            self.assertEqual(len(owner._diagnostic_timeout_events),2)


if __name__=='__main__':
    unittest.main()
