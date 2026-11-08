"""Original task-construction contract; synthetic cases are only tool tests."""
import copy
from pathlib import Path
import struct
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'fenestra/z62'))
import task_create_contract as create


class TaskCreateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = create.collect()

    def pair(self, role='master', thumb=True):
        p = self.contract['roles'][role]
        tcb = p['context']['geometry']['pool_end'] + 0x100
        sp = tcb + 0x1000
        cfg = bytearray(56)
        entry = create.BASE + 0x1001
        struct.pack_into('<4I', cfg, 0, 0xAB, 0x100 if thumb else 0, entry if thumb else entry-1, 32)
        cfg[48:56] = b'TEST\0XYZ'
        regs = {n:0 for n in create.REGISTERS}
        regs.update(r0=sp+0x100, sp=sp, lr=create.BASE+0x200, pc=p['entry'], cpsr=0x13)
        block = bytearray(216)
        for off,val in [(8,0x10001),(12,0xAB),(16,0x100 if thumb else 0),(20,entry if thumb else entry-1),(0xB8,sp+0x400),(0xBC,sp+0x400-76)]:
            struct.pack_into('<I',block,off,val)
        block[0xCC:0xD4] = b'TEST\0\0\0\0'
        frame = bytearray(76)
        struct.pack_into('<I',frame,48,0x10001 if thumb else 0)
        struct.pack_into('<I',frame,64,0x3F if thumb else 0x13)
        struct.pack_into('<I',frame,72,entry-1)
        built = dict(registers=dict(regs,r0=sp+0x400-76,r4=tcb,r5=sp+0x100,sp=sp-56,pc=p['constructed']),
            tcb_address=tcb,tcb=block.hex(),frame_address=sp+0x400-76,frame=frame.hex(),config=cfg.hex())
        return dict(role=role,thread='01' if role=='master' else '03',
            entry=dict(registers=regs,config=cfg.hex()),constructed=built,
            returned=dict(registers=dict(regs,r0=0x10001,pc=regs['lr']),tcb=block.hex()))

    def test_original_entry_and_constructed_anchors(self):
        self.assertEqual(self.contract['roles']['master']['entry'],0x1010A268)
        self.assertEqual(self.contract['roles']['slave']['entry'],0x1003BC3C)
        self.assertEqual(self.contract['roles']['slave']['constructed'],0x1003C0A8)

    def test_both_engines_and_arm_thumb(self):
        for role in ('master','slave'):
            for thumb in (False,True):
                result=create.check_pair(self.pair(role,thumb),self.contract['roles'][role])
                self.assertEqual(result['name_hex'],'5445535400000000')
                self.assertFalse(result['complete_task_abi_verified'])

    def test_full_eight_byte_name_is_not_forced_nul(self):
        row=self.pair(); cfg=bytearray.fromhex(row['entry']['config']);cfg[48:56]=b'12345678'
        row['entry']['config']=row['constructed']['config']=cfg.hex()
        for snap in ('constructed','returned'):
            b=bytearray.fromhex(row[snap]['tcb']);b[204:212]=b'12345678';row[snap]['tcb']=b.hex()
        self.assertEqual(create.check_pair(row,self.contract['roles']['master'])['name_hex'],b'12345678'.hex())

    def test_config_frame_return_and_bounds_corruption_rejected(self):
        for kind in ('entry','frame','handle','sp','cpu','config','name','saved'):
            row=self.pair()
            if kind=='entry':row['constructed']['registers']['r5']+=4
            elif kind=='frame':row['constructed']['frame']='00'*76
            elif kind=='handle':row['returned']['registers']['r0']+=1
            elif kind=='sp':row['returned']['registers']['sp']+=4
            elif kind=='cpu':row['thread']='05'
            elif kind=='config':row['constructed']['config']='00'*56
            elif kind=='name':row['returned']['tcb']='00'*216
            else:row['returned']['registers']['r4']+=1
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                create.check_pair(row,self.contract['roles']['master'])

    def test_clock_read_restores_original_selected_engine(self):
        from unittest.mock import Mock, patch
        import observe_task_create as observer
        remote=Mock()
        with patch.object(observer,'ticks',return_value=42):
            self.assertEqual(observer.selected_ticks(remote,'03'),42)
        remote.select_thread.assert_called_once_with(3)

    def test_shared_return_address_is_not_enough_to_pair(self):
        import observe_task_create as observer
        pair=self.pair();regs=pair['returned']['registers']
        self.assertEqual(observer.matching_returns([pair],'master','01',regs),[pair])
        self.assertEqual(observer.matching_returns([pair],'master','02',regs),[])
        self.assertEqual(observer.matching_returns([pair],'master','01',dict(regs,sp=regs['sp']+4)),[])

    def test_lifecycle_and_name_uniqueness_not_asserted(self):
        r=create.check_pair(self.pair(),self.contract['roles']['master'])
        self.assertFalse(r['stable_lifetime_identity_verified'])
        self.assertFalse(r['task_name_unique_verified'])


if __name__=='__main__':unittest.main()
