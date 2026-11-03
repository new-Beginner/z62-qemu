"""Run scene -> MAIN envelope -> native read lease -> r86 pixel core offline.

Geometry/LUT are register readback, not factory commit provenance. The native
binary performs ordinary file IO only; it contains no QEMU DMA or IRQ path.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import numpy as np

from record_z62_action_evidence import workspace,digest,require
from probe_z62_capturework_pixels import profile
from verify_z62_capturework_pixels_evidence import tile_resize
from z62_software_camera import Scene
from z62_main_frame import make_packet,parse_packet

ROOT=Path(__file__).resolve().parents[1]


def probe(state_path,output):
    state_path,output=map(workspace,(state_path,output)); output.mkdir(parents=True,exist_ok=False)
    alias=Path('Q:/')
    root=alias if alias.exists() and alias.samefile(ROOT) else ROOT
    require(str(root).isascii(),'Use verified ASCII workspace alias')
    compiler=root/'.runtime/tools/msys64/ucrt64/bin/gcc.exe'
    require(compiler.is_file(),'Workspace GCC required')
    env=dict(os.environ,TEMP=str(root/'.runtime/tmp'),TMP=str(root/'.runtime/tmp'),LANG='C',LC_ALL='C',
             PATH=str(compiler.parent)+os.pathsep+os.environ.get('PATH',''))
    out=root/output.resolve().relative_to(ROOT); executable=out/'main-source-probe.exe'
    command=[str(compiler),'-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic',
        '-I',str(root/'qemu/z62-capturework'),str(root/'tests/native/z62_main_source_probe.c'),'-o',str(executable)]
    compiled=subprocess.run(command,env=env,cwd=out,capture_output=True,timeout=60)
    with (output/'compile.log').open('xb') as handle: handle.write(compiled.stdout+compiled.stderr)
    require(compiled.returncode==0,compiled.stderr.decode('utf-8','backslashreplace'))
    state=json.loads(state_path.read_text(encoding='utf-8')); dimensions,bits,stride,lut=profile(state)
    iw,ih,mw,mh,ow,oh=dimensions
    require(bits==12,'Independent packed12 comparison required')
    frames=[]; scene=Scene(seed=62)
    for publication in (1,2):
        time_ns=(publication-1)*33_333_334; frame_id=time_ns*30//1_000_000_000
        image=scene.render(iw,ih,frame_id)
        packet=make_packet(image,width=iw,height=ih,stride=2*iw,epoch=87,
            publish_id=publication,frame_id=frame_id,virtual_time_ns=time_ns)
        meta,raw=parse_packet(packet)
        packet_path=out/f'frame-{publication}.z62m'; packed_path=out/f'frame-{publication}.p12'
        with packet_path.open('xb') as handle: handle.write(packet)
        ran=subprocess.run([str(executable),'render',str(packet_path),str(mw),str(mh),str(ow),str(oh),
            str(bits),str(stride),','.join(map(str,lut)),str(packed_path)],env=env,cwd=out,
            capture_output=True,timeout=60)
        require(ran.returncode==0,ran.stderr.decode('utf-8','backslashreplace'))
        native=json.loads(ran.stdout)
        require(native['completed'] and native['publish_id']==publication and native['frame_id']==frame_id,
                'Native producer identity differs')
        source=np.frombuffer(raw,dtype='<u2').reshape(ih,meta.stride//2)[:,:iw]
        expected=np.asarray(lut,dtype=np.uint16)[tile_resize(tile_resize(source,mw,mh),ow,oh)>>8]
        packed=packed_path.read_bytes(); rows=np.frombuffer(packed,dtype=np.uint8).reshape(oh,stride)
        payload=rows[:,:ow*12//8].reshape(oh,ow//2,3).astype(np.uint16)
        actual=np.empty((oh,ow),dtype=np.uint16)
        actual[:,0::2]=payload[:,:,0]|((payload[:,:,1]&15)<<8)
        actual[:,1::2]=(payload[:,:,1]>>4)|(payload[:,:,2]<<4)
        mismatches=int(np.count_nonzero(actual!=expected))
        require(mismatches==0 and np.all(rows[:,ow*12//8:]==0xa5),'Independent scene sample/padding comparison failed')
        frames.append({'publication':publication,'frame_id':frame_id,'virtual_time_ns':time_ns,
            'scene':scene.identity,'source_role':'MAIN','input_domain':'linear16 C sRGB approximation',
            'output_domain':'lookup8-high-byte encoded RAW12','packet_sha256':digest(packet_path),
            'packed_sha256':digest(packed_path),'pixels_checked':ow*oh,'sample_mismatches':mismatches,
            'padding_preserved':True,'native':native})
    require(frames[0]['packed_sha256']!=frames[1]['packed_sha256'],'Moving scene must affect output')
    sources=(Path(__file__),ROOT/'tools/z62_main_frame.py',ROOT/'tools/z62_software_camera.py',
        ROOT/'tools/probe_z62_capturework_pixels.py',ROOT/'tools/verify_z62_capturework_pixels_evidence.py',
        ROOT/'qemu/z62-capturework/nikon-z62-main-source.h',
        ROOT/'qemu/z62-capturework/nikon-z62-capturework-pixels.h',ROOT/'tests/native/z62_main_source_probe.c')
    snapshot=output/'source-snapshot'; snapshot.mkdir()
    hashes={}
    for path in sources:
        relative=path.resolve().relative_to(ROOT).as_posix(); target=snapshot/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        data=path.read_bytes()
        with target.open('xb') as handle: handle.write(data)
        hashes[relative]=hashlib.sha256(data).hexdigest()
    result={'schema':1,'version':'2026.11.04-main-source-r87','completed':True,
        'scope':'standalone scene MAIN producer/read lease and pixel core; no QEMU device integration',
        'dimensions':dimensions,'bits':bits,'stride':stride,'observed_state_sha256':digest(state_path),
        'source_sha256':hashes,'executable_sha256':digest(executable),'frames':frames,
        'total_pixels_checked':sum(f['pixels_checked'] for f in frames),'scene_motion_observed':True,
        'QEMU_DMA_performed':False,'completion_or_IRQ_injected':False,'camera_accessed':False,
        'factory_MAIN_source_or_commit_provenance_verified':False,'LUT_inverse_integrated':False,
        'factory_mode_roundtrip_AF_or_flash_safety_verified':False}
    with (output/'result.json').open('x',encoding='utf-8') as handle: json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); probe(args.state,args.output)
