"""Synthetic entry relations test tools, not firmware lifecycle acceptance."""
from pathlib import Path
import struct
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'fenestra/z62'))
import task_entry_contract as t


class TaskEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.c=t.collect()

    def pair(self,role='master',thumb=True):
        p=self.c['roles'][role];tb=p['context']['geometry']['pool_end']+0x100
        top=tb+0x1000;fp=top-76;entry=t.BASE+0x1000+(1 if thumb else 0)
        b=bytearray(216)
        for off,x in [(8,0x1000001),(12,0x1234),(20,entry),(0xB8,top),(0xBC,fp)]:struct.pack_into('<I',b,off,x)
        f=bytearray(76)
        for off,x in [(0,0x5678),(4,0x1234),(64,0x33 if thumb else 0x13),(72,entry&~1)]:struct.pack_into('<I',f,off,x)
        regs={n:0 for n in t.REGISTERS};regs.update(r0=fp,r1=0x1234,r4=tb,r5=0,r11=0x5678,pc=p['checkpoint'],cpsr=0x13)
        prepared=dict(registers=regs,tcb_address=tb,tcb=b.hex(),frame_address=fp,frame=f.hex())
        first=dict(registers=dict(regs,r0=0x5678,r1=0x1234,pc=entry&~1,sp=top,cpsr=0x33 if thumb else 0x13),
                   tcb_address=tb,tcb=b.hex(),current=[tb,0],local_cpu=0)
        return dict(role=role,prepared=prepared,entered=first)

    def test_both_original_checkpoints(self):
        self.assertEqual(self.c['roles']['master']['checkpoint'],0x1010AAC4)
        self.assertEqual(self.c['roles']['slave']['checkpoint'],0x1003C498)

    def test_arm_thumb_nonzero_arguments(self):
        for role in ('master','slave'):
            for thumb in (False,True):
                r=t.check_pair(self.pair(role,thumb),self.c['roles'][role])
                self.assertEqual(r['entry_arguments'],[0x5678,0x1234]);self.assertFalse(r['business_task_completed'])

    def test_corruption_and_system_mode_rejected(self):
        for k in ('arg','exinf','sp','tcb','pc','mode','frame'):
            row=self.pair()
            if k in ('arg','exinf','sp','pc'):row['entered']['registers'][{'arg':'r0','exinf':'r1'}.get(k,k)]^=4
            elif k=='tcb':row['entered']['tcb_address']+=216
            elif k=='mode':row['entered']['registers']['cpsr']=0x1F
            else:row['prepared']['frame']='00'*76
            with self.subTest(k=k),self.assertRaises(ValueError):t.check_pair(row,self.c['roles']['master'])

    def test_r5_is_reused_status_not_input_handle(self):
        row=self.pair()['prepared'];row['registers']['r5']=0x1000001
        with self.assertRaises(ValueError):t.check_prepared(row,self.c['roles']['master'])

    def test_prepared_is_not_yet_executed(self):
        r=t.check_prepared(self.pair()['prepared'],self.c['roles']['master'])
        self.assertFalse(r['task_entry_observed']);self.assertFalse(r['complete_task_abi_verified'])


if __name__=='__main__':unittest.main()
