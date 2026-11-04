"""Native r103: actual completed input -> frozen finite mean batches and DMA."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import struct
import subprocess
from unittest.mock import patch
import numpy as np
import probe_z62_capturework_device as cw
import probe_z62_capturework_finite as prior
import probe_z62_finite_stats as finite
import probe_z62_input_readout as readout
import run_z62_readout_statistics as hardware
from z62_main_frame import parse_packet
from record_z62_action_evidence import workspace,digest,require


@contextmanager
def session(binary,proof,enabled=True):
    previous=subprocess.Popen
    class StatisticsProcess(previous):
        def __init__(self,command,*args,**kwargs):
            command=list(command)+['-global','nikon-z72-input-config.z62-input-readout=on',
                '-global','nikon-z62-sensor-config.functional-raw-completion=on']
            if enabled:command+=['-global','nikon-z72-input-config.z62-readout-statistics=on']
            proof.setdefault('effective_commands',[]).append(command)
            super().__init__(command,*args,**kwargs)
    with patch.object(cw.subprocess,'Popen',StatisticsProcess),prior.session(binary,proof,True) as s:yield s


def status(s):return json.loads(s.get('input-readout-statistics-status'))


def setup(s,dims,bits,stride,lut):
    cw.configure(s,dims,bits,stride,lut);cw.upload(s,dims,1);cw.advance(s,1);cw.acknowledge(s)
    s.write(0x2006800c,0x20d)
    for address,value in ((0x20069d00,136<<16),(0x20069d04,2020<<16),
        (0x20069e78,136<<16),(0x20069e7c,2020<<16),(0x20068100,4),(0x20068104,4),
        (0x20065400,0x10011),(0x20065504,0x8000),(0x2006550c,2)):
        s.write(address,value)
    finite.configure(s);finite.arm(s)


def expected(packet):
    meta,payload=parse_packet(packet)
    pixels=np.frombuffer(payload,dtype='<u2').reshape(meta.height,meta.stride//2)[:,:meta.width]>>4
    result=bytearray(768)
    for y in range(12):
        for x in range(30):
            area=pixels[y*136//12:(y+1)*136//12,x*2020//30:(x+1)*2020//30]
            struct.pack_into('<H',result,y*64+x*2,(int(area.astype(np.uint64).sum())+area.size//2)//area.size)
    return bytes(result)


def inspect_dma(s,expected_bytes,address,outputs):
    data=s.read(address,768)
    require(data==expected_bytes,'Actual finite DMA differs from independent input means')
    require(s.read(address+768,8)==b'\xa5'*8,'Finite output exceeded its declared extent')
    outputs.extend(data)


def check(binary,state_path,output):
    binary,state_path,output=map(workspace,(binary,state_path,output));require(not output.exists(),'Use new native statistics output')
    output.parent.mkdir(parents=True,exist_ok=True)
    proof={'schema':1,'completed':False,'artifact_root':str(output.parent),'camera_accessed':False,
        'firmware_executed':False,'new_RAW_acquisitions':False,'source_sha256':{
            str(Path(p)):digest(Path(p)) for p in (__file__,cw.__file__,prior.__file__,finite.__file__,readout.__file__,hardware.__file__)}}
    try:
        help_result=subprocess.run([str(binary),'-device','nikon-z72-input-config,help'],capture_output=True,timeout=20)
        require(help_result.returncode==0 and b'z62-readout-statistics' in help_result.stdout+help_result.stderr,
            'Missing real readout-statistics property')
        proof['binary_sha256']=hardware.verify_build(binary)['binary_sha256'];proof['state_sha256']=digest(state_path)
        dims,bits,stride,lut=cw.profile(json.loads(state_path.read_text(encoding='utf-8')))
        with session(binary,proof,False) as s:
            setup(s,dims,bits,stride,lut);finite.frame(s)
            require(not status(s)['enabled'] and finite.get(s,'frames')==1 and status(s)['batches']==0,
                'Default-off option replaced the legacy retained-CW source')
        proof['default_off_preserves_retained_CW_source']=True
        with session(binary,proof,True) as s:
            setup(s,dims,bits,stride,lut);finite.frame(s)
            require(prior.status(s)['captured']==1 and finite.get(s,'frames')==0 and finite.get(s,'reason')=='source',
                'Old CW image bypassed the explicit new input requirement')
            require(readout.status(s)['eligible'] and not status(s)['valid'],'Finite source phase not eligible or fabricated a cache')
            s.access(f'memset {finite.START:#x} {61*finite.PITCH:#x} 0xa5')
            first=readout.packet(1);readout.publish(s,first);cw.idle(s)
            require(status(s)['valid'] and status(s)['latest_publication']==1 and finite.get(s,'frames')==0,
                'Source did not complete, or produced statistics without finite sampling')
            finite.frame(s);one=bytearray();inspect_dma(s,expected(first),finite.START,one)
            require(status(s)['batch_publication']==1 and status(s)['batches']==1,'First batch source not frozen')
            second=readout.packet(2,(210,60,20));readout.publish(s,second);cw.idle(s)
            require(status(s)['latest_publication']==2 and status(s)['batch_publication']==1,
                'Later input replaced an owned finite batch')
            for i in range(1,61):
                finite.frame(s);inspect_dma(s,expected(first),finite.START+i*finite.PITCH,one)
            require(finite.get(s,'frames')==61 and finite.get(s,'batches')==1,'First actual 61-DMA batch incomplete')
            third=readout.packet(3,(120,90,40));readout.publish(s,third)
            require(readout.status(s)['pending'] and status(s)['latest_publication']==2,
                'Uncompleted next lease overwrote the completed source cache')
            s.write(0x20068270,0xa0);finite.configure(s,pitch=0,bank=1);s.write(0x20068100,8)
            finite.frame(s);two=bytearray();inspect_dma(s,expected(second),finite.START,two)
            require(status(s)['batch_publication']==2,'Next request did not select the last completed image')
            cw.idle(s);require(status(s)['latest_publication']==3 and status(s)['batch_publication']==2,
                'In-flight input changed the running second batch')
            for _ in range(60):
                finite.frame(s);inspect_dma(s,expected(second),finite.START,two)
            require(finite.get(s,'frames')==122 and finite.get(s,'batches')==2 and s.get('raw-accepted')==0,
                'Second actual batch incomplete or inline data impersonated RAW acquisition')
            proof['batches']=[{'publication':1,'samples':61,'source':'source-1.z62m','outputs':'batch-1.scalar'},
                {'publication':2,'samples':61,'source':'source-2.z62m','outputs':'batch-2.scalar'}]
            for name,data in (('source-1.z62m',first),('source-2.z62m',second),('batch-1.scalar',one),('batch-2.scalar',two)):
                with (output.parent/name).open('xb') as handle:handle.write(data)
            proof['batch_status']=status(s)
            readout.publish(s,readout.packet(4));s.write(0x2006800c,0x10);cw.idle(s)
            require(not status(s)['valid'] and not readout.status(s)['pending'] and readout.status(s)['completed']==3,
                'Stop kept a stale statistics source or completed cancelled input')
            finite.arm(s);finite.frame(s)
            require(finite.get(s,'frames')==122 and finite.get(s,'reason')=='source','Re-enable reused the last phase source')
            readout.publish(s,readout.packet(5));cw.idle(s)
            bad=finite.END-60*finite.PITCH-512;finite.configure(s,destination=bad)
            s.access(f'memset {bad:#x} 768 0x5a');s.write(0x20068100,8);finite.frame(s)
            require(finite.get(s,'frames')==122 and finite.get(s,'reason')=='destination' and s.read(bad,768)==b'\x5a'*768,
                'Invalid full-batch destination wrote partial data')
            finite.configure(s);readout.publish(s,readout.packet(6));s.query('system_reset');cw.idle(s)
            require(not status(s)['valid'] and status(s)['batches']==0 and finite.get(s,'frames')==0
                and not readout.status(s)['pending'],'Reset kept cache/batch/pending input')
        proof.update(actual_statistics_DMA_samples=122,independently_checked_DMA_bytes=93696,
            no_retained_CW_fallback=True,completed_cache_separate_from_pending_lease=True,
            frozen_batches_and_latest_selection=True,stop_requires_new_input=True,
            cancelled_input_no_completion=True,full_batch_preflight=True,reset_clears_source_and_batch=True,completed=True)
    except Exception as exc:proof['failure']={'type':type(exc).__name__,'message':str(exc)}
    with output.open('x',encoding='utf-8') as handle:json.dump(proof,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in proof.items() if k not in ('source_sha256','effective_commands','sessions')},ensure_ascii=False),flush=True)
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--state',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();proof=check(args.qemu,args.state,args.output);raise SystemExit(0 if proof['completed'] else 1)
