"""Task entry replay safety unit checks."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'fenestra/z62'))
import verify_task_entry as v


class TaskEntryVerifierTests(unittest.TestCase):
    def test_original_arm_push_register_effects(self):
        from pool_calls import REGISTERS
        b={n:0 for n in REGISTERS};b.update(pc=0x10103BC8,sp=0xC2C53008,cpsr=0x13)
        e=dict(role='master',registers=b,after_registers=dict(b,pc=b['pc']+4,sp=b['sp']-8),rom_window={'bytes':('00'*16)+'10402de9'+('00'*12)})
        v.check_first_step(e)
        e['after_registers']['r0']=1
        with self.assertRaises(ValueError):v.check_first_step(e)

    def test_original_thumb_load_effects_not_memory_value_proof(self):
        from pool_calls import REGISTERS
        b={n:0 for n in REGISTERS};b.update(pc=0x103DEBBC,sp=0xC2C53008,cpsr=0x33,r1=0xC20A1730)
        e=dict(role='master',registers=b,after_registers=dict(b,pc=b['pc']+2,r1=0x10200C8D),rom_window={'bytes':('00'*16)+'4968'+('00'*14)})
        v.check_first_step(e)
        e['after_registers']['r1']=0
        with self.assertRaises(ValueError):v.check_first_step(e)

    def test_missing_record_rejected(self):
        with self.assertRaises((ValueError,KeyError)):v.check_run({})

    def test_independent_processes_required(self):
        with self.assertRaises(ValueError):v.require_independent([{'owned_pid':1},{'owned_pid':1}])

    def test_debug_writes_denied(self):
        for c in ('s','Hc03','M10020000,1:00','P0=00','Z0,10020000,2','c10020000'):
            with self.assertRaises(ValueError):v.allowed_command(c)


if __name__=='__main__':unittest.main()
