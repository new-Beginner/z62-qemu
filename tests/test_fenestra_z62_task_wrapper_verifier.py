import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'fenestra/z62'))
import verify_task_wrapper as v

class WrapperVerifierTests(unittest.TestCase):
    def test_incomplete_rejected(self):
        with self.assertRaises((ValueError,KeyError)):v.check_run({'schema':1,'tool':v.TOOL,'completed':False})
    def test_independence_rejected(self):
        with self.assertRaises(ValueError):v.require_independent([{'owned_pid':1},{'owned_pid':1}])
    def test_register_write_rejected(self):
        with self.assertRaises(ValueError):v.allowed_command('P0=00000000')
    def test_software_breakpoint_rejected(self):
        with self.assertRaises(ValueError):v.allowed_command('Z0,10020000,2')

    def test_current_record_replays(self):
        import json
        path=Path(__file__).resolve().parents[1]/'analysis/fenestra-z62-task-wrapper-r12/run-6-final.json'
        r=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(v.check_run(r)['chains'],len(r['pairs']))
    def test_all_targeted_record_mutations_rejected(self):
        import json
        path=Path(__file__).resolve().parents[1]/'analysis/fenestra-z62-task-wrapper-r12/run-6-final.json'
        r=json.loads(path.read_text(encoding='utf-8'));bad=v.mutations(r);self.assertEqual(len(bad),33)
        for name,record in bad.items():
            with self.subTest(name=name),self.assertRaises((ValueError,KeyError,TypeError,IndexError)):
                v.check_run(record)
    def test_foreign_service_stack_rejected(self):
        import json
        path=Path(__file__).resolve().parents[1]/'analysis/fenestra-z62-task-wrapper-r12/run-6-final.json'
        r=json.loads(path.read_text(encoding='utf-8'));e=r['events'][r['pairs'][0]['stages']['native_start']]
        e['registers']['sp']+=4;e['after_registers']['sp']+=4
        with self.assertRaises(ValueError):v.check_run(r)
if __name__=='__main__':unittest.main()
