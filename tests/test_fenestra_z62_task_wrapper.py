"""Tool contracts only; synthetic tests are not native failure coverage."""
import sys
from pathlib import Path
import struct
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'fenestra/z62'))
import task_wrapper_contract as w

class WrapperTests(unittest.TestCase):
    def test_original_boundaries(self):
        c=w.collect()
        self.assertEqual(c['roles']['master']['points']['entry'],0x103DEBC6)
        self.assertEqual(c['roles']['slave']['points']['entry'],0x1006CB8A)
        self.assertEqual(c['roles']['master']['shared_entry'],0x103DEBBD)
    def test_config_modes(self):
        for mode in range(3):
            cfg=bytearray(28);cfg[0]=mode;struct.pack_into('<3I',cfg,4,4096,22,0x1234)
            x=w.native_config(0xC2000000,bytes(cfg),0x103DEBBD,b'ABCDEFGH')
            a=struct.unpack('<14I',x)
            self.assertEqual(a[:5],(0xC2000000,1 if mode==0 else 0x20001,0x103DEBBD,4096,22))
            self.assertEqual(a[5:11],(0,)*6);self.assertEqual(a[11],mode);self.assertEqual(x[48:],b'ABCDEFGH')
    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):w.native_config(0xC2000000,bytes([3])+bytes(27),0x103DEBBD,bytes(8))
    def test_sizes_rejected(self):
        for size in (0,27,29):
            with self.assertRaises(ValueError):w.native_config(0xC2000000,bytes(size),0x103DEBBD,bytes(8))
    def test_field_effect(self):
        c=w.collect()['roles']['master'];r={n:i for i,n in enumerate(w.REGISTERS)}
        r.update(pc=c['points']['field'],cpsr=0x33,sp=0xC2001000)
        self.assertEqual(w.step_effect(r,c,'field'),dict(r,pc=r['pc']+4))
    def test_blx_clears_thumb(self):
        c=w.collect()['roles']['master'];r={n:i for i,n in enumerate(w.REGISTERS)}
        r.update(pc=c['points']['call'],cpsr=0x33)
        a=w.step_effect(r,c,'call');self.assertEqual(a['pc'],c['create_api']);self.assertEqual(a['cpsr'],0x13);self.assertEqual(a['lr'],r['pc']+5)
    def test_service_0a_is_not_r10_start(self):
        p=w.collect()['roles']['master']
        self.assertEqual(p['points']['native_start'],0x1010B4E8)
        self.assertEqual(p['service_code'],0x800A0200)
        r={n:i for i,n in enumerate(w.REGISTERS)};r.update(pc=p['points']['native_start'],sp=0xC2001000)
        self.assertEqual(w.step_effect(r,p,'native_start')['sp'],r['sp']-24)
    def test_unassigned_stack_word_is_preserved(self):
        cfg=bytes(28);x=w.native_config(0xC2000000,cfg,0x103DEBBD,bytes(8),0x11223344)
        self.assertEqual(struct.unpack_from('<I',x,40)[0],0x11223344)
    def test_both_engines_and_drained_required(self):
        rows=[{'role':'slave','stages':{'started':1}} for _ in range(24)]
        self.assertFalse(w.sample_ready(rows,24))
        rows.append({'role':'master','stages':{}});self.assertFalse(w.sample_ready(rows,24))
        rows[-1]['stages']['started']=2;self.assertTrue(w.sample_ready(rows,24))
        self.assertFalse(w.sample_ready(rows,26))
    def test_unknown_phase_rejected(self):
        with self.assertRaises(ValueError):w.step_effect({}, {}, 'unknown')

if __name__=='__main__':unittest.main()
