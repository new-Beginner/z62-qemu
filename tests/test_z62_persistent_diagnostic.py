"""A fault stack must survive normal VM scratch cleanup."""
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))


class PersistentDiagnosticTests(unittest.TestCase):
    def test_fault_files_survive_vm_cleanup_and_capture_is_not_repeated(self):
        import z62_persistent_diagnostic_console as api
        with tempfile.TemporaryDirectory(dir=ROOT/'.runtime/tmp') as directory:
            root=Path(directory); work=root/'session/runs/vm-1'; work.mkdir(parents=True)
            persistent=root/'persistent'
            owner=object.__new__(api.PersistentDiagnosticMixin)
            owner.work=work; owner.process=SimpleNamespace(pid=123)
            owner._diagnostic_timeout_events=[]; owner._diagnostic_capture_attempted=False
            owner._diagnostic_capture=None
            owner.diagnostic_profile={'runtime_binary':'qemu-system-arm.exe','binary_sha256':'a'*64,'gdb':'gdb.exe'}
            owner.persistent_diagnostic_profile={'output_root':str(persistent),'workspace':str(ROOT)}
            def capture(*args,**kwargs):
                target=Path(args[4]); target.mkdir(parents=True)
                data=b'#0 qemu_main_loop\n'; (target/'host-gdb.txt').write_bytes(data)
                return {'completed_capture':True,'log_sha256':hashlib.sha256(data).hexdigest()}
            with patch.object(api.host_capture,'capture',side_effect=capture) as spy:
                owner._diagnostic_timeout('query-status',None,'first timeout')
                owner._diagnostic_timeout('qom-get',{'property':'x'},'second timeout')
                self.assertEqual(spy.call_count,1)
            self.assertTrue(work.resolve().is_relative_to(ROOT))
            shutil.rmtree(work)
            report=persistent/'vm-1/first-timeout/host-gdb.txt'
            self.assertEqual(report.read_bytes(),b'#0 qemu_main_loop\n')
            self.assertTrue((persistent/'vm-1/timeout-0002.json').is_file())
            self.assertEqual(owner._diagnostic_capture['log_sha256'],hashlib.sha256(report.read_bytes()).hexdigest())

    def test_persistent_output_outside_workspace_is_refused(self):
        import z62_persistent_diagnostic_console as api
        owner=object.__new__(api.PersistentDiagnosticMixin)
        owner.work=ROOT/'.runtime/tmp/fake-vm'
        owner.persistent_diagnostic_profile={'output_root':'C:/not-a-project-output','workspace':str(ROOT)}
        with self.assertRaisesRegex(ValueError,'workspace'):
            owner._persistent_folder()


if __name__=='__main__':
    unittest.main()
