"""An ASCII alias must never create a second C-drive runtime."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import z62_workspace_paths as storage


class WorkspacePathsTests(unittest.TestCase):
    def test_resolved_workspace_path_keeps_its_ascii_access_name(self):
        path=storage.WorkspacePath(storage.ROOT/'.runtime')
        self.assertTrue(str(path).isascii())
        self.assertEqual(Path(path).resolve(),storage.ROOT/'.runtime')
        self.assertTrue(str(path.resolve()).isascii())

    def test_old_project_roots_are_resolved_inside_the_workspace(self):
        path=storage.WorkspacePath(storage.OLD_RUNTIME/'fixtures/group23.bin')
        self.assertEqual(Path(path).resolve(),storage.ROOT/'.runtime/migrated/c-runtime/fixtures/group23.bin')

    def test_external_output_is_rejected_before_creation(self):
        path=storage.WorkspacePath('C:/z62-output-must-not-be-created.txt')
        with self.assertRaisesRegex(ValueError,'workspace'):
            path.open('x')
        self.assertFalse(Path(str(path)).exists())

    def test_relative_name_contract_is_preserved(self):
        path=storage.WorkspacePath('frame.bin')
        self.assertFalse(path.is_absolute())
        self.assertEqual(path.name,'frame.bin')


if __name__=='__main__':
    unittest.main()
