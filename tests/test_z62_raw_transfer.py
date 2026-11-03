"""Immutable RAW domain snapshots and real native quantized reconstruction."""
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))


class RawTransferTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('z62_raw_transfer'),'RAW transfer contract is missing')
        return importlib.import_module('z62_raw_transfer')

    def test_snapshot_copies_curve_and_serializes_exact_domain(self):
        m=self.module(); lut=[16+i*4 for i in range(256)]
        transfer=m.RawTransfer(12,'lookup8-high-byte',lut)
        blob=transfer.to_bytes(); lut[10]=999
        self.assertEqual(transfer.lookup[10],56)
        self.assertEqual(m.RawTransfer.from_bytes(blob),transfer)
        self.assertEqual(len(blob),532)
        self.assertEqual(transfer.input_quantum,256)
        with self.assertRaises(AttributeError): transfer.bits=14

    def test_malformed_or_unsupported_descriptor_rejected(self):
        m=self.module()
        for args in ((10,'shift',()),(12,'unknown',()),(12,'lookup8-high-byte',[0]*256),
                     (12,'lookup8-high-byte',list(range(255))),(12,'shift',[1]*256)):
            with self.assertRaises(ValueError): m.RawTransfer(*args)
        blob=m.RawTransfer(14,'shift').to_bytes()
        for offset in (0,4,8,12,16,527,528):
            bad=bytearray(blob); bad[offset]^=1
            with self.assertRaises(ValueError): m.RawTransfer.from_bytes(bad)

    def native(self,case,bits,codec,main_packet=None):
        m=self.module(); alias=Path('Q:/')
        root=alias if alias.exists() and alias.samefile(ROOT) else ROOT
        self.assertTrue(str(root).isascii())
        compiler=root/'.runtime/tools/msys64/ucrt64/bin/gcc.exe'
        self.assertTrue(compiler.is_file(),'Native GCC required; no skipped checks')
        base=root/'.runtime/tmp'; base.mkdir(parents=True,exist_ok=True)
        self.assertTrue(base.resolve().is_relative_to(ROOT))
        env=dict(os.environ,TEMP=str(base),TMP=str(base),LANG='C',LC_ALL='C',
                 PATH=str(compiler.parent)+os.pathsep+os.environ.get('PATH',''))
        lut=tuple(16+i*4 for i in range(256)) if codec=='lookup8-high-byte' else ()
        with tempfile.TemporaryDirectory(prefix='raw-transfer-',dir=base) as directory:
            work=Path(directory); descriptor=work/'transfer.z62t'
            descriptor.write_bytes(m.RawTransfer(bits,codec,lut).to_bytes())
            exe=work/'transfer.exe'
            built=subprocess.run([str(compiler),'-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic',
                '-I',str(root/'qemu/z62-capturework'),str(root/'tests/native/z62_raw_transfer_probe.c'),
                '-o',str(exe)],env=env,cwd=work,capture_output=True,timeout=60)
            self.assertEqual(built.returncode,0,built.stderr.decode('utf-8','backslashreplace'))
            command=[str(exe),case,str(descriptor)]
            if main_packet is not None:
                (work/'frame.z62m').write_bytes(main_packet)
                command.extend([str(work/'frame.z62m'),'10','10','6','6','16',str(work/'output.p12'),str(work/'linear.raw')])
            ran=subprocess.run(command,env=env,cwd=work,capture_output=True,timeout=60)
            self.assertEqual(ran.returncode,0,ran.stderr.decode('utf-8','backslashreplace'))
            result=json.loads(ran.stdout); self.assertTrue(result['completed'])
            if main_packet is not None: result['linear']=(work/'linear.raw').read_bytes()
            return result

    def test_native_shift12_all_65536_input_samples(self): self.native('roundtrip',12,'shift')
    def test_native_shift14_all_65536_input_samples(self): self.native('roundtrip',14,'shift')
    def test_native_shift16_is_lossless(self): self.native('roundtrip',16,'shift')
    def test_native_lut_all_65536_samples_reconstruct_quantized_interval(self): self.native('roundtrip',12,'lookup8-high-byte')
    def test_native_unknown_code_in_last_pixel_rejects_without_writing(self): self.native('rejects',12,'lookup8-high-byte')

    def test_main_frame_through_frozen_transfer_recovers_independent_quantized_samples(self):
        from z62_main_frame import make_packet,parse_packet
        from verify_z62_capturework_pixels_evidence import tile_resize
        image=Image.new('RGB',(2,2)); image.putdata([(255,20,0),(0,230,30),(40,60,255),(180,200,70)])
        packet=make_packet(image,width=14,height=14,stride=32,epoch=62,publish_id=1,frame_id=0,virtual_time_ns=0)
        meta,raw=parse_packet(packet)
        linear=self.native('scene',12,'lookup8-high-byte',packet)['linear']
        source=np.frombuffer(raw,dtype='<u2').reshape(meta.height,meta.stride//2)[:,:meta.width]
        selected=tile_resize(tile_resize(source,10,10),6,6)
        rows=np.frombuffer(linear,dtype=np.uint8).reshape(6,16)
        actual=rows[:,:12].copy().view('<u2').reshape(6,6)
        np.testing.assert_array_equal(actual,((selected>>8).astype(np.uint32)*256+128).astype(np.uint16))
        self.assertTrue(np.all(rows[:,12:]==0xa5))


if __name__=='__main__': unittest.main()
