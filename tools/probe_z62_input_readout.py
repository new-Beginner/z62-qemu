"""Native C inline readout: supplied pixels, ownership, sensor event and negatives.

No Nikon firmware. This checks a declared C MAIN view, not physical CMOS/SDES
equivalence or new guest RAW DMA. Pixel consumption is independently audited.
"""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
from unittest.mock import patch
import numpy as np
from PIL import Image
import probe_z62_capturework_device as cw
import run_z62_input_readout as hardware
from z62_main_frame import make_packet,parse_packet
from record_z62_action_evidence import workspace,digest,require


@contextmanager
def session(binary,proof,enabled):
    previous=subprocess.Popen
    class ReadoutProcess(previous):
        def __init__(self,command,*args,**kwargs):
            command=list(command)+['-global','nikon-z62-sensor-config.functional-raw-completion=on']
            if enabled:command+=['-global','nikon-z72-input-config.z62-input-readout=on']
            super().__init__(command,*args,**kwargs)
    with patch.object(cw.subprocess,'Popen',ReadoutProcess),cw.session(binary,True,proof) as s:yield s


def status(s):return json.loads(s.get('input-readout-status'))
def word(s,address):return int.from_bytes(s.read(address,4),'little')
def sensor(s,prop):return s.get(prop,'/machine/master-sensor')


def configure(s):
    # Full original CW setup first, then the separate committed inline phase.
    cw.configure(s,(2020,1342,1514,1342,1514,1006),12,2272,list(range(256)))
    s.write(0x2006800c,0x20d)
    for address,value in ((0x20069d00,136<<16),(0x20069d04,2020<<16),
        (0x20069e78,136<<16),(0x20069e7c,2020<<16),(0x20068100,4),
        (0x20068104,4),(0x20068008,1)):
        s.write(address,value)
    for address,value in ((0x20065400,0x10011),(0x20065504,0x8000),(0x2006550c,2)):
        s.write(address,value)


def packet(publication,color=(40,80,160),width=2020,height=136,epoch=0x102):
    ns=publication*33_333_334
    return make_packet(Image.new('RGB',(8,8),color),width=width,height=height,
        stride=(2*width+15)&~15,epoch=epoch,publish_id=publication,
        frame_id=ns*30//1_000_000_000,virtual_time_ns=ns)


def publish(s,content,name='source.z62m',error=False):
    path=s.work/name
    with path.open('wb') as handle:handle.write(content)
    s.query('qom-set',{'path':cw.raw.MASTER,'property':'input-readout-file','value':str(path)},error=error)
    return path


def audit(content):
    meta,pixels=parse_packet(content)
    values=np.frombuffer(pixels,dtype='<u2').reshape(meta.height,meta.stride//2)[:,:meta.width]
    active=values.astype('<u2').tobytes();fnv=14695981039346656037
    for byte in active:fnv=((fnv^byte)*1099511628211)&0xffffffffffffffff
    return {'sum_u16':int(values.astype(np.uint64).sum()),'fnv1a64':fnv,
        'last_bytes':len(active),'rows':meta.height,'epoch':meta.epoch,'publication':meta.publish_id,
        'frame':meta.frame_id,'time_ns':meta.virtual_time_ns}


def check(binary,output):
    binary,output=map(workspace,(binary,output));require(not output.exists(),'Use new native readout output')
    output.parent.mkdir(parents=True,exist_ok=True)
    proof={'schema':1,'completed':False,'artifact_root':str(output.parent),'camera_accessed':False,
        'firmware_executed':False,'guest_RAW_DMA':False,'physical_sensor_equivalence':False,
        'source_sha256':{str(Path(p)):digest(Path(p)) for p in (__file__,cw.__file__,hardware.__file__)}}
    try:
        help_result=subprocess.run([str(binary),'-device','nikon-z72-input-config,help'],capture_output=True,timeout=20)
        require(help_result.returncode==0 and b'z62-input-readout' in help_result.stdout+help_result.stderr,
            'Missing real C inline readout property')
        proof['binary_sha256']=hardware.verify_build(binary)['binary_sha256']
        with session(binary,proof,False) as s:
            configure(s);publish(s,packet(1),error=True);cw.idle(s)
            require(not status(s)['enabled'] and status(s)['completed']==0 and sensor(s,'raw-source-events')==0,
                'Default-off readout produced work or notification')
        proof['default_off']=True
        with session(binary,proof,True) as s:
            publish(s,packet(1),error=True);configure(s);cw.idle(s)
            require(status(s)['eligible'] and status(s)['completed']==0 and sensor(s,'raw-source-events')==0,
                'Register writes or missing input manufactured completion')
            first=packet(1);path=publish(s,first)
            require(status(s)['pending'] and status(s)['completed']==0 and word(s,0x20065508)==0,
                'Paused VM consumed data or completed sensor')
            publish(s,packet(2),name='busy.z62m',error=True)
            # The owned bytes must survive host mailbox replacement after admission.
            with path.open('wb') as handle:handle.write(packet(1,(210,20,10)))
            cw.idle(s);one=status(s);expected=audit(first)
            require(all(one[key]==value for key,value in expected.items()),'Actual all-row C consumption differs')
            require(one['completed']==1 and sensor(s,'raw-source-events')==1 and sensor(s,'raw-completions')==1
                and word(s,0x20065508)&2,'Data-qualified sensor status absent')
            require(cw.status(s)['completed']==0 and s.get('raw-accepted')==0,
                'Inline source impersonated CW or legacy RAW DMA')
            with (output.parent/'source-1.z62m').open('xb') as handle:handle.write(first)
            proof['independent_pixel_audit']=expected;proof['output_status']=one
            s.write(0x20065508,2)
            require(not word(s,0x20065508)&2,'Sensor W1C did not clear actual pending')
            publish(s,first,error=True)
            bad=bytearray(packet(2));bad[-16]^=1;publish(s,bytes(bad),error=True)
            publish(s,packet(2,width=2018),error=True)
            publish(s,packet(2,epoch=0x103),error=True)
            cw.idle(s);require(status(s)['completed']==1 and sensor(s,'raw-source-events')==1,
                'Bad input produced a source event')
            second=packet(2,(210,60,20));publish(s,second);s.write(0x2006800c,1);cw.idle(s)
            require(status(s)['cancelled']==1 and status(s)['completed']==1 and sensor(s,'raw-source-events')==1,
                'Stopped pending data still completed')
            s.write(0x20068008,1);cw.idle(s)
            require(status(s)['completed']==1,'Restart replayed a cancelled publication')
            publish(s,second,error=True);third=packet(3,(120,90,40));publish(s,third);cw.idle(s)
            require(status(s)['completed']==2 and all(status(s)[key]==value for key,value in audit(third).items()),
                'Fresh post-stop input did not process')
            s.write(0x20065508,2);s.write(0x2006550c,0)
            publish(s,packet(4));cw.idle(s)
            require(status(s)['completed']==3 and sensor(s,'raw-source-events')==3 and sensor(s,'raw-ignored')==1
                and not word(s,0x20065508)&2,'Unarmed sensor consumer received success')
            publish(s,packet(5));s.query('system_reset');cw.idle(s)
            require(status(s)['completed']==0 and not status(s)['pending'] and sensor(s,'raw-source-events')==0,
                'Reset retained pending/completed source state')
        proof.update(missing_source_no_completion=True,register_only_no_completion=True,
            owned_input_survives_mailbox_replacement=True,CRC_geometry_epoch_replay_rejected=True,
            pause_stop_restart_reset_verified=True,sensor_mask_and_W1C_verified=True,
            legacy_RAW_counters_unchanged=True,completed=True)
    except Exception as exc:proof['failure']={'type':type(exc).__name__,'message':str(exc)}
    with output.open('x',encoding='utf-8') as handle:json.dump(proof,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in proof.items() if k not in ('sessions','source_sha256')},ensure_ascii=False),flush=True)
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();proof=check(args.qemu,args.output)
    raise SystemExit(0 if proof['completed'] else 1)
