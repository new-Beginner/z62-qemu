"""Native r93 real MAIN -> LUT/FIR records -> DMA -> event96 validation.

Fixtures declare their own nonzero numerical inputs; they never turn the
original zero resource into a successful firmware configuration.
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
import run_z62_capture_group as hardware
from z62_main_frame import parse_packet
from record_z62_action_evidence import workspace,digest,require


@contextmanager
def session(binary,proof,enabled=True):
    original=subprocess.Popen
    class GroupProcess(original):
        def __init__(self,command,*args,**kwargs):
            command=list(command)+['-global','nikon-z72-input-config.z62-capturework-policy0=on']
            if enabled:command+=['-global','nikon-z72-input-config.z62-capture-group=on']
            super().__init__(command,*args,**kwargs)
    with patch.object(cw.subprocess,'Popen',GroupProcess),cw.session(binary,True,proof) as s:yield s


def status(s,path=cw.raw.MASTER):return json.loads(s.get('capture-group-status',path))


def configure(s,profile,dims,bits,stride,lut):
    cw.configure(s,dims,bits,stride,lut)
    for offset,value in profile.items():s.write(0x2006b800+offset,value)
    for address,value in ((0x20068000,0x20),(0x20068004,0x20),(0x20068010,0x20),
        (0x20068100,0x10),(0x20068104,0x10),(0x20068260,1),(0x20068008,0x20)):
        s.write(address,value)
    for bank in range(2):
        for f in range(3):
            base=profile[0x350+bank*16+f*256];pitch=profile[0x380+f*256]
            # Only ordinary model RAM ranges in the declared fixture are filled.
            if 0x891b8000<=base<0x891c8000:s.access(f'memset {base:#x} {pitch*5:#x} 0xa5')


def expected(packet,profile,cursor,bank,marker=None):
    meta,payload=parse_packet(packet)
    raw=np.frombuffer(payload,dtype='<u2').reshape(meta.height,meta.stride//2)[:,:meta.width].astype(np.uint64)
    curve=np.array([profile[0x80+4*i] for i in range(65)],dtype=np.uint64)
    index=raw//1024;fraction=raw%1024
    linear=((curve[index]*(1024-fraction)+curve[index+1]*fraction)//1024//16).astype(np.int64)
    planes=[linear,linear*linear]
    for f in range(3):
        coefficients=[]
        for tap in range(8):
            v=profile[0x20+f*32+tap*4];bits=7 if tap else 8
            coefficients.append(v-(1<<bits) if v&(1<<(bits-1)) else v)
        response=np.zeros_like(linear);magnitude=sum(map(abs,coefficients))
        for tap,c in enumerate(coefficients):
            if c:response+=c*linear[:,np.clip(np.arange(meta.width)+tap-3,0,meta.width-1)]
        planes.append(np.abs(response)//magnitude)
    dw,dh=profile[0x208],profile[0x20c];families=profile[0x22c]
    def record(rect,kind):
        x,y,w,h=rect;x0=x*meta.width//dw;y0=y*meta.height//dh
        x1=((x+w)*meta.width+dw-1)//dw;y1=((y+h)*meta.height+dh-1)//dh
        count=w*h;samples=(x1-x0)*(y1-y0)
        sums=[int(p[y0:y1,x0:x1].sum())*count//samples for p in planes]
        out=bytearray([0xa5]*(40 if kind==0 else 24 if kind==1 else 32))
        if kind==1:
            struct.pack_into('<5I',out,0,min(sums[0],0xffffffff),count,*[min(v,0xffffffff) for v in sums[2:]])
        else:
            largest=max(v//count for v in sums[2:]);ss=min(sums[0],0x7fffff);energy=min(sums[1],0x1fffffff)
            struct.pack_into('<5I',out,0,(min(largest,0xfff)|(ss<<12))&0xffffffff,
                ((ss>>20)|(energy<<3))&0xffffffff,min(sums[0],0xffffffff),count,min(sums[2],0xffffffff))
            struct.pack_into('<H',out,20,sums[0]//count)
            struct.pack_into('<IH',out,24,min(sums[3],0xffffffff),x+w//2)
            if kind==0:struct.pack_into('<IH',out,32,min(sums[4],0xffffffff),y+h//2)
        return out
    output=[]
    if families&1:
        output=[record([profile[0x234+k*16+4*i] for i in range(4)],k) for k in range(2)]
    else:output=[bytearray(),bytearray()]
    if families&2:
        sx,sy=profile[0x10],profile[0x14];columns,rows=profile[0]+1,profile[4]+1
        grid=bytearray()
        for y in range(rows):
            for x in range(columns):grid.extend(record((profile[8]+x*sx-sx//2,profile[12]+y*sy-sy//2,sx,sy),2))
        output.append(grid)
    else:output.append(bytearray())
    if marker is not None:output[0][22]=marker
    return list(map(bytes,output))


def verify_output(s,packet,profile,proof,marker=None):
    state=status(s);oracle=expected(packet,profile,state['cursor'],state['bank'])
    if marker is not None:
        oracle[0]=oracle[0][:22]+bytes([marker])+oracle[0][23:]
    pub=state['publication'];root=Path(proof['artifact_root'])
    expected_packet=[state['bank'],state['cursor']]+[
        profile[0x350+bank*16+family*256]+state['cursor']*profile[0x380+family*256]
        for bank in range(2) for family in range(3)]
    packet_offsets=(0x370,0x374,0x378,0x478,0x578,0x37c,0x47c,0x57c)
    actual_packet=[struct.unpack('<I',s.read(0x2006b800+o,4))[0] for o in packet_offsets]
    require(actual_packet==expected_packet,'Published group cursor/address packet differs')
    s.write(0x2006bb74,0xdeadbeef)
    require(struct.unpack('<I',s.read(0x2006bb74,4))[0]==state['cursor'],'Guest overwrote read-only group results')
    input_path=root/f'publication-{pub}.z62m'
    with input_path.open('xb') as handle:handle.write(packet)
    outputs=[]
    for family,data in enumerate(oracle):
        if not data:continue
        address=state['addresses'][family];actual=s.read(address,len(data))
        require(actual==data,'Independent group wire/aggregate mismatch: '+str(family))
        require(s.read(address+len(data),4)==b'\xa5'*4,'Group wrote past selected family')
        path=root/f'publication-{pub}-family-{family}.dat'
        with path.open('xb') as handle:handle.write(actual)
        outputs.append({'family':family,'path':path.name,'sha256':digest(path),'bytes':len(data)})
    require(s.get('raw-accepted')==0,'Group manufactured legacy RAW acceptance')
    proof.setdefault('frames',[]).append({'source':state,'profile':{hex(k):v for k,v in profile.items()},
        'MAIN_path':input_path.name,'MAIN_sha256':digest(input_path),'outputs':outputs,
        'unclassified_marker':marker,'published_cursor_packet':actual_packet,'result_write_ignored':True})


def check(binary,contract_path,state_path,output):
    binary,contract_path,state_path,output=map(workspace,(binary,contract_path,state_path,output))
    require(not output.exists(),'Use new group probe output');output.parent.mkdir(parents=True,exist_ok=True)
    sources=(Path(__file__),Path(cw.__file__),Path(hardware.__file__))
    proof={'schema':1,'completed':False,'camera_accessed':False,'firmware_executed':False,
        'artifact_root':str(output.parent),'QEMU_binary_sha256':digest(binary),
        'contract_sha256':digest(contract_path),'state_sha256':digest(state_path),
        'source_sha256':{str(p):digest(p) for p in sources}}
    try:
        help_run=subprocess.run([str(binary),'-device','nikon-z72-input-config,help'],capture_output=True,timeout=20)
        require(help_run.returncode==0 and b'z62-capture-group' in help_run.stdout+help_run.stderr,
            'Missing actual group device property')
        hardware.verify_build(binary)
        original={int(k,16):v for k,v in json.loads(contract_path.read_text(encoding='utf-8'))['profile'].items()}
        profile=dict(original);profile[0x22c]=3
        for i in range(65):profile[0x80+i*4]=min(i*1024,65535)
        for f in range(3):
            for tap in range(8):profile[0x20+f*32+tap*4]=1 if tap==3 else 127 if tap==4+f else 0
        dims,bits,stride,lut=cw.profile(json.loads(state_path.read_text(encoding='utf-8')))
        with session(binary,proof,False) as s:
            configure(s,profile,dims,bits,stride,lut);cw.upload(s,dims,1);cw.advance(s,1)
            require(status(s)['completed']==0 and not status(s)['enabled'],'Default-off group produced output')
        proof['default_off']=True
        with session(binary,proof) as s:
            configure(s,profile,dims,bits,stride,lut);cw.idle(s)
            require(status(s)['completed']==0,'Configuration manufactured group work')
            s.write(0x20068260,0)
            packet=cw.upload(s,dims,1)
            s.access(f'writeb {profile[0x350]+22:#x} 0x3c')
            cw.advance(s,1);require(status(s)['completed']==1 and status(s)['pending']==1,'No real group event')
            verify_output(s,packet,profile,proof,0x3c)
            cw.acknowledge(s);cw.upload(s,dims,2);cw.advance(s,2)
            require(status(s)['completed']==1 and status(s)['pending']==1,'Pending group result overwritten')
            s.write(0x20068270,0x20);require(status(s)['pending']==1,'Unrelated ACK released group')
            s.write(0x20068260,1)
            s.write(0x20068270,1)
            for pub in (3,4,5,6,7):
                cw.acknowledge(s)
                packet=cw.upload(s,dims,pub,(210,60,20) if pub&1 else (40,80,160));cw.advance(s,pub)
                require(status(s)['completed']==pub-1,'Fresh group input missing')
                verify_output(s,packet,profile,proof,0x3c if status(s)['cursor']==0 else None)
                s.write(0x20068270,1)
            require(status(s)['cursor']==0,'Five-slot group ring failed to wrap')
            require(status(s,'/machine/slave-input')['completed']==0,'Slave consumed master MAIN')
            s.query('system_reset');require(status(s)['completed']==0 and status(s)['pending']==0,'Reset retained group work')
        proof['all_three_families_six_frames_ring_and_guards']=True
        proof['masked_or_unrelated_ACK_never_releases_pending']=True
        with session(binary,proof) as s:
            alternate=dict(profile);alternate[0x33c]=1;alternate[0x22c]=2
            alternate[0x234]=0xffffffff;alternate[0x350]=0x10020000;alternate[0x360]=0x10020000
            alternate[0x450]=0x10020000;alternate[0x460]=0x10020000
            configure(s,alternate,dims,bits,stride,lut)
            packet=cw.upload(s,dims,101);cw.advance(s,1)
            require(status(s)['completed']==1 and status(s)['bank']==1,'Independent group bank1 selection failed')
            verify_output(s,packet,alternate,proof)
            proof['bank1_grid_only_ignores_inactive_ROI_geometry_and_destinations']=True
        for label,bad in (('actual-zero-resource',original),('zero-filter',dict(profile)),
                ('nonmonotonic-curve',dict(profile)),('unmapped-output',dict(profile)),('RAW-alias',dict(profile))):
            if label=='zero-filter':
                for tap in range(8):bad[0x20+tap*4]=0
            if label=='nonmonotonic-curve':bad[0x84]=65535;bad[0x88]=1
            if label=='unmapped-output':bad[0x350]=0xfffffff0
            if label=='RAW-alias':bad[0x350]=cw.raw.SLOTS[0]
            with session(binary,proof) as s:
                configure(s,bad,dims,bits,stride,lut);cw.upload(s,dims,1);cw.advance(s,1)
                require(status(s)['completed']==0 and status(s)['rejected'] and status(s)['pending']==0,
                    'Invalid group profile produced completion: '+label)
                proof.setdefault('negative_cases',[]).append({'case':label,'status':status(s)})
        with session(binary,proof) as s:
            configure(s,profile,dims,bits,stride,lut);cw.upload(s,dims,1)
            s.write(0x2006800c,0x20);cw.advance(s,1)
            require(status(s)['completed']==0,'Stopped group task published after cancellation')
            s.write(0x20068008,0x20);cw.acknowledge(s);cw.upload(s,dims,2);cw.advance(s,2)
            require(status(s)['completed']==1,'Restart did not accept fresh group source')
        proof['queued_cancel_and_restart']=True
        require(all(code==0 for code in proof['process_exit_codes']),'Native child did not close normally')
        require(all(digest(Path(name))==sha for name,sha in proof['source_sha256'].items()),'Native source changed')
        proof['completed']=True
    except Exception as exc:proof['failure']={'type':type(exc).__name__,'message':str(exc)}
    with output.open('x',encoding='utf-8') as handle:json.dump(proof,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:proof.get(k) for k in ('completed','failure','QEMU_binary_sha256','default_off',
        'all_three_families_six_frames_ring_and_guards','process_exit_codes')},ensure_ascii=False),flush=True)
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--contract',type=Path,required=True);parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=check(args.qemu,args.contract,args.state,args.output)
    raise SystemExit(0 if result['completed'] else 1)
