"""Native r104: four actual CW frames, frozen linear domains and NV12 DMA."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess
from unittest.mock import patch
import numpy as np
import probe_z62_capturework_device as cw
import probe_z62_preview as preview
import run_z62_capturework_preview as hardware
from z62_main_frame import parse_packet
from record_z62_action_evidence import workspace,digest,require

GEOMETRY=((64,48,64,0x1000),(32,24,32,0x1000),(16,12,16,0x1000))
OUTPUTS=tuple(tuple(base+i*0x400000 for i in range(4)) for base in (0xea000100,0xd4e00100,0xe3000100))


@contextmanager
def session(binary,proof,enabled=True):
    previous=subprocess.Popen
    class PreviewProcess(previous):
        def __init__(self,command,*args,**kwargs):
            command=list(command)+['-global','nikon-z72-boot-config.z62-preview=on',
                '-global','nikon-z72-boot-config.z62-card-detect=on']
            if enabled:command+=['-global','nikon-z72-input-config.z62-capturework-preview=on']
            proof.setdefault('effective_commands',[]).append(command)
            super().__init__(command,*args,**kwargs)
    with patch.object(cw.subprocess,'Popen',PreviewProcess),cw.session(binary,True,proof) as s:
        paths=[]
        for child in s.query('qom-list',{'path':'/machine/unattached'}):
            if child['type']=='child<nikon-z72-boot-config>':
                path='/machine/unattached/'+child['name']
                if s.get('master-role',path):paths.append(path)
        require(len(paths)==1,'Single master preview device required');s.boot=paths[0]
        yield s


def cohort(s):return json.loads(s.get('capturework-cohort-status'))
def source(s):return json.loads(s.get('capturework-preview-status',s.boot))
def counter(s,name):return s.get('preview-'+name,s.boot)


def configure_preview(s):
    for i,address in enumerate(cw.raw.SLOTS):s.write(0x20380310+i*4,address)
    for channel,(width,height,stride,uv) in enumerate(GEOMETRY,3):
        base=0x20100400+channel*0x40
        for offset,value in ((0,0x09000201),(0x10,stride),(0x14,stride),(0x20,(height<<16)|width),(0x28,uv)):
            s.write(base+offset,value)
        for frame,address in enumerate(OUTPUTS[channel-3]):s.write(0x20102200+frame*64+channel*4,address)
    for address,value in ((0x20380048,0x05ea03ee),(0x20380300,0),(0x2038030c,2272),
        (0x20380020,0x1002),(0x20380008,1),(0x20100014,8),(0x20100004,1),
        (0x20102100,0x121),(0x20102600,0x305),(0x20102604,1002),(0x20102608,1)):
        s.write(address,value)


def fill(s):
    for channel,(_,height,stride,uv) in enumerate(GEOMETRY):
        for address in OUTPUTS[channel]:
            for start,size in ((address,stride*height),(address+uv,stride*height//2)):
                s.access(f'memset {start-16:#x} {size+32:#x} 0xa5')


def check_guard(s,start,length,label):
    prefix=s.read(start-16,16);suffix=s.read(start+length,16)
    require(prefix==b'\xa5'*16 and suffix==b'\xa5'*16,
        f'{label} guard at {start:#x}+{length:#x}: prefix={prefix.hex()} suffix={suffix.hex()}')


def initial_guards(s):
    for channel,(_,height,stride,uv) in enumerate(GEOMETRY):
        for frame,address in enumerate(OUTPUTS[channel]):
            check_guard(s,address,height*stride,f'Initial frame{frame} ch{channel} Y')
            check_guard(s,address+uv,height*stride//2,f'Initial frame{frame} ch{channel} UV')


def linear(packet,dims,stride):
    data=bytearray(cw.expected(packet,dims,stride,[i*16+8 for i in range(256)]))
    for y in range(1006):data[y*stride+stride-1]=0
    return bytes(data)


def color_pixels(packed):
    def value(x,y):
        p=y*2272+(x//2)*3
        return (packed[p+1]>>4)|(packed[p+2]<<4) if x&1 else packed[p]|((packed[p+1]&15)<<8)
    def tone(v):
        v=max(0,min(1,(v-64)/(4095-64)))
        return round(255*(12.92*v if v<=.0031308 else 1.055*v**(1/2.4)-.055))
    r,g,b=tone(value(2,2)),tone((value(3,2)+value(2,3)+1)//2),tone(value(3,3))
    return (max(16,min(235,((66*r+129*g+25*b+128)>>8)+16)),
        max(16,min(240,((-38*r-74*g+112*b+128)>>8)+128)),
        max(16,min(240,((112*r-94*g-18*b+128)>>8)+128)))


def verify_outputs(s,publications,packets,dims,stride):
    total=0
    for frame,publication in enumerate(publications):
        y,u,v=color_pixels(linear(packets[publication],dims,stride))
        for channel,(width,height,out_stride,uv) in enumerate(GEOMETRY):
            address=OUTPUTS[channel][frame];size=height*out_stride
            require(s.read(address,size)==bytes([y])*size,'Actual cohort Y output differs from independent C reference')
            require(s.read(address+uv,size//2)==bytes([u,v])*(size//4),'Actual cohort UV output differs')
            for start,length in ((address,size),(address+uv,size//2)):
                check_guard(s,start,length,f'Output frame{frame} ch{channel}')
            total+=size*3//2
    return total


def check(binary,state_path,output):
    binary,state_path,output=map(workspace,(binary,state_path,output));require(not output.exists(),'Use new cohort preview output')
    output.parent.mkdir(parents=True,exist_ok=True)
    proof={'schema':1,'completed':False,'artifact_root':str(output.parent),'camera_accessed':False,
        'firmware_executed':False,'source_sha256':{str(Path(p)):digest(Path(p)) for p in (__file__,cw.__file__,preview.__file__,hardware.__file__)}}
    try:
        help_result=subprocess.run([str(binary),'-device','nikon-z72-input-config,help'],capture_output=True,timeout=20)
        require(help_result.returncode==0 and b'z62-capturework-preview' in help_result.stdout+help_result.stderr,
            'Missing actual CW preview source property')
        proof['binary_sha256']=hardware.verify_build(binary)['binary_sha256'];proof['state_sha256']=digest(state_path)
        dims,bits,stride,lut=cw.profile(json.loads(state_path.read_text(encoding='utf-8')))
        with session(binary,proof,False) as s:
            configure_preview(s);cw.configure(s,dims,bits,stride,lut)
            cw.upload(s,dims,1);cw.advance(s,1);cw.idle(s)
            require(not cohort(s)['enabled'] and counter(s,'batches')==0 and source(s)['accepted']==0,
                'Default-off source notified or generated preview')
        proof['default_off']=True;packets={};colors={}
        with session(binary,proof) as s:
            configure_preview(s);cw.configure(s,dims,bits,stride,lut);fill(s);cw.fill(s,stride*1006);initial_guards(s);cw.idle(s)
            require(counter(s,'batches')==0 and cohort(s)['cohorts']==0,'Registers/missing input produced a cohort')
            def produce(publication,expected_completed):
                color=((publication*17+23)%220+16,(publication*29+41)%210+16,(publication*37+67)%200+16)
                packet=cw.upload(s,dims,publication,color);packets[publication]=packet;colors[publication]=color
                cw.advance(s,expected_completed);cw.acknowledge(s)
            for p in range(1,4):
                produce(p,p);require(counter(s,'batches')==0 and source(s)['accepted']==0,'Partial three-slot input produced a preview')
            produce(4,4);cw.idle(s)
            require(counter(s,'batches')==1 and counter(s,'outputs')==12 and source(s)['accepted']==1,'Four-frame preview did not complete')
            first=source(s);require([r['publication'] for r in first['frames']]==[1,2,3,4],'Source identities were duplicated or reordered')
            for frame in first['frames']:
                require(frame['linear_sha256']==hashlib.sha256(linear(packets[frame['publication']],dims,stride)).hexdigest(),
                    'Full frozen linear source differs from independent quantization')
            checked=verify_outputs(s,[1,2,3,4],packets,dims,stride)
            for p in range(5,13):produce(p,p)
            require(counter(s,'batches')==1 and source(s)['accepted']==2 and source(s)['blocked']==1,
                'Unconsumed source/output backpressure lost or queued data')
            require([r['publication'] for r in source(s)['frames']]==[5,6,7,8],'Blocked third cohort replaced owned source')
            preview.acknowledge(s);cw.idle(s)
            require(counter(s,'batches')==2,'Pending second cohort was not consumed')
            checked+=verify_outputs(s,[5,6,7,8],packets,dims,stride)
            require(counter(s,'batches')==2 and s.get('raw-accepted')==0 and s.get('raw-stream-frames',s.boot)==0,
                'Source bridge changed a legacy acquisition counter')
            proof['first_source']=first;proof['second_source']=source(s)
            preview.acknowledge(s)
            cw.upload(s,dims,13,(255,0,0));s.write(0x2006800c,0x200);cw.idle(s)
            require(cw.status(s)['completed']==12 and not source(s)['owns_source'],'Stop retained stale source or completed cancelled work')
            s.write(0x20068008,0x200)
            for p in range(14,17):
                produce(p,p-1);require(counter(s,'batches')==2,'Restart reused pre-stop slots')
            produce(17,16);cw.idle(s)
            require(counter(s,'batches')==3 and [r['publication'] for r in source(s)['frames']]==[14,15,16,17],
                'Fresh post-stop four-slot source did not replace the cancelled epoch')
            checked+=verify_outputs(s,[14,15,16,17],packets,dims,stride)
            proof['third_source']=source(s)
            require(json.loads(s.get('capturework-cohort-status',cw.raw.SLAVE))['collected_frames']==0,'Slave consumed master input')
            s.query('system_reset');cw.idle(s)
            require(cohort(s)['cohorts']==0 and source(s)['accepted']==0 and not source(s)['owns_source']
                and counter(s,'batches')==0,'Reset retained source/cohort/output state')
        for publication,packet in packets.items():
            with (output.parent/f'source-{publication}.z62m').open('xb') as handle:handle.write(packet)
        proof.update(actual_CW_DMA_frames=16,actual_preview_batches=3,actual_preview_outputs=36,
            NV12_bytes_independently_verified=checked,four_distinct_frames_required=True,
            frozen_transfer_linear_domain_verified=True,output_backpressure_and_no_credits=True,
            stop_requires_four_fresh_slots=True,reset_and_slave_isolation=True,
            legacy_RAW_counters_unchanged=True,metadata_event6_emitted=False,completed=True)
    except Exception as exc:proof['failure']={'type':type(exc).__name__,'message':str(exc)}
    with output.open('x',encoding='utf-8') as handle:json.dump(proof,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in proof.items() if k not in ('source_sha256','effective_commands','sessions')},ensure_ascii=False),flush=True)
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--state',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=check(args.qemu,args.state,args.output);raise SystemExit(0 if result['completed'] else 1)
