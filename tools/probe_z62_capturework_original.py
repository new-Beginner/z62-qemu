"""Run unchanged C1.70 with r89 and explicit MAIN, without any completion injection.

This is a bounded original-code experiment, not the interactive acceptance
entry. All writes after baseline boot setup are ordinary C-source publications.
"""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

import run_reference_console as reference
import run_z62_transaction as transaction
import run_z62_capcom as capcom
import run_z62_raw_stream as stream
import run_z62_output_lineage as legacy
import run_z62_continuous_stats as statistics
import run_z62_raw_boundary as boundary
import run_z62_capturework as hardware
import z62_shutter_input_v2 as shutter
import z62_lens_contact as lens
import z62_workspace_paths as paths
import z62_workspace_console as host_paths
from z62_main_frame import make_packet,parse_packet
from z62_kernel_event_layout import contract,resolve
from record_z62_action_evidence import workspace,digest,require
from verify_z62_capturework_pixels_evidence import tile_resize

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.04-capturework-original-r90b'
MASTER_SHA='bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4'


def main_geometry(words):
    require(len(words)==2 and all(type(value) is int and 0<=value<=0xffffffff for value in words),
        'Complete raw geometry required')
    rows,columns=words
    require(not (rows|columns)&0xffff,'C source does not guess cropped geometry')
    width,height=columns>>16,rows>>16
    require(0<width<=4096 and 0<height<=4096 and not (width|height)&1 and width*height<=4*1024*1024,
        'MAIN geometry outside declared C source profile')
    return width,height


def virtual_ns(ticks,frequency):
    require(type(ticks) is int and ticks>=0 and type(frequency) is int and frequency>0,'Hardware clock unavailable')
    return ticks*1_000_000_000//frequency


def command_profile(command,group23,policy0=False):
    command=transaction.configure_command(command,True,True)
    command=capcom.configure_command(command,True)
    command=stream.configure_command(command,True,drain=True,paired=True)
    command=legacy.configure_command(command,geometry=True,retained=True,video=True,
        origin=(0,76),observe=True,stop_control=True,paired=False,lineage=False)
    command=statistics.configure_command(boundary.configure_command(command,True),True)
    command+=['-global','nikon-z72-boot-config.z62-preview=on',
        '-global','nikon-z72-boot-config.z62-preview-results=on',
        '-global','nikon-z62-sensor-config.laboratory-init-completion=on',
        '-global','nikon-z62-sensor-config.laboratory-mode-completion=on',
        '-device',f'loader,file={group23},addr=0x13420000,force-raw=on',
        '-trace','enable=nikon_z62_mmio_write']
    if policy0:
        import run_z62_capturework_policy as policy
        return policy.configure_command(command,True)
    return hardware.configure_command(command,True)


class HmpReader:
    def __init__(self,machine): self.machine=machine
    def read(self,address,size):
        require(not address&3 and not size&3,'Bounded aligned HMP data only')
        return struct.pack('<'+'I'*(size//4),*self.machine._words(address,size//4))


def read_physical(machine,address,size):
    data=bytearray()
    for offset in range(0,size,65536):
        count=min(65536,size-offset)
        machine.wire_file.write(f'read {address+offset:#x} {count:#x}\n'.encode()); machine.wire_file.flush()
        line=machine.wire_file.readline().decode().strip()
        require(line.startswith('OK 0x'),'Native qtest read did not complete')
        data.extend(bytes.fromhex(line.split()[1][2:]))
    require(len(data)==size,'Incomplete physical DMA readback')
    return bytes(data)


def snapshot(machine,layout):
    now=virtual_ns(*machine._key_clock())
    row={'virtual_time_ns':now,'capturework':json.loads(machine.qmp.command('qom-get',
        {'path':'/machine/master-input','property':'capturework-status'})),
        'geometry_words':machine._words(0x20069d00,2),
        'controls':machine._words(0x20068000,7)}
    try:
        if not getattr(machine,'capturework_boot_path',None):
            found=[]
            for entry in machine.qmp.command('qom-list',{'path':'/machine/unattached'}):
                if entry['type']=='child<nikon-z72-boot-config>':
                    path='/machine/unattached/'+entry['name']
                    if machine.qmp.command('qom-get',{'path':path,'property':'master-role'}): found.append(path)
            require(len(found)==1,'Single master processing device required')
            machine.capturework_boot_path=found[0]
        row['other_pipeline_counters']={name:machine.qmp.command('qom-get',{
            'path':machine.capturework_boot_path,'property':name}) for name in
            ('raw-stream-frames','grid-groups','grid-reason','preview-batches','preview-reason')}
        row['continuous_statistics']={name:machine.qmp.command('qom-get',{
            'path':'/machine/master-input','property':name}) for name in
            ('continuous-frames','continuous-batches','continuous-reason')}
    except (RuntimeError,ValueError,OSError) as exc:
        row['pipeline_counters_unavailable']=str(exc)
    try:
        row['kernel_event']=resolve(HmpReader(machine),layout)
        row['original_words']={hex(address):machine._words(address,count) for address,count in
            ((0xC1868AE8,1),(0xC1821EB8,1),(0xC23D9F14,6),(0xC1888084,1))}
    except (RuntimeError,ValueError,OSError) as exc:
        row['original_state_unavailable']={'type':type(exc).__name__,'message':str(exc)}
    return row


def run(qemu,card,group23,output,duration=8,wall_limit=300,policy0=False):
    qemu,card,group23,output=map(workspace,(qemu,card,group23,output))
    require(8<=duration<=30 and 30<=wall_limit<=600,'Bounded original window required')
    output.mkdir(parents=True,exist_ok=False)
    paths.ensure_alias()
    if policy0:
        import run_z62_capturework_policy as policy
        build=policy.verify_build(qemu)
    else: build=hardware.verify_build(qemu)
    require(digest(group23)=='c7dd14358b45b2813fdee85fc587bcdd5899f7a81e0d5830513d631235bcc700',
        'Reviewed synthetic group23 required')
    require(card.is_file() and card.suffix.lower() in ('.raw','.img') and card.stat().st_size%512==0,
        'Dedicated ordinary virtual card required')
    record={'schema':1,'version':VERSION,'completed_observation':False,'camera_accessed':False,
        'original_firmware_requested':True,'original_firmware_executed':False,
        'external_main_policy0_requested':policy0,'QEMU_binary_sha256':build['binary_sha256'],
        'no_ready_or_software_event_injection':True,'controls_after_baseline_boot':[],
        'publications':[],'samples':[],'DMA_frames':[],'downstream_ISP_integrated':False,
        'factory_capture_AF_or_flash_safety_verified':False,
        'driver_sources_before_run':{str(path):digest(path) for path in (Path(__file__),
            ROOT/'tools/z62_main_frame.py',ROOT/'tools/run_z62_capturework.py',
            ROOT/'tools/run_z62_capturework_policy.py',ROOT/'tools/z62_kernel_event_layout.py')}}
    machine=process=staged=None; old_popen=subprocess.Popen; old_path=list(sys.path)
    journal=(output/'observations.jsonl').open('x',encoding='utf-8')
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ,{'Z62_PROJECT_ROOT':str(ROOT),'Z62_PROJECT_DRIVE':'Q:/',
                'TEMP':'Q:/.runtime/tmp','TMP':'Q:/.runtime/tmp','PI_SCRATCH_DIR':'Q:/.runtime/tmp',
                'PYTHONDONTWRITEBYTECODE':'1'}))
            stack.enter_context(patch.object(reference,'Path',paths.WorkspacePath))
            staged,session=reference.stage('z62',paths.WorkspacePath(qemu),experimental_parameters=True,updates=True)
            source=staged/'source'; transaction.apply_console(source)
            capcom.apply_status(source); stream.apply_status(source); shutter.apply_console(source); lens.apply_console(source)
            host_paths.apply_console(source)
            record.update(session=str(staged),master_sha256=digest(staged/'inputs/master.bin'),
                original_card_sha256=digest(card),synthetic_parameters=session['parameters'])
            require(record['master_sha256']==MASTER_SHA,'Original master differs')
            layout=contract((staged/'inputs/master.bin').read_bytes())
            reference.install_native_process_adapter(staged); native_popen=subprocess.Popen
            class OriginalPopen(native_popen):
                def __init__(self,command,*args,**kwargs):
                    if isinstance(command,(list,tuple)) and Path(command[0]).name.lower()=='qemu-system-arm.exe':
                        command=command_profile(list(command),paths.WorkspacePath(group23),policy0)
                        require(any('snapshot=on' in value for value in command),'Virtual card snapshot required')
                        record['effective_command']=list(command)
                    super().__init__(command,*args,**kwargs)
            subprocess.Popen=OriginalPopen
            sys.path.insert(0,str(source))
            spec=importlib.util.spec_from_file_location('z62_capturework_original_host',source/'tools/z62_console.py')
            module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            args=SimpleNamespace(qemu=paths.WorkspacePath(qemu),master=staged/'inputs/master.bin',
                slave=staged/'inputs/slave.bin',controller=staged/'inputs/controller.bin',
                parameters=staged/'parameters',runs=staged/'runs',port=0,
                sd_card=paths.WorkspacePath(card),auto_menu=False,wsl=False,
                main_screen_experiment=False,sampling_source=False,input_trace=False,
                update_store=staged/'unused-update-store',update_image=None)
            machine=module.Z62Machine(args); require(machine.restart(),'Could not start own original session')
            start=time.monotonic(); next_source=0; publication=0; previous_completed=0
            epoch=int(hashlib.sha256(str(staged).encode()).hexdigest()[:16],16)
            inputs=output/'inputs'; inputs.mkdir(); frame_root=output/'frames'; frame_root.mkdir()
            published={}; reported=0
            while time.monotonic()-start<wall_limit:
                if machine.phase=='failed': raise RuntimeError('Original start failed: '+str(machine.error))
                if machine.phase!='running': time.sleep(.1); continue
                with machine.io:
                    process=machine.process
                    row=snapshot(machine,layout); record['samples'].append(row)
                    journal.write(json.dumps({'kind':'sample','value':row})+'\n'); journal.flush()
                    now=row['virtual_time_ns']; status=row['capturework']
                    if now>0: record['original_firmware_executed']=True
                    if status['completed']>previous_completed and status['valid']:
                        previous_completed=status['completed']; identity=status['publication']
                        if identity in published and len(record['DMA_frames'])<6:
                            packet_path=published[identity]; meta,raw=parse_packet(packet_path.read_bytes())
                            width,height,stride=status['width'],status['height'],status['stride']
                            actual=read_physical(machine,status['address'],stride*height)
                            path=frame_root/f'publication-{identity}.p12'
                            with path.open('xb') as handle: handle.write(actual)
                            record['DMA_frames'].append({'publication':identity,'source_sha256':digest(packet_path),
                                'packed_sha256':digest(path),'device_state':status,'virtual_time_ns':now,
                                'input_width':meta.width,'input_height':meta.height})
                    if now>=next_source and publication<24:
                        try:
                            width,height=main_geometry(row['geometry_words'])
                            next_source=now+500_000_000
                            publication+=1
                            gray=40 if publication%2 else 210
                            packet=make_packet(Image.new('RGB',(8,8),(gray,gray,gray)),width=width,height=height,
                                stride=2*width,epoch=epoch,publish_id=publication,frame_id=now*30//1_000_000_000,
                                virtual_time_ns=now)
                            path=inputs/f'publication-{publication}.z62m'
                            with path.open('xb') as handle: handle.write(packet)
                            attempt={'publication':publication,'virtual_time_ns':now,'gray':gray,
                                'width':width,'height':height,'packet_sha256':digest(path),'accepted':False}
                            record['publications'].append(attempt)
                            machine.qmp.command('qom-set',{'path':'/machine/master-input',
                                'property':'capturework-main-file','value':str(paths.WorkspacePath(path))})
                            attempt['accepted']=True; published[publication]=path
                            journal.write(json.dumps({'kind':'publication','value':attempt})+'\n'); journal.flush()
                        except (RuntimeError,ValueError,OSError) as exc:
                            failure={'kind':'source-rejection','virtual_time_ns':now,'message':str(exc)}
                            journal.write(json.dumps(failure)+'\n'); journal.flush()
                    if time.monotonic()>=reported:
                        print('ORIGINAL',now,status['completed'],status['reason'],len(record['publications']),flush=True)
                        reported=time.monotonic()+15
                    if now>=duration*1_000_000_000:
                        record['completed_observation']=True; break
                time.sleep(.15)
            else: raise TimeoutError('Original window reached wall limit')
            with machine.io:
                record['final']=snapshot(machine,layout)
                record['qemu_query_status']=machine.qmp.command('query-status')
                record['runtime_work']=str(machine.work)
                for filename in ('command.json','console.txt'):
                    path=machine.work/filename
                    if path.is_file():
                        with (output/filename).open('xb') as handle: handle.write(path.read_bytes())
            try:
                frame=machine.frame_png()
                with (output/'final-lcd.png').open('xb') as handle: handle.write(frame)
            except (OSError,RuntimeError,ValueError) as exc:
                record['LCD_capture_unavailable']=str(exc)
            machine.close(); record['process_exit_code']=process.poll()
            record['original_card_unchanged']=digest(card)==record['original_card_sha256']
            record['source_sha256']={str(path):digest(path) for path in (Path(__file__),
                ROOT/'tools/run_z62_capturework.py',ROOT/'tools/z62_main_frame.py',source/'tools/z62_console.py',
                source/'tools/web_console.py',source/'tools/z62_workspace_paths.py')}
            record['session_source_retained']=source.is_dir()
    except Exception as exc:
        record['failure']={'type':type(exc).__name__,'message':str(exc)}
    finally:
        if machine is not None and machine.work is not None:
            record['runtime_work']=str(machine.work)
            for filename in ('command.json','console.txt'):
                path=machine.work/filename
                if path.is_file() and not (output/filename).exists():
                    with (output/filename).open('xb') as handle: handle.write(path.read_bytes())
        if machine is not None and not machine.shutdown.is_set():
            try:
                if machine.work and (machine.work/'console.txt').is_file() and not (output/'console.txt').exists():
                    with (output/'console.txt').open('xb') as handle: handle.write((machine.work/'console.txt').read_bytes())
                machine.close()
            except Exception as exc: record['cleanup_failure']=str(exc)
        if process is not None: record['process_exit_code']=process.poll()
        if staged is not None:
            candidates=[Path(__file__),ROOT/'tools/z62_main_frame.py',ROOT/'tools/run_z62_capturework.py',
                ROOT/'tools/run_z62_capturework_policy.py',staged/'source/tools/z62_console.py',
                staged/'source/tools/web_console.py',staged/'source/tools/z62_workspace_paths.py']
            record['source_sha256']={str(path):digest(path) for path in candidates if path.is_file()}
        record['driver_sources_unchanged']=all(digest(Path(path))==expected for path,expected in
            record['driver_sources_before_run'].items())
        if record.get('original_card_sha256'):
            record['original_card_unchanged']=digest(card)==record['original_card_sha256']
        subprocess.Popen=old_popen; sys.path[:]=old_path
        journal.close()
        with (output/'result.json').open('x',encoding='utf-8') as handle: json.dump(record,handle,ensure_ascii=False,indent=2)
    print(json.dumps({key:record.get(key) for key in ('completed_observation','failure','cleanup_failure','process_exit_code')},ensure_ascii=False),flush=True)
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True); parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--duration',type=float,default=8)
    parser.add_argument('--wall-limit',type=float,default=300)
    parser.add_argument('--source-policy0',action='store_true'); args=parser.parse_args()
    result=run(args.qemu,args.card,args.group23,args.output,args.duration,args.wall_limit,args.source_policy0)
    raise SystemExit(0 if result['completed_observation'] and result.get('process_exit_code')==0 and
        not result.get('failure') and not result.get('cleanup_failure') else 1)
