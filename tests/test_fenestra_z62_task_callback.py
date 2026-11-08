"""Synthetic callback checks exercise tools, not original firmware failure paths."""
import copy
from pathlib import Path
import struct
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'fenestra/z62'))
import task_callback_contract as t
from pool_calls import REGISTERS


class CallbackContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.c=t.collect()

    def row(self,role='master',target=0x10200AC3):
        p=self.c['roles'][role];d=0xC20A1730 if role=='master' else 0xC167B7D8
        b={n:0 for n in REGISTERS};b.update(pc=p['shared_entry'],sp=0xC2C53008,cpsr=0x33,r0=0x1234,r1=d,lr=0x10100000)
        a=dict(b,pc=b['pc']+2,r1=target);bx=dict(a,pc=target&~1,cpsr=(a['cpsr']&~32)|(32 if target&1 else 0))
        return dict(role=role,registers=b,after_registers=a,current=[0xC2C15290,0],local_cpu=0,
            callback=dict(descriptor_address=d,descriptor=struct.pack('<2I',0xAABBCCDD,target).hex(),
                after_bx=bx,target_current=[0xC2C15290,0],target_rom=dict(address=target&~1,bytes='10b5'+'00'*14),
                after_target=dict(bx,pc=(target&~1)+2,sp=bx['sp']-8),
                stack_write=dict(address=bx['sp']-8,bytes=struct.pack('<2I',bx['r4'],bx['lr']).hex())))

    def test_both_original_shared_entries(self):
        self.assertEqual(self.c['roles']['master']['shared_entry'],0x103DEBBC)
        self.assertEqual(self.c['roles']['slave']['shared_entry'],0x1006CB80)
        for role in self.c['roles']:self.assertEqual(self.c['roles'][role]['shared_bytes'],'49680847')

    def test_independent_field_and_actual_target_effect(self):
        r=t.check_shared(self.row(),self.c['roles']['master'])
        self.assertTrue(r['independent_field_load_verified']);self.assertTrue(r['target_first_instruction_verified'])
        self.assertFalse(r['business_task_completed']);self.assertFalse(r['descriptor_ownership_verified'])

    def test_field_bx_and_stack_corruption_rejected(self):
        for kind in ('descriptor','address','loaded','bx-pc','bx-isa','arg','current','stack','effect'):
            e=self.row();c=e['callback']
            if kind=='descriptor':c['descriptor']='00'*8
            elif kind=='address':c['descriptor_address']+=4
            elif kind=='loaded':e['after_registers']['r1']+=4
            elif kind=='bx-pc':c['after_bx']['pc']+=2
            elif kind=='bx-isa':c['after_bx']['cpsr']^=32
            elif kind=='arg':c['after_bx']['r0']+=1
            elif kind=='current':c['target_current'][0]+=216
            elif kind=='stack':c['stack_write']['bytes']='00'*8
            else:c['after_target']['r2']=1
            with self.subTest(kind=kind),self.assertRaises(ValueError):t.check_shared(e,self.c['roles']['master'])

    def test_original_finite_instruction_effects(self):
        b=self.row()['callback']['after_bx']
        for raw,expected in [('08b5',dict(b,pc=b['pc']+2,sp=b['sp']-8)),
            ('2de9f05f',dict(b,pc=b['pc']+4,sp=b['sp']-40)),
            ('90b0',dict(b,pc=b['pc']+2,sp=b['sp']-64)),
            ('00f12005',dict(b,pc=b['pc']+4,r5=b['r0']+32)),
            ('0024',dict(b,pc=b['pc']+2,r4=0,cpsr=(b['cpsr']&~0xC0000000)|0x40000000))]:
            with self.subTest(raw=raw):self.assertEqual(t.first_effect(b,bytes.fromhex(raw))[0],expected)

    def test_arm_bx_alignment_and_unknown_instruction(self):
        b=self.row()['after_registers'];b['r1']=0x10103BC8
        self.assertEqual(t.bx_effect(b)['cpsr']&32,0)
        b['r1']+=2
        with self.assertRaises(ValueError):t.bx_effect(b)
        for raw in ('','00','00de','00bf'):
            with self.assertRaises(ValueError):t.first_effect(self.row()['registers'],bytes.fromhex(raw))

    def test_unbounded_descriptor_rejected(self):
        e=self.row();e['registers']['r1']=e['callback']['descriptor_address']=0x20000000
        with self.assertRaises(ValueError):t.check_shared(e,self.c['roles']['master'])


if __name__=='__main__':unittest.main()
