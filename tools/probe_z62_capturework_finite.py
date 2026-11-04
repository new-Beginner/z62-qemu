"""Native r98: finite sample DMAs retain an actual completed CW image identity.

This is not a test that manufactures 61 new RAW acquisitions. It verifies the
explicit retained-scene finite model and its independent data ownership.
"""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import struct
import subprocess
from unittest.mock import patch
import numpy as np
import probe_z62_capturework_device as cw
import probe_z62_finite_stats as finite
import run_z62_capturework_finite as hardware
from z62_main_frame import parse_packet
from record_z62_action_evidence import workspace,digest,require


@contextmanager
def session(binary,proof,enabled=True):
    original=subprocess.Popen
    class FiniteProcess(original):
        def __init__(self,command,*args,**kwargs):
            command=list(command)+['-global','nikon-z72-input-config.z62-capturework-policy0=on',
                '-global','nikon-z72-input-config.functional-finite-stats=on',
                '-global','nikon-z72-boot-config.z62-finite-stats=on',
                '-global','nikon-z72-boot-config.z62-card-detect=on']
            if enabled:command+=['-global','nikon-z72-input-config.z62-capturework-finite=on']
            super().__init__(command,*args,**kwargs)
    with patch.object(cw.subprocess,'Popen',FiniteProcess),cw.session(binary,True,proof) as s:yield s


def status(s):return json.loads(s.get('capturework-finite-status'))


def expected(packet,dims):
    meta,pixels=parse_packet(packet)
    raw=np.frombuffer(pixels,dtype='<u2').reshape(meta.height,meta.stride//2)[:,:meta.width]
    chosen=cw.tile_resize(cw.tile_resize(raw,dims[2],dims[3]),dims[4],dims[5])
    linear=(chosen.astype(np.uint32)//256)*16+8;out=bytearray(768)
    for y in range(12):
        for x in range(30):
            values=linear[y*1006//12:(y+1)*1006//12,x*1514//30:(x+1)*1514//30]
            struct.pack_into('<H',out,y*64+x*2,(int(values.sum())+values.size//2)//values.size)
    return bytes(out)


def save_batch(s,proof,packet,dims,batch,pitch=finite.PITCH):
    expected_bytes=expected(packet,dims);data=bytearray()
    for index in range(61):
        actual=s.read(finite.START+index*pitch,finite.SIZE)
        require(actual==expected_bytes,'Independent retained-image mean differs')
        require(s.read(finite.START+index*pitch+finite.SIZE,8)==b'\xa5'*8,'Finite DMA exceeded output span')
        data.extend(actual)
    root=Path(proof['artifact_root']);source=root/f'batch-{batch}.z62m';path=root/f'batch-{batch}.scalar'
    with source.open('xb') as handle:handle.write(packet)
    with path.open('xb') as handle:handle.write(data)
    proof.setdefault('batches',[]).append({'batch':batch,'source':status(s),'MAIN':source.name,
        'MAIN_sha256':digest(source),'outputs':path.name,'outputs_sha256':digest(path),'samples':61,'bytes':len(data)})


def check(binary,state_path,output):
    binary,state_path,output=map(workspace,(binary,state_path,output))
    require(not output.exists(),'Use new finite-source output');output.parent.mkdir(parents=True,exist_ok=True)
    proof={'schema':1,'completed':False,'camera_accessed':False,'firmware_executed':False,
        'artifact_root':str(output.parent),'binary_sha256':digest(binary),'state_sha256':digest(state_path),
        'source_sha256':{str(Path(p)):digest(Path(p)) for p in (__file__,cw.__file__,finite.__file__,hardware.__file__)}}
    try:
        checked=subprocess.run([str(binary),'-device','nikon-z72-input-config,help'],capture_output=True,timeout=20)
        require(checked.returncode==0 and b'z62-capturework-finite' in checked.stdout+checked.stderr,
            'Missing real retained finite-source property')
        hardware.verify_build(binary)
        dims,bits,stride,lut=cw.profile(json.loads(state_path.read_text(encoding='utf-8')))
        def source_config(s):cw.configure(s,dims,bits,stride,lut)
        with session(binary,proof,False) as s:
            source_config(s);cw.upload(s,dims,1);cw.advance(s,1);finite.configure(s);finite.arm(s);finite.frame(s)
            require(finite.get(s,'frames')==0 and finite.get(s,'reason')=='source' and status(s)['captured']==0,
                'Default-off source bypassed legacy RAW ownership')
        proof['default_off_preserves_legacy_gate']=True
        with session(binary,proof) as s:
            source_config(s);finite.configure(s);finite.arm(s);finite.frame(s)
            require(finite.get(s,'frames')==0 and finite.get(s,'reason')=='source','Missing image fabricated finite samples')
            first=cw.upload(s,dims,1);cw.advance(s,1)
            s.write(0x2006800c,0x20d)
            require(status(s)['valid'] and status(s)['captured']==1,'Acquisition stop dropped independent retained image')
            s.access(f'memset {finite.START:#x} {61*finite.PITCH:#x} 0xa5')
            finite.arm(s);finite.frame(s,10)
            require(finite.get(s,'frames')==10 and finite.get(s,'batches')==0,'Early finite batch completion')
            s.write(0x20068008,0x20d);cw.acknowledge(s)
            second=cw.upload(s,dims,2,(210,60,20));cw.advance(s,2)
            require(status(s)['captured']==2 and status(s)['batch_publication']==1,'Later acquisition replaced an owned finite batch')
            s.write(0x2006800c,0x20d);finite.frame(s,51)
            require(finite.get(s,'frames')==61 and finite.get(s,'batches')==1,'Declared finite batch incomplete')
            save_batch(s,proof,first,dims,1)
            finite.frame(s,3);require(finite.get(s,'frames')==61,'Completed batch replayed without a new request')
            s.write(0x20068270,0xa0);s.write(0x2006800c,0x10);finite.arm(s);finite.frame(s,61)
            require(finite.get(s,'frames')==122 and finite.get(s,'batches')==2 and status(s)['batch_publication']==2,
                'New finite request did not select the latest actual image')
            save_batch(s,proof,second,dims,2)
            require(s.get('raw-accepted')==0 and status(s)['captured']==2,'Finite sample count masqueraded as RAW acquisition count')
            s.query('system_reset');require(not status(s)['valid'] and status(s)['captured']==0,'Reset retained stale finite source')
        proof['two_actual_inputs_122_sample_DMAs_and_frozen_batch_identity']=True
        with session(binary,proof) as s:
            source_config(s);cw.upload(s,dims,1);s.write(0x20068000,0x20d);cw.idle(s)
            finite.configure(s);finite.arm(s);finite.frame(s)
            require(status(s)['captured']==0 and finite.get(s,'frames')==0,'Cancelled acquisition became a finite image')
        proof['cancelled_acquisition_not_retained']=True
        with session(binary,proof) as s:
            source_config(s);s.write(0x20069a50,finite.START);s.write(0x20068104,0x80)
            cw.upload(s,dims,1);cw.advance(s,1);before=s.read(finite.START,64)
            finite.configure(s);finite.arm(s);finite.frame(s)
            require(finite.get(s,'frames')==0 and finite.get(s,'reason')=='memory' and s.read(finite.START,64)==before,
                'Finite descriptor overwrote its encoded source')
        proof['source_output_alias_rejected']=True
        require(all(code==0 for code in proof['process_exit_codes']),'Native child did not exit normally')
        proof['completed']=True
    except Exception as exc:proof['failure']={'type':type(exc).__name__,'message':str(exc)}
    with output.open('x',encoding='utf-8') as handle:json.dump(proof,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:proof.get(k) for k in ('completed','failure','binary_sha256','default_off_preserves_legacy_gate',
        'two_actual_inputs_122_sample_DMAs_and_frozen_batch_identity','process_exit_codes')},ensure_ascii=False),flush=True)
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--state',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=check(args.qemu,args.state,args.output)
    raise SystemExit(0 if result['completed'] else 1)
