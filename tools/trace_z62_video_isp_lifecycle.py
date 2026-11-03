"""Original mode cycle with explicit C video and real scene-pixel challenges."""
import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
import trace_z62_photo_results_lifecycle as parent
import trace_z62_grid_geometry_lifecycle as geometry
import trace_z62_grid_lifecycle as lifecycle
import trace_z62_scene_response as scene_reader
import run_z62_video_isp_format as host
import z62_scene_packet as packet
import z62_scene_response as pixel_measure

VERSION='2026.11.03-video-isp-lifecycle-r59b'
ORIGINAL_COUNTERS=geometry.collect_counters
VIDEO_COUNTERS=('video-batches','video-main-bytes','video-work-bytes','video-rejected','video-blocked',
    'video-source-captures','video-source-coalesced','video-source-rejected','video-source-cancelled',
    'video-source-bytes','video-source-seq')


def counters(machine,cache):
    row=ORIGINAL_COUNTERS(machine,cache)
    with machine.io:
        for name in (*VIDEO_COUNTERS,'video-reason'):
            try:
                value=machine.qmp.command('qom-get',{'path':cache['stream'],'property':name})
                if (name=='video-reason' and type(value) is not str) or (name!='video-reason' and (type(value) is not int or value<0)):
                    raise ValueError('Invalid video property')
                row['stream'][name]=value
            except (OSError,RuntimeError,ValueError) as exc:
                row['errors'].append({'property':name,'type':type(exc).__name__,'message':str(exc)})
    row['known']=not row['errors']
    return row


def pixels(machine):
    bank=machine._words(0x20069a3c,1)[0]&1
    sources=machine._words(0x20069a50+bank*16,4)
    offset=502*2272+752*3//2
    raw=[scene_reader.read_bytes(machine,address+offset,48) for address in sources]
    nv12=[];heights=[]
    for port in (3,4,5):
        regs=machine._words(0x20100400+port*64,13)
        width,height=regs[8]&0x7fff,regs[8]>>16
        if regs[0]!=0x09000201 or width not in (1024,1920) or height not in (576,680,682,1080):
            raise ValueError('Unsupported LCD output during scene observation')
        heights.append(height)
        for f in range(4):
            address=machine._words(0x20102200+f*64+port*4,1)[0]
            nv12.append({'y':scene_reader.read_bytes(machine,address,32),
                         'uv':scene_reader.read_bytes(machine,address+regs[10],32)})
    return raw,nv12,heights


def run(output,card,group23,qemu,origin,duration=55):
    if output.exists(): raise FileExistsError('Existing video lifecycle evidence is immutable')
    # Validate the explicit C choice before any process or output is created.
    host.configure_command([],video=True,origin=origin)
    original_run=lifecycle.baseline.run
    original_configure=lifecycle.configure_command
    sources={str(Path(p)):hashlib.sha256(Path(p).read_bytes()).hexdigest()
             for p in (__file__,packet.__file__,pixel_measure.__file__)}
    observations=[];publications=[];errors=[];cache={}
    state={'level':None,'phase':0,'high_time':None,'next_sample':0,'video_before':None,
           'video_after':None,'photo_after':None,'video_sent':None,'photo_sent':None}

    with tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR'),prefix='z62-video-scene-r59b-') as folder:
        folder=Path(folder)
        if not str(folder).isascii(): raise ValueError('Require an ASCII scene mailbox')
        def payload(identifier,gray,time_ns):
            frame=time_ns*30//1_000_000_000
            data=packet.make_packet(Image.new('RGB',(64,64),(gray,)*3),epoch=0x59,publish_id=identifier,
                                    frame_id=frame,virtual_time_ns=time_ns)
            info,raw=packet.parse_packet(data)
            return data,{**info,'gray':gray,'packet_sha256':hashlib.sha256(data).hexdigest(),
                         'raw_reference':raw[502*2272+752*3//2:502*2272+752*3//2+48].hex()}
        data,initial=payload(1,40,0);initial_path=folder/'initial.scene'
        with initial_path.open('xb') as handle: handle.write(data)
        def configure(command,*args,**kwargs):
            return original_configure(command,*args,**kwargs)+['-global','nikon-z72-input-config.scene-source=on',
                '-global','nikon-z72-input-config.scene-initial-file='+initial_path.as_posix()]
        facade=SimpleNamespace(DEFAULT_QEMU=host.DEFAULT_QEMU,verify_build=host.verify_build,
            configure_command=lambda command,g=True,retained=False:host.configure_command(command,g,retained,video=True,origin=origin))

        def current_video(machine):
            with machine.io:
                if 'path' not in cache:
                    found=[]
                    for obj in machine.qmp.command('qom-list',{'path':'/machine/unattached'}):
                        if obj['type']=='child<nikon-z72-boot-config>':
                            path='/machine/unattached/'+obj['name']
                            if machine.qmp.command('qom-get',{'path':path,'property':'master-role'}) is True: found.append(path)
                    if len(found)!=1: raise ValueError('Expected one master video device')
                    cache['path']=found[0]
                value=machine.qmp.command('qom-get',{'path':cache['path'],'property':'video-batches'})
                if type(value) is not int or value<0: raise ValueError('Invalid video batch counter')
                return value

        def publish(machine,now,identifier,gray):
            data,info=payload(identifier,gray,int(now*1_000_000_000))
            file=folder/(str(identifier)+'.scene')
            with file.open('xb') as handle: handle.write(data)
            record={**info,'published_virtual_seconds':now,'video_batches_before':current_video(machine),
                    'publication_confirmed':False}
            publications.append(record)
            # No retransmission if QMP delivery is uncertain.
            with machine.io:
                machine.qmp.command('qom-set',{'path':'/machine/master-input','property':'scene-file','value':file.as_posix()})
                actual=machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'scene-publish-id'})
            if actual!=identifier: raise ValueError('Scene publication readback differs')
            record['publication_confirmed']=True
            print('VIDEO_SCENE_PUBLISH',json.dumps(record),flush=True)
            return record

        def observe_pixels(machine,row,source,kind):
            with machine.io:
                status=scene_reader.source_status(machine)
                raw,nv12,heights=pixels(machine)
                ready=machine._words(0xc1868ae8,1)[0];inhibit=machine._words(0xc1821eb8,1)[0]
            png=machine.frame_png()
            with Image.open(io.BytesIO(png)) as img:
                measured=pixel_measure.measure(source['gray'],bytes.fromhex(source['raw_reference']),raw,nv12,img)
            tags={'scene-used-publish-id':'publish_id','scene-used-epoch':'epoch',
                  'scene-used-frame-id':'frame_id','scene-used-time-ns':'virtual_time_ns'}
            match=all(status[k]==source[v] for k,v in tags.items())
            mode_ok=heights[1]==576 if kind.startswith('video') else heights[1] in (680,682)
            verified=bool(match and mode_ok and row['display_enabled'] and row['index']==3 and
                          all(measured[k] for k in ('raw_matches','nv12_matches','lcd_matches')))
            name=kind+'-'+str(len(observations))+'.png'
            with (output/name).open('xb') as handle: handle.write(png)
            value={'kind':kind,'virtual_seconds':row['virtual_seconds'],'source':status,
                'expected_source':source,'measure':measured,'source_tags_match':match,'mode_heights':heights,
                'video_batches':current_video(machine),'pixel_response_verified':verified,
                'original_ready':ready,'input_inhibit':inhibit,'index':row['index'],
                'display_enabled':row['display_enabled'],'lcd_file':name,'lcd_sha256':hashlib.sha256(png).hexdigest(),
                'raw_patches':[x.hex() for x in raw],
                'nv12_patches':[{'y':v['y'].hex(),'uv':v['uv'].hex()} for v in nv12],
                'snapshots_atomic':False,'is_full_mode_recovery_assessment':False}
            observations.append(value)
            print('VIDEO_SCENE_RESPONSE',json.dumps({k:value[k] for k in
                ('kind','virtual_seconds','video_batches','pixel_response_verified','measure','original_ready','input_inhibit')}),flush=True)
            return value

        def instrument(*args,**kwargs):
            prior=kwargs['extra_observation_hook']
            def observed(machine,row):
                result=prior(machine,row);now=row['virtual_seconds']
                if now<state['next_sample']: return result
                state['next_sample']=now+1
                try:
                    with machine.io:
                        level=machine.qmp.command('qom-get',{'path':'/machine/peripheral/keys','property':'input-levels'})
                    if type(level) is not int or not 0<=level<=0xffffff: raise ValueError('Invalid selector readback')
                    level&=1
                    if state['level'] is not None and level!=state['level']:
                        state['phase']+=1
                        if level==1: state['high_time']=now
                    state['level']=level
                    if errors: return result
                    if state['phase']==1 and current_video(machine)>0:
                        if state['video_before'] is None:
                            value=observe_pixels(machine,row,initial,'video-before')
                            if value['pixel_response_verified']:
                                state['video_before']=value
                                state['video_sent']=publish(machine,now,2,210)
                        elif state['video_after'] is None and now>=state['video_sent']['published_virtual_seconds']+2:
                            value=observe_pixels(machine,row,state['video_sent'],'video-after')
                            if value['pixel_response_verified'] and value['video_batches']>state['video_sent']['video_batches_before']:
                                state['video_after']=value
                    elif state['phase']==2 and now>=state['high_time']+6:
                        if state['photo_sent'] is None:
                            state['photo_sent']=publish(machine,now,3,40)
                        elif state['photo_after'] is None and now>=state['photo_sent']['published_virtual_seconds']+2:
                            value=observe_pixels(machine,row,state['photo_sent'],'photo-after')
                            if value['pixel_response_verified']: state['photo_after']=value
                except (OSError,RuntimeError,ValueError) as exc:
                    failure={'virtual_seconds':now,'type':type(exc).__name__,'message':str(exc)}
                    errors.append(failure);print('VIDEO_SCENE_ERROR',json.dumps(failure),flush=True)
                return result
            kwargs['extra_observation_hook']=observed
            return original_run(*args,**kwargs)

        with patch.object(lifecycle,'configure_command',configure),patch.object(parent,'host',facade),\
             patch.object(geometry,'collect_counters',counters),patch.object(lifecycle.baseline,'run',instrument):
            previous=parent.run(output,card,group23,qemu,True,duration)
    unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in sources.items())
    result={'schema':1,'version':VERSION,'qemu_sha256':previous['qemu_sha256'],'source_sha256':sources,
        'sources_unchanged_during_run':unchanged,'completed_observation':bool(previous['completed_observation'] and unchanged and not errors),
        'process_closed':previous['process_closed'],'software_origin':list(origin),'initial_source':initial,
        'publications':publications,'observations':observations,'read_errors':errors,
        'video_before':state['video_before'],'video_after':state['video_after'],'photo_after':state['photo_after'],
        'video_new_pixels_reached_factory_lcd':bool(state['video_before'] and state['video_after']),
        'photo_return_new_pixels_reached_factory_lcd':bool(state['photo_after']),
        'strict_mode_recovery_verified':previous['mode_recovery_verified'],
        'implementation_level':'C','work_is_temporal_history':False,'physical_isp_equivalent':False,
        'camera_accessed':False,'guest_software_written':False,'whole_camera_verified':False}
    with (output/'video-isp-lifecycle.json').open('x',encoding='utf-8') as handle: json.dump(result,handle,indent=2)
    print(json.dumps({key:result[key] for key in ('completed_observation','video_new_pixels_reached_factory_lcd',
        'photo_return_new_pixels_reached_factory_lcd','strict_mode_recovery_verified','read_errors')}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--card',type=Path,required=True)
    parser.add_argument('--group23',type=Path,required=True);parser.add_argument('--qemu',type=Path,default=host.DEFAULT_QEMU)
    parser.add_argument('--origin-x',type=int,required=True);parser.add_argument('--origin-y',type=int,required=True)
    parser.add_argument('--duration',type=float,default=55);args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x',encoding='utf-8') as log:
        with redirect_stdout(lifecycle.Tee(sys.stdout,log)):
            record=run(args.output,args.card,args.group23,args.qemu.resolve(),(args.origin_x,args.origin_y),args.duration)
    raise SystemExit(0 if record['completed_observation'] else 1)
