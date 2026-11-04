"""Real r92 QEMU CW -> frozen linear view -> five statistics DMA oracle."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import struct
import subprocess
import time
from unittest.mock import patch
import numpy as np

import probe_z62_capturework_device as cw
import probe_z62_continuous_stats as stats
import run_z62_capturework_statistics as hardware
from z62_main_frame import parse_packet
from record_z62_action_evidence import workspace,digest,require


@contextmanager
def session(binary,proof,bridge=True):
    original=subprocess.Popen
    class BridgeProcess(original):
        def __init__(self,command,*args,**kwargs):
            command=list(command)+['-global','nikon-z72-input-config.z62-capturework-policy0=on',
                '-global','nikon-z72-input-config.functional-continuous-stats=on',
                '-global','nikon-z72-boot-config.z62-finite-stats=on',
                '-global','nikon-z72-boot-config.z62-card-detect=on']
            if bridge: command+=['-global','nikon-z72-input-config.z62-capturework-statistics=on']
            super().__init__(command,*args,**kwargs)
    with patch.object(cw.subprocess,'Popen',BridgeProcess),cw.session(binary,True,proof) as s:
        yield s


def bridge_status(s): return json.loads(s.get('capturework-statistics-status'))


def expected(packet,dims):
    meta,raw=parse_packet(packet)
    linear=np.frombuffer(raw,dtype='<u2').reshape(meta.height,meta.stride//2)[:,:meta.width]
    selected=cw.tile_resize(cw.tile_resize(linear,dims[2],dims[3]),dims[4],dims[5])
    # Independent LUT8 interval midpoint followed by explicit linear16 -> 12.
    view=(selected.astype(np.uint32)//256)*16+8
    result=[bytearray(n) for n in stats.SIZES]
    r,g1,g2,b=(view[0::2,0::2],view[0::2,1::2],view[1::2,0::2],view[1::2,1::2])
    for width,height in ((30,20),(60,40)):
        for y in range(height):
            for x in range(width):
                sy=slice(y*503//height,(y+1)*503//height)
                sx=slice(x*757//width,(x+1)*757//width)
                rr,gg1,gg2,bb=(a[sy,sx] for a in (r,g1,g2,b)); count=rr.size
                sums=(int(rr.sum()),int(((gg1+gg2+1)//2).sum()),int(bb.sum()))
                if width==30:
                    struct.pack_into('<4I',result[0],y*480+x*16,*sums,count)
                    total=int((rr+gg1+gg2+bb).sum())
                    struct.pack_into('<H',result[1],y*64+x*2,(total+2*count)//(4*count))
                else:
                    for ch in range(3): struct.pack_into('<H',result[ch+2],y*128+x*2,(sums[ch]+count//2)//count)
    return list(map(bytes,result))


def verify_outputs(s,packet,dims,index,proof):
    oracle=expected(packet,dims); state=bridge_status(s)
    packet_path=Path(proof['artifact_root'])/f'publication-{state["publication"]}.z62m'
    with packet_path.open('xb') as handle: handle.write(packet)
    outputs=[]
    for ch,(base,pitch,size) in enumerate(zip(stats.BASES,stats.PITCHES,stats.SIZES)):
        address=base+pitch*index; actual=s.read(address,size)
        require(actual==oracle[ch],f'Independent five-plane mismatch ch={ch}, slot={index}')
        require(s.read(address+size,8)==b'\xa5'*8,'Statistics wrote past output')
        target=Path(proof['artifact_root'])/f'publication-{state["publication"]}-channel-{ch}.dat'
        with target.open('xb') as handle: handle.write(actual)
        outputs.append({'channel':ch,'path':target.name,'sha256':digest(target),'bytes':size})
    require(s.get('raw-accepted')==0,'Bridge manufactured legacy RAW acceptance')
    proof.setdefault('frames',[]).append({'source':state,'statistics_slot':index,
        'all_five_planes_and_guards_match':True,'legacy_RAW_accepted':0,
        'MAIN_path':packet_path.name,'MAIN_sha256':digest(packet_path),'outputs':outputs})


def check(binary,state_path,output):
    binary,state_path,output=map(workspace,(binary,state_path,output))
    require(not output.exists(),'Use a new native bridge result')
    output.parent.mkdir(parents=True,exist_ok=True)
    result={'schema':1,'completed':False,'camera_accessed':False,'firmware_executed':False,
        'artifact_root':str(output.parent),'QEMU_binary_sha256':digest(binary),
        'state_sha256':digest(state_path),
        'source_sha256':{str(path):digest(path) for path in
            (Path(__file__),Path(cw.__file__),Path(stats.__file__),Path(hardware.__file__))}}
    try:
        help_run=subprocess.run([str(binary),'-device','nikon-z72-input-config,help'],capture_output=True,timeout=20)
        require(help_run.returncode==0 and b'z62-capturework-statistics' in help_run.stdout+help_run.stderr,
            'Missing actual CW statistics device property')
        hardware.verify_build(binary)
        dims,bits,stride,lut=cw.profile(json.loads(state_path.read_text(encoding='utf-8')))
        def configure(s):
            cw.configure(s,dims,bits,stride,lut); stats.configure(s); stats.fill(s); stats.arm(s)
        with session(binary,result,False) as s:
            configure(s); cw.upload(s,dims,1); cw.advance(s,1); stats.frame(s)
            require(stats.get(s,'frames')==0 and s.get('raw-accepted')==0,'Default-off bridge changed legacy eligibility')
        result['default_off_preserves_legacy_source_gate']=True
        with session(binary,result) as s:
            configure(s); stats.frame(s)
            require(stats.get(s,'frames')==0,'Missing source manufactured statistics')
            for publication in range(1,7):
                if publication>1: cw.acknowledge(s)
                if publication!=2: s.write(0x20068270,0xa0)
                packet=cw.upload(s,dims,publication,(40,80,160) if publication&1 else (210,60,20))
                complete=cw.advance(s,publication)
                encoded_before=s.read(complete['address'],stride*dims[5])
                if publication==2:
                    stats.frame(s)
                    require(stats.get(s,'frames')==1 and bridge_status(s)['pending'],'Statistics ACK backpressure lost')
                    cw.upload(s,dims,100,error=True)
                    # Uncommitted live LUT changes cannot re-interpret a frozen view.
                    s.write(0x20069600,0); s.write(0x20068270,0xa0)
                    stats.frame(s); s.write(0x20069600,lut[0]|lut[1]<<16)
                else: stats.frame(s)
                require(stats.get(s,'frames')==publication,'Real CW source was not consumed once')
                require(s.read(complete['address'],stride*dims[5])==encoded_before,'Bridge overwrote guest encoded RAW')
                require(not bridge_status(s)['pending'],'Source lease not released after five DMA')
                verify_outputs(s,packet,dims,publication-1,result)
                stats.frame(s); require(stats.get(s,'frames')==publication,'Unchanged source replayed')
            require(stats.get(s,'batches')==1,'Six-slot statistics batch did not complete')
            cw.acknowledge(s); cw.upload(s,dims,7); cw.advance(s,7); stats.frame(s)
            require(bridge_status(s)['pending'],'Pending source missing before cancellation')
            s.write(0x2006800c,0x20d); s.write(0x20068270,0xa0); stats.frame(s)
            require(not bridge_status(s)['pending'] and stats.get(s,'frames')==6,'Cancelled source leaked')
            s.query('system_reset')
            require(bridge_status(s)['published']==0 and bridge_status(s)['consumed']==0 and
                not bridge_status(s)['pending'],'Reset retained source ownership/counters')
            result['single_source_backpressure_frozen_transfer_stop_reset']=True
            result['six_frames_five_planes_verified']=True
        with session(binary,result) as s:
            configure(s); s.write(0x2006a2e8,0x283b)
            cw.upload(s,dims,1); cw.advance(s,1); stats.frame(s)
            require(stats.get(s,'frames')==0 and stats.get(s,'reason')=='geometry' and
                bridge_status(s)['pending'],'CW source bypassed statistics geometry qualification')
            require(s.read(stats.BASES[0],stats.SIZES[0])==b'\xa5'*stats.SIZES[0],
                'Rejected statistics geometry wrote data')
            s.write(0x2006a2e8,0x283c); stats.arm(s); stats.frame(s)
            require(stats.get(s,'frames')==1,'Qualified retry did not consume preserved source')
            result['invalid_statistics_geometry_preserves_source_and_no_DMA']=True
        with session(binary,result) as s:
            bad_dims=(*dims[:4],dims[4]-2,dims[5])
            cw.configure(s,bad_dims,bits,stride,lut); cw.fill(s,stride*dims[5])
            stats.configure(s); stats.fill(s); stats.arm(s); cw.upload(s,bad_dims,1)
            deadline=time.monotonic()+20
            while not cw.status(s)['rejected'] and time.monotonic()<deadline: cw.idle(s)
            state=cw.status(s); stats.frame(s)
            require(state['rejected']>0 and state['completed']==0 and not bridge_status(s)['pending'],
                'Incompatible source geometry produced a bridge publication')
            require(s.read(cw.raw.SLOTS[0],32)==b'\xa5'*32 and stats.get(s,'frames')==0,
                'Incompatible bridge geometry performed DMA')
            result['incompatible_view_no_RAW_or_statistics_DMA']=True
        require(all(code==0 for code in result['process_exit_codes']),'Child did not close normally')
        require(all(digest(Path(name))==sha for name,sha in result['source_sha256'].items()),
            'Native source changed during validation')
        result['completed']=True
    except Exception as exc: result['failure']={'type':type(exc).__name__,'message':str(exc)}
    with output.open('x',encoding='utf-8') as handle: json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({key:result.get(key) for key in ('completed','failure','QEMU_binary_sha256',
        'default_off_preserves_legacy_source_gate','six_frames_five_planes_verified','process_exit_codes')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--state',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); result=check(args.qemu,args.state,args.output)
    raise SystemExit(0 if result['completed'] else 1)
