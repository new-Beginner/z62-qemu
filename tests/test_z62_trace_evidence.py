"""No hardware access: validate complete/incomplete trace acceptance."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from trace_z62_capture_waits import trace_complete


class TraceEvidenceTests(unittest.TestCase):
    def fixture(self):
        return {'hits':[{'label':'kernel-wait-return','caller_lr':'0x102dbbb1'},
                        {'label':'kernel-wait-return','caller_lr':'0x102dda01'},
                        {'label':'capture-stop-result'}],
                'first_0x3f_append_captured':True,'process_closed':True,'detach':'OK'}

    def test_complete(self):
        self.assertTrue(trace_complete(self.fixture()))

    def test_unrelated_wait_cannot_replace_target(self):
        r=self.fixture();r['hits'][0]['caller_lr']='0x10372aa7'
        self.assertFalse(trace_complete(r))

    def test_missing_cleanup_or_error_is_failure(self):
        for change in ({'process_closed':False},{'detach':'E01'},
                       {'failure':{'type':'TimeoutError'}},{'cleanup_error':'socket error'},
                       {'first_0x3f_append_captured':False}):
            r=copy.deepcopy(self.fixture());r.update(change)
            self.assertFalse(trace_complete(r))

    def test_empty_is_failure(self):
        self.assertFalse(trace_complete({}))


if __name__=='__main__':unittest.main()
