"""Moving runtime evidence must preserve bytes and reject conflicting targets."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import migrate_z62_storage as migration


class StorageMigrationTests(unittest.TestCase):
    def scenario(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root=Path(temporary.name); source=root/'old-runtime'; source.mkdir()
        return root,source,root/'.runtime/migrated'

    def configure(self,root,source,target):
        return patch.multiple(migration,ROOT=root,DEST=target,OLD_RUNTIME=source,OLD_TEMP=root/'not-a-temp-root')

    def test_verified_copy_is_committed_and_old_file_removed(self):
        root,source,target=self.scenario(); data=bytes(range(256))*100
        (source/'evidence.bin').write_bytes(data)
        with self.configure(root,source,target),patch.object(migration,'sources',return_value=[(source,target/'c-runtime')]):
            migration.migrate()
        self.assertEqual((target/'c-runtime/evidence.bin').read_bytes(),data)
        self.assertFalse(source.exists())
        self.assertIn('"state": "moved"',(target/'files.jsonl').read_text(encoding='utf-8'))

    def test_conflicting_destination_keeps_the_source(self):
        root,source,target=self.scenario(); (source/'evidence.bin').write_bytes(b'original')
        destination=target/'c-runtime/evidence.bin'; destination.parent.mkdir(parents=True)
        destination.write_bytes(b'different')
        with self.configure(root,source,target),patch.object(migration,'sources',return_value=[(source,target/'c-runtime')]):
            with self.assertRaisesRegex(ValueError,'destination differs'):
                migration.migrate()
        self.assertEqual((source/'evidence.bin').read_bytes(),b'original')
        self.assertEqual(destination.read_bytes(),b'different')


if __name__=='__main__':
    unittest.main()
