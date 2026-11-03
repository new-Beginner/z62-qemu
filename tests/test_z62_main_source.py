"""Host MAIN envelope and actual native C source lifecycle checks."""
import importlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))


class MainSourceTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('z62_main_frame'),'MAIN producer module is missing')
        return importlib.import_module('z62_main_frame')

    def packet(self,**changes):
        options=dict(width=14,height=10,stride=32,epoch=62,publish_id=1,
                     frame_id=1,virtual_time_ns=33_333_334)
        options.update(changes)
        return self.module().make_packet(Image.new('RGB',(7,5),(255,128,0)),**options)

    def test_linear16_cfa_tags_padding_and_immutable_bytes(self):
        m=self.module(); packet=self.packet(); meta,raw=m.parse_packet(packet)
        self.assertIsInstance(packet,bytes)
        self.assertEqual((meta.width,meta.height,meta.stride),(14,10,32))
        self.assertEqual((meta.epoch,meta.publish_id,meta.frame_id,meta.virtual_time_ns),(62,1,1,33_333_334))
        rows=np.frombuffer(raw,dtype=np.uint8).reshape(10,32)
        self.assertTrue(np.all(rows[:,28:]==0))
        values=rows[:,:28].copy().view('<u2').reshape(10,14)
        green=round(1024+((128/255+.055)/1.055)**2.4*(65520-1024))
        self.assertEqual(values[0,:4].tolist(),[65520,green,65520,green])
        self.assertEqual(values[1,:4].tolist(),[green,1024,green,1024])

    def test_corruption_and_wrong_pixel_domain_rejected(self):
        m=self.module(); original=self.packet()
        for offset in (0,16,32,56,84,96,len(original)-1):
            damaged=bytearray(original); damaged[offset]^=1
            with self.assertRaises(ValueError): m.parse_packet(damaged)
        damaged=bytearray(original); struct.pack_into('<I',damaged,64,2)
        struct.pack_into('<I',damaged,88,zlib.crc32(damaged[:88]))
        with self.assertRaises(ValueError): m.parse_packet(damaged)

    def test_geometry_timeline_and_old_auxiliary_role_rejected(self):
        m=self.module()
        for changes in ({'width':13},{'height':0},{'stride':27},{'frame_id':2},
                        {'width':4096,'height':4096},{'publish_id':0}):
            with self.assertRaises(ValueError): self.packet(**changes)
        with self.assertRaises(ValueError): m.parse_packet(b'Z62S'+self.packet()[4:])

    def native(self,case,packet_bytes=None,render_options=None):
        m=self.module(); alias=Path('Q:/')
        root=alias if alias.exists() and alias.samefile(ROOT) else ROOT
        self.assertTrue(str(root).isascii(),'Native checks require an ASCII checkout/verified alias')
        compiler=root/'.runtime/tools/msys64/ucrt64/bin/gcc.exe'
        self.assertTrue(compiler.is_file(),'Workspace GCC is required; tests never skip')
        base=root/'.runtime/tmp'; base.mkdir(parents=True,exist_ok=True)
        self.assertTrue(base.resolve().is_relative_to(ROOT))
        env=dict(os.environ,TEMP=str(base),TMP=str(base),LANG='C',LC_ALL='C',
                 PATH=str(compiler.parent)+os.pathsep+os.environ.get('PATH',''))
        with tempfile.TemporaryDirectory(prefix='main-source-native-',dir=base) as directory:
            work=Path(directory); packet=work/'frame.z62m'
            packet.write_bytes(self.packet() if packet_bytes is None else packet_bytes)
            exe=work/'main-source.exe'
            built=subprocess.run([str(compiler),'-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic',
                '-I',str(root/'qemu/z62-capturework'),str(root/'tests/native/z62_main_source_probe.c'),
                '-o',str(exe)],env=env,cwd=work,capture_output=True,timeout=60)
            self.assertEqual(built.returncode,0,built.stderr.decode('utf-8','backslashreplace'))
            command=[str(exe),case,str(packet)]
            if render_options is not None: command.extend([*map(str,render_options),str(work/'output.p12')])
            ran=subprocess.run(command,env=env,cwd=work,capture_output=True,timeout=30)
            self.assertEqual(ran.returncode,0,ran.stderr.decode('utf-8','backslashreplace'))
            result=json.loads(ran.stdout); self.assertTrue(result['completed'])
            if render_options is not None: result['packed']=(work/'output.p12').read_bytes()
            return result

    def test_native_python_crc_layout_and_samples(self):
        result=self.native('parse')
        self.assertEqual((result['width'],result['height'],result['stride']),(14,10,32))
        self.assertEqual((result['publish_id'],result['frame_id']),(1,1))

    def test_native_source_lease_backpressure_cancel_stop_reset(self): self.native('lifecycle')
    def test_native_bad_packets_preserve_current_source(self): self.native('rejects')

    def test_full_main_to_capture_pixels_two_scenes_independently_decoded(self):
        from verify_z62_capturework_pixels_evidence import tile_resize
        m=self.module(); lut=np.arange(256,dtype=np.uint16)*4+16
        previous=None
        for publication,color in enumerate(((40,80,160),(210,60,20)),1):
            packet=m.make_packet(Image.new('RGB',(8,8),color),epoch=62,publish_id=publication,
                frame_id=publication-1,virtual_time_ns=(publication-1)*33_333_334)
            meta,raw=m.parse_packet(packet)
            actual=self.native('render',packet,(1514,1342,1514,1006,12,2272,','.join(map(str,lut))))['packed']
            source=np.frombuffer(raw,dtype='<u2').reshape(meta.height,meta.stride//2)[:,:meta.width]
            expected=lut[tile_resize(tile_resize(source,1514,1342),1514,1006)>>8]
            rows=np.frombuffer(actual,dtype=np.uint8).reshape(1006,2272)
            payload=rows[:,:2271].reshape(1006,757,3).astype(np.uint16)
            decoded=np.empty((1006,1514),dtype=np.uint16)
            decoded[:,0::2]=payload[:,:,0]|((payload[:,:,1]&15)<<8)
            decoded[:,1::2]=(payload[:,:,1]>>4)|(payload[:,:,2]<<4)
            np.testing.assert_array_equal(decoded,expected)
            self.assertTrue(np.all(rows[:,2271:]==0xa5))
            if previous is not None: self.assertNotEqual(actual,previous)
            previous=actual


if __name__=='__main__': unittest.main()
