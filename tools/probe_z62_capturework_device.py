"""Actual r89 QEMU DMA/IRQ tests over executing synthetic ARM loops, no firmware."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import sys
import importlib.metadata

import numpy as np
from PIL import Image

import probe_z62_functional_raw as raw
from record_z62_action_evidence import workspace,digest,require
from probe_z62_capturework_pixels import profile
from verify_z62_capturework_pixels_evidence import tile_resize
from z62_main_frame import make_packet,parse_packet

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'.build/z62-capturework-2026.11.04-r89/runtime/qemu-system-arm.exe'


@contextmanager
def session(binary,enabled,proof):
    base=Path('Q:/.runtime/tmp'); require(base.samefile(ROOT/'.runtime/tmp'),'Verified workspace scratch required')
    with tempfile.TemporaryDirectory(prefix='capturework-qtest-',dir=base) as directory:
        work=Path(directory); qmp_port,wire_port=raw.free_port(),raw.free_port()
        command=[str(binary),'-M','nikon-z62-dual-lab','-smp','4,maxcpus=5','-S',
            '-display','none','-serial','none','-monitor','none','-nic','none',
            '-qmp',f'tcp:127.0.0.1:{qmp_port},server=on,wait=off',
            '-qtest',f'tcp:127.0.0.1:{wire_port},server=on,wait=off','-qtest-log','NUL']
        for cpu in range(4):
            command+=['-device',f'loader,addr=0x10020000,data=0xeafffffe,data-len=4,cpu-num={cpu}',
                      '-device',f'loader,addr=0x10020000,cpu-num={cpu}']
        if enabled: command+=['-global','nikon-z72-input-config.z62-capturework=on']
        with (work/'qemu.log').open('wb') as log:
            process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=log,
                env=dict(os.environ,TEMP=str(base),TMP=str(base)))
        session_number=len(proof.setdefault('sessions',[]))+1
        session_record={'command':command,'pid':process.pid,'enabled':enabled}
        proof['sessions'].append(session_record)
        streams=[]; sockets=[]; s=raw.Session()
        try:
            sock=raw.connect(qmp_port,process); sockets.append(sock); s.qmp=sock.makefile('rwb'); streams.append(s.qmp)
            json.loads(s.qmp.readline()); s.query('qmp_capabilities')
            sock=raw.connect(wire_port,process); sockets.append(sock); s.wire=sock.makefile('rwb'); streams.append(s.wire)
            s.irqs=[]; s.work=work
            s.access(f'irq_intercept_out {raw.MASTER} capturework-complete')
            yield s
        except Exception:
            proof.setdefault('qemu_errors',[]).append((work/'qemu.log').read_text(errors='replace'))
            raise
        finally:
            if process.poll() is None:
                try: s.query('quit')
                except (OSError,ValueError,AssertionError): process.terminate()
            for stream in streams: stream.close()
            for sock in sockets: sock.close()
            result=process.wait(timeout=20)
            proof.setdefault('process_exit_codes',[]).append(result)
            session_record['exit_code']=result
            log_path=Path(proof['artifact_root'])/f'qemu-{session_number}.log'
            with log_path.open('xb') as handle: handle.write((work/'qemu.log').read_bytes())
            session_record['log_sha256']=digest(log_path)
            if not work.resolve().is_relative_to(ROOT): raise ValueError('Scratch escaped workspace')


def status(s,path=raw.MASTER): return json.loads(s.get('capturework-status',path))


def advance(s,expected):
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        s.query('cont')
        try: time.sleep(.03)
        finally: s.query('stop')
        state=status(s)
        if state['completed']>=expected: return state
    raise TimeoutError('CaptureWork did not complete: '+json.dumps(status(s)))


def idle(s):
    for _ in range(3):
        s.query('cont')
        try: time.sleep(.025)
        finally: s.query('stop')


def configure(s,dimensions,bits,stride,lut,bank=0):
    iw,ih,mw,mh,ow,oh=dimensions
    registers={0x20068500:0,0x20069d00:ih<<16,0x20069d04:iw<<16,
        0x20069e78:mh<<16,0x20069e7c:mw<<16,0x20069f00:0x11,
        0x20069514:{16:0,14:1,12:2}[bits]|4,0x20069518:ow<<16,0x2006951c:oh<<16,
        0x20069520:0,0x20069524:0,0x20069528:0,0x2006952c:2,0x20069530:0,
        0x20069a08:stride,0x20069a14:1,0x20069a18:1,0x20069a24:0,0x20069a3c:bank,
        0x20069a40:1,0x20069a44:0,0x20069a48:3,0x20069a4c:0,0x20069a80:0}
    for i in range(128): registers[0x20069600+4*i]=lut[2*i]|(lut[2*i+1]<<16)
    for b in range(2):
        for i,address in enumerate(raw.SLOTS): registers[0x20069a50+b*16+4*i]=address+b*0x300000
    for address,value in registers.items(): s.write(address,value)
    for address,value in ((0x20068000,0x20d),(0x20068004,0x20d),(0x20068010,0x20d),
                          (0x20068100,0x85),(0x20068104,0x85),(0x20068200,0x18),
                          (0x20068280,0x80),(0x20068008,0x20d)):
        s.write(address,value)
    return registers


def fill(s,size):
    for bank in range(2):
        for address in raw.SLOTS: s.access(f'memset {address+bank*0x300000:#x} {size+4:#x} 0xa5')


def acknowledge(s):
    s.write(0x20068210,0x18); s.write(0x20068290,0x80)


def upload(s,dimensions,publication,color=(40,80,160),error=False):
    iw,ih,*_=dimensions; ns=(publication-1)*33_333_334
    packet=make_packet(Image.new('RGB',(8,8),color),width=iw,height=ih,stride=2*iw,
        epoch=0x89,publish_id=publication,frame_id=ns*30//1_000_000_000,virtual_time_ns=ns)
    path=s.work/f'frame-{publication}.z62m'
    with path.open('xb') as handle: handle.write(packet)
    s.query('qom-set',{'path':raw.MASTER,'property':'capturework-main-file','value':str(path)},error=error)
    return packet


def expected(packet,dimensions,stride,lut):
    meta,data=parse_packet(packet); _,_,mw,mh,ow,oh=dimensions
    source=np.frombuffer(data,dtype='<u2').reshape(meta.height,meta.stride//2)[:,:meta.width]
    values=np.asarray(lut,dtype=np.uint16)[tile_resize(tile_resize(source,mw,mh),ow,oh)>>8]
    rows=np.full((oh,stride),0xa5,dtype=np.uint8); a,b=values[:,0::2],values[:,1::2]
    payload=rows[:,:ow*12//8]; payload[:,0::3]=a&255
    payload[:,1::3]=(a>>8)|((b&15)<<4); payload[:,2::3]=b>>4
    return rows.tobytes()


def verify_frame(s,packet,dimensions,stride,lut,address,proof):
    size=stride*dimensions[5]; actual=s.read(address,size)
    require(actual==expected(packet,dimensions,stride,lut),'Actual DMA differs from independent samples')
    require(s.read(address+size,4)==b'\xa5'*4,'DMA touched suffix')
    meta,_=parse_packet(packet); target=Path(proof['artifact_root'])/'frames'
    target.mkdir(exist_ok=True)
    packet_path=target/f'publication-{meta.publish_id}.z62m'; packed_path=target/f'publication-{meta.publish_id}.p12'
    with packet_path.open('xb') as handle: handle.write(packet)
    with packed_path.open('xb') as handle: handle.write(actual)
    proof.setdefault('frames',[]).append({'publication':meta.publish_id,'frame_id':meta.frame_id,
        'virtual_time_ns':meta.virtual_time_ns,'address':hex(address),'packet_sha256':digest(packet_path),
        'packed_sha256':digest(packed_path),'pixels_checked':dimensions[4]*dimensions[5],
        'exact_bytes_and_padding_match':True,'device_state':status(s)})


def check(binary,state_path,proof):
    help_result=subprocess.run([str(binary),'-device','nikon-z72-input-config,help'],capture_output=True,text=True,timeout=20)
    require(help_result.returncode==0 and 'z62-capturework' in help_result.stdout+help_result.stderr,
        'Missing real QEMU CaptureWork device property')
    import z62_capturework_device as device
    manifest=json.loads((binary.parent.parent/'capturework-build-manifest.json').read_text(encoding='utf-8'))
    require(manifest['capturework_device']==device.identity() and digest(binary)==manifest['binary_sha256'],
        'CaptureWork source/binary identity differs')
    dimensions,bits,stride,lut=profile(json.loads(state_path.read_text(encoding='utf-8')))
    require(bits==12,'Independent native packed12 oracle required'); size=stride*dimensions[5]
    with session(binary,False,proof) as s:
        configure(s,dimensions,bits,stride,lut); fill(s,size)
        upload(s,dimensions,1,error=True); idle(s)
        require(not status(s)['enabled'] and status(s)['completed']==0,'Default-off device did work')
        require(s.read(raw.SLOTS[0],size)==b'\xa5'*size,'Default-off DMA')
    proof['default_off']=True
    with session(binary,True,proof) as s:
        configure(s,dimensions,bits,stride,lut); fill(s,size); idle(s)
        require(status(s)['completed']==0,'Missing MAIN manufactured completion')
        first=upload(s,dimensions,1)
        time.sleep(.04)
        require(status(s)['completed']==0 and s.read(raw.SLOTS[0],32)==b'\xa5'*32,'Paused VM performed DMA')
        one=advance(s,1)
        require(one['valid'] and one['publication']==1 and one['bank']==0 and one['slot']==0,'Wrong output identity')
        verify_frame(s,first,dimensions,stride,lut,raw.SLOTS[0],proof)
        require(one['pending_front']==0x18 and one['pending_raw']==0x80,'Wrong completion causes')
        require(int.from_bytes(s.read(0x20068210,4),'little')&0x18==0x18 and
            int.from_bytes(s.read(0x20068290,4),'little')&0x80==0x80,'Real input event latches absent')
        require(status(s,raw.SLAVE)['completed']==0,'Slave device consumed master input')
        second=upload(s,dimensions,2,(210,60,20)); idle(s)
        require(status(s)['completed']==1 and status(s)['publication']==1,'Backpressure overwrote committed output')
        s.write(0x20068210,8); idle(s); require(status(s)['completed']==1,'Partial ACK released data')
        s.write(0x20068210,0x10); s.write(0x20068290,0x80)
        two=advance(s,2)
        require(two['slot']==1 and two['publication']==2,'Ring did not advance')
        verify_frame(s,second,dimensions,stride,lut,raw.SLOTS[1],proof)
        proof.update(actual_engine_local_DMA=True,independent_full_frame_samples=True,
            virtual_clock_owns_DMA=True,real_event_latches=True,slave_isolated=True,
            backpressure_and_partial_ACK=True,ring_advances=True,
            irq_notifications=list(s.irqs),initial_pair_frames=2)
        acknowledge(s); s.write(0x20069a3c,1)
        third=upload(s,dimensions,3,(120,90,40)); three=advance(s,3)
        require(three['bank']==1 and three['slot']==2,'Z62 bit0 bank selection was not independent')
        verify_frame(s,third,dimensions,stride,lut,raw.SLOTS[2]+0x300000,proof)
        acknowledge(s)
        # The black source uses LUT index4. An uncommitted broken shadow word
        # must not replace the immutable transfer used by the actual job.
        s.write(0x20069608,0)
        fourth=upload(s,dimensions,4,(0,0,0)); four=advance(s,4)
        verify_frame(s,fourth,dimensions,stride,lut,raw.SLOTS[3]+0x300000,proof)
        require(four['lookup']==lut,'Committed metadata copied live LUT state')
        s.write(0x20069608,lut[4]|(lut[5]<<16)); acknowledge(s)
        upload(s,dimensions,5,(255,0,0)); require(status(s)['active'],'No task to cancel before virtual dispatch')
        before_irqs=len(s.irqs); s.write(0x20068014,0x200); idle(s)
        require(status(s)['completed']==4 and not status(s)['active'] and len(s.irqs)==before_irqs,
            'Cancelled timer still wrote/completed')
        require(s.read(raw.SLOTS[0]+0x300000,size)==b'\xa5'*size,'Cancelled work wrote its target')
        s.write(0x20068010,0x200); s.write(0x20068008,0x200); idle(s)
        require(status(s)['completed']==4,'Restart replayed a pre-stop publication')
        sixth=upload(s,dimensions,6,(210,220,30)); advance(s,5)
        verify_frame(s,sixth,dimensions,stride,lut,raw.SLOTS[0]+0x300000,proof)
        acknowledge(s); upload(s,dimensions,7)
        s.query('system_reset'); configure(s,dimensions,bits,stride,lut); fill(s,size); idle(s)
        require(status(s)['completed']==0 and not status(s)['valid'],'Reset replayed old work')
        eighth=upload(s,dimensions,8,(60,20,210)); advance(s,1)
        require(status(s)['publication']==8,'Reset lost publication fencing')
        verify_frame(s,eighth,dimensions,stride,lut,raw.SLOTS[0],proof)
        acknowledge(s); fill(s,size)
        s.write(0x20069a5c,raw.SLOTS[0]); s.write(0x20068104,0x80)
        upload(s,dimensions,9); idle(s)
        require(status(s)['completed']==1 and status(s)['reason']=='alias','Invalid ring was accepted')
        for address in raw.SLOTS:
            require(s.read(address,size)==b'\xa5'*size,'Ring rejection left partial DMA')
        require(status(s)['pending_front']==0 and status(s)['pending_raw']==0,'Ring rejection emitted completion')
        s.query('qom-set',{'path':raw.MASTER,'property':'capturework-status','value':'{}'},error=True)
        proof.update(bank_bit0_verified=True,uncommitted_LUT_isolated=True,
            pre_dispatch_cancel_has_no_DMA_or_IRQ=True,restart_requires_fresh_publication=True,
            reset_requires_fresh_publication=True,complete_selected_ring_preflight=True,
            rejected_ring_has_no_partial_DMA_or_completion=True,status_readonly=True,
            inflight_worker_cancel_race_exhaustively_verified=False,
            irq_notifications=list(s.irqs),actual_successful_DMA_frames_total=len(proof['frames']),
            actual_pixels_checked=sum(row['pixels_checked'] for row in proof['frames']))
    require(all(code==0 for code in proof['process_exit_codes']),'Native child did not exit cleanly')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--qemu',type=Path,default=DEFAULT)
    parser.add_argument('--state',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); output=workspace(args.output); output.parent.mkdir(parents=True,exist_ok=True)
    require(not output.exists(),'Use new native evidence path')
    result={'schema':1,'completed':False,'firmware_executed':False,'synthetic_ARM_loops_only':True,
        'camera_accessed':False,'probe_sha256':digest(Path(__file__)),'artifact_root':str(output.parent),
        'source_sha256':{str(path):digest(path) for path in (Path(__file__),Path(raw.__file__),
            ROOT/'tools/probe_reference_devices.py',ROOT/'tools/probe_z62_capturework_pixels.py',
            ROOT/'tools/verify_z62_capturework_pixels_evidence.py',ROOT/'tools/z62_main_frame.py',
            ROOT/'tools/z62_scene_packet.py',ROOT/'tools/z62_capturework_device.py',ROOT/'tools/reference_updates.py')},
        'dependencies':{name:importlib.metadata.version(name) for name in ('numpy','Pillow')},
        'python':sys.version,'QEMU_binary_sha256':digest(args.qemu),'state_sha256':digest(args.state)}
    try:
        check(args.qemu,args.state,result)
        require(all(digest(Path(path))==expected for path,expected in result['source_sha256'].items()) and
            digest(args.qemu)==result['QEMU_binary_sha256'],'Native test source or executable changed')
        result['completed']=True
    except Exception as exc: result['failure']={'type':type(exc).__name__,'message':str(exc)}
    with output.open('x',encoding='utf-8') as handle: json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    raise SystemExit(0 if result['completed'] else 1)
