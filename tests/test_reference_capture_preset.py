"""CLI and audit checks only; no real QEMU or USB calls."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import run_reference_console as run

class CapturePresetCliTests(unittest.TestCase):
    def test_nonbaseline_rejected_before_staging(self):
        for argv in (['run','z72','--capture-preset','init-mode'],
                     ['run','z62','--capture-preset','init-mode','--experimental-parameters']):
            with self.subTest(argv=argv), patch.object(sys,'argv',argv), patch.object(run,'stage') as stage, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exc:run.main()
                self.assertEqual(exc.exception.code,2)
                stage.assert_not_called()

    def test_preset_record_and_effective_command(self):
        for preset in ('baseline','mode-only','init-mode'):
            with self.subTest(preset=preset), tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR')) as folder:
                root=Path(folder);old_path=list(sys.path);captured=[]
                class FakePopen:
                    def __init__(self, command, *a, **kw):captured.append(command)
                def fake_run(*a,**kw):run.subprocess.Popen(['qemu-system-arm.exe','-S'])
                try:
                    with patch.object(sys,'argv',['run','z62','--experimental-parameters','--z62-updates','--capture-preset',preset]), patch.object(run,'stage',return_value=(root,{'parameters':None})), patch.object(run.subprocess,'Popen',FakePopen), patch.object(run,'install_native_process_adapter',side_effect=lambda work: run.subprocess.Popen), patch.object(run.runpy,'run_path',side_effect=fake_run),contextlib.redirect_stdout(io.StringIO()):
                        run.main()
                    data=json.loads((root/'session.json').read_text())
                    self.assertEqual(data['capture_preset'],preset)
                    self.assertFalse(data['capture_pixels_implemented'])
                    self.assertEqual(data['host_version'],'2026.10.28-r3')
                    props=[v for v in captured[0] if 'laboratory-' in v]
                    self.assertEqual(props,list(run.PRESETS[preset]))
                finally:sys.path[:]=old_path

if __name__=='__main__':unittest.main()
