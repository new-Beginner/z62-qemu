"""Do not fill a system drive or adopt an unowned directory while staging SD."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import run_z62_paired_managed_console as managed


class ManagedScratchTests(unittest.TestCase):
    def test_capacity_is_checked_before_a_large_card_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'owned'
            with patch.object(managed.shutil,'disk_usage',return_value=SimpleNamespace(free=10)):
                with self.assertRaisesRegex(ValueError,'Insufficient scratch'):
                    managed.managed_scratch(root,11)
            self.assertEqual(list(root.glob('*.raw')),[])
            with patch.object(managed.shutil,'disk_usage',return_value=SimpleNamespace(free=20)):
                self.assertEqual(managed.managed_scratch(root,11),root)

    def test_unowned_existing_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'owner marker'):
                managed.managed_scratch(Path(folder),1)

    def test_process_local_scratch_is_restored_after_launch_failure(self):
        before=tempfile.gettempdir(); names=('TEMP','TMP','PI_SCRATCH_DIR')
        old={name:os.environ.get(name) for name in names}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'owned'; card=Path(folder)/'card.raw'; card.write_bytes(bytes(512))
            def launch(argv):
                self.assertEqual(Path(tempfile.gettempdir()),root)
                self.assertTrue(all(os.environ[name]==str(root) for name in names))
                raise RuntimeError('synthetic launch failure')
            with patch.object(managed.diagnostic,'main',side_effect=launch), \
                 patch.object(managed.shutil,'disk_usage',return_value=SimpleNamespace(free=3*1024**3)):
                with self.assertRaisesRegex(RuntimeError,'synthetic launch'):
                    managed.main(['--scratch-root',str(root),'--sd-card',str(card)])
        self.assertEqual(tempfile.gettempdir(),before)
        self.assertEqual({name:os.environ.get(name) for name in names},old)


if __name__=='__main__':
    unittest.main()
