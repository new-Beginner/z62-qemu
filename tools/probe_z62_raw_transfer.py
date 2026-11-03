"""Bind observed RAW transfer to two existing MAIN frames and decode numerically.

Ordinary files and a standalone C executable only. LUT reconstruction is
quantized interval midpoint, not a physical lossless inverse or QEMU DMA.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

import numpy as np

from record_z62_action_evidence import workspace,digest,require
from probe_z62_capturework_pixels import profile
from verify_z62_capturework_pixels_evidence import tile_resize
from z62_main_frame import parse_packet
from z62_raw_transfer import RawTransfer

ROOT=Path(__file__).resolve().parents[1]


def probe(state_path,main_result,output):
    state_path,main_result,output=map(workspace,(state_path,main_result,output))
    state=json.loads(state_path.read_text(encoding='utf-8'))
    previous=json.loads(main_result.read_text(encoding='utf-8'))
    require(previous['completed'] and previous['observed_state_sha256']==digest(state_path),
            'Use the complete identity-bound MAIN case')
    for relative,expected in previous['source_sha256'].items():
        require(digest(main_result.parent/'source-snapshot'/relative)==expected,'Archived MAIN source changed')
    dimensions,bits,stride,lut=profile(state); iw,ih,mw,mh,ow,oh=dimensions
    transfer=RawTransfer(bits,'lookup8-high-byte',lut)
    output.mkdir(parents=True,exist_ok=False)
    alias=Path('Q:/'); root=alias if alias.exists() and alias.samefile(ROOT) else ROOT
    require(str(root).isascii(),'Use verified ASCII workspace alias')
    out=root/output.resolve().relative_to(ROOT)
    compiler=root/'.runtime/tools/msys64/ucrt64/bin/gcc.exe'; require(compiler.is_file(),'Workspace GCC required')
    env=dict(os.environ,TEMP=str(root/'.runtime/tmp'),TMP=str(root/'.runtime/tmp'),LANG='C',LC_ALL='C',
             PATH=str(compiler.parent)+os.pathsep+os.environ.get('PATH',''))
    executable=out/'raw-transfer-probe.exe'
    command=[str(compiler),'-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic',
        '-I',str(root/'qemu/z62-capturework'),str(root/'tests/native/z62_raw_transfer_probe.c'),'-o',str(executable)]
    built=subprocess.run(command,env=env,cwd=out,capture_output=True,timeout=60)
    with (output/'compile.log').open('xb') as handle: handle.write(built.stdout+built.stderr)
    require(built.returncode==0,built.stderr.decode('utf-8','backslashreplace'))
    descriptor=out/'transfer.z62t'
    with descriptor.open('xb') as handle: handle.write(transfer.to_bytes())
    require(RawTransfer.from_bytes(descriptor.read_bytes())==transfer,'Descriptor roundtrip differs')
    frames=[]
    for prior in previous['frames']:
        publication=prior['publication']
        original=workspace(main_result.parent/f'frame-{publication}.z62m')
        require(digest(original)==prior['packet_sha256'],'MAIN packet identity differs')
        meta,raw=parse_packet(original.read_bytes())
        require((meta.width,meta.height,meta.publish_id,meta.frame_id,meta.virtual_time_ns)==
            (iw,ih,publication,prior['frame_id'],prior['virtual_time_ns']),'MAIN metadata differs')
        packet=root/original.resolve().relative_to(ROOT)
        packed=out/f'frame-{publication}.p12'; linear=out/f'frame-{publication}-linear.raw'
        ran=subprocess.run([str(executable),'scene',str(descriptor),str(packet),str(mw),str(mh),
            str(ow),str(oh),str(stride),str(packed),str(linear)],env=env,cwd=out,
            capture_output=True,timeout=60)
        require(ran.returncode==0,ran.stderr.decode('utf-8','backslashreplace'))
        require(json.loads(ran.stdout)['completed'],'Native transfer run incomplete')
        source=np.frombuffer(raw,dtype='<u2').reshape(ih,meta.stride//2)[:,:iw]
        selected=tile_resize(tile_resize(source,mw,mh),ow,oh).astype(np.uint32)
        quantum=transfer.input_quantum; lower=selected//quantum*quantum
        expected=lower+quantum//2
        rows=np.frombuffer(linear.read_bytes(),dtype=np.uint8).reshape(oh,2*ow+4)
        actual=rows[:,:2*ow].copy().view('<u2').reshape(oh,ow)
        mismatches=int(np.count_nonzero(actual!=expected))
        max_error=int(np.abs(actual.astype(np.int32)-selected.astype(np.int32)).max())
        require(mismatches==0 and max_error<=quantum//2 and np.all(rows[:,2*ow:]==0xa5),
                'Independent quantized reconstruction failed')
        require(digest(packed)==prior['packed_sha256'],'Frozen transfer changed the r87 forward output')
        frames.append({'publication':publication,'frame_id':meta.frame_id,'virtual_time_ns':meta.virtual_time_ns,
            'MAIN_packet_sha256':prior['packet_sha256'],'transfer_sha256':digest(descriptor),
            'packed_sha256':digest(packed),'linear16_sha256':digest(linear),'pixels_checked':ow*oh,
            'sample_mismatches':mismatches,'max_abs_linear16_error':max_error,'input_quantum':quantum,
            'padding_preserved':True,'r87_forward_bytes_preserved':True})
    names=('tools/probe_z62_raw_transfer.py','tools/z62_raw_transfer.py','tools/z62_main_frame.py',
        'tools/probe_z62_capturework_pixels.py','tools/verify_z62_capturework_pixels_evidence.py',
        'qemu/z62-capturework/nikon-z62-raw-transfer.h','qemu/z62-capturework/nikon-z62-main-source.h',
        'qemu/z62-capturework/nikon-z62-capturework-pixels.h','tests/native/z62_raw_transfer_probe.c',
        'tests/test_z62_raw_transfer.py')
    hashes={}
    for relative in names:
        source=ROOT/relative; target=output/'source-snapshot'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as handle: handle.write(source.read_bytes())
        hashes[relative]=digest(source)
    version=subprocess.run([str(compiler),'--version'],env=env,capture_output=True,check=True,timeout=15)
    result={'schema':1,'version':'2026.11.04-raw-transfer-r88','completed':True,
        'scope':'immutable C RAW domain descriptor and quantized midpoint reconstruction, standalone only',
        'state_sha256':digest(state_path),'MAIN_result_sha256':digest(main_result),
        'transfer_sha256':digest(descriptor),'compiler_version':version.stdout.decode('utf-8').splitlines()[0],
        'executable_sha256':digest(executable),'source_sha256':hashes,'frames':frames,
        'total_pixels_checked':sum(row['pixels_checked'] for row in frames),
        'lossy_low_input_bits':8,'linear16_reconstruction':'upper midpoint of the identified 256-value input bin',
        'exact_original_sample_recovery':False,'QEMU_device_integrated':False,
        'factory_commit_provenance_verified':False,'QEMU_DMA_or_IRQ_performed':False,
        'downstream_ISP_integration_complete':False,'camera_accessed':False,'AF_verified':False}
    with (output/'result.json').open('x',encoding='utf-8') as handle: json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True); parser.add_argument('--main-result',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); probe(args.state,args.main_result,args.output)
