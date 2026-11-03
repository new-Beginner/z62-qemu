"""Saved original C1.70 DMA, CPU W1C and non-atomic kernel snapshot verification."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
from PIL import Image

import run_z62_capturework_policy as hardware
import z62_mmio_filtered_trace as trace
from z62_main_frame import parse_packet
from prepare_reference_firmware import PROFILES
from record_z62_action_evidence import workspace,digest,require
from verify_z62_capturework_pixels_evidence import tile_resize

ROOT=Path(__file__).resolve().parents[1]


def verify(window_path,native_path,output):
    window_path,native_path,output=map(workspace,(window_path,native_path,output))
    require(not output.exists(),'Use a new original-window receipt')
    window=json.loads(window_path.read_text(encoding='utf-8'))
    native=json.loads(native_path.read_text(encoding='utf-8')); build=hardware.verify_build()
    require(window['completed_observation'] and not window.get('failure') and not window.get('cleanup_failure') and
        window['process_exit_code']==0 and window['original_firmware_executed'] and
        window['driver_sources_unchanged'] and window['original_card_unchanged'],'Original window incomplete')
    require(native['completed'] and native['default_policy_off_preserves_strict_recipe'] and
        native['unknown_shared_source_word_rejected'] and all(code==0 for code in native['process_exit_codes']),
        'Explicit policy native acceptance incomplete')
    require(window['QEMU_binary_sha256']==native['QEMU_binary_sha256']==build['binary_sha256'],
        'Original/native executable identities differ')
    for path,expected in window['source_sha256'].items(): require(digest(Path(path))==expected,'Original source changed')
    archive=json.loads((window_path.parent/'source-archive.json').read_text(encoding='utf-8'))
    require(archive['result_sha256']==digest(window_path),'Original source archive/result differs')
    for name,expected in archive['source_sha256'].items():
        require(digest(window_path.parent/'source-snapshot'/name)==expected,'Archived original host differs')
    session=workspace(window['session'])
    for _,(name,size,expected) in PROFILES['z62']['members'].items():
        path=session/'inputs'/name
        require(path.stat().st_size==size and digest(path)==expected,'Original firmware member changed: '+name)
    rows=trace.parse_lines((window_path.parent/'console.txt').read_text(encoding='utf-8').splitlines())
    master=[row for row in rows if row['board_view']=='master']
    # Resolve committed geometry from actual CPU write order, not a later
    # register readback or r86 default. Require one stable qualified geometry.
    addresses=(0x20069d00,0x20069d04,0x20069e78,0x20069e7c,0x20069f00)
    shadow={}; geometries=[]
    for row in master:
        if row['address'] in addresses: shadow[row['address']]=row['value']
        if row['address'] in (0x20068100,0x20068104) and row['value']&4 and all(a in shadow for a in addresses):
            geometries.append(tuple(shadow[a] for a in addresses))
    require(geometries and len(set(geometries))==1,'Window needs generation-specific geometry reconstruction')
    ih,iw,mh,mw,enable=geometries[0]
    require(not (ih|iw|mh|mw)&0xffff and enable==0x11,'Unsupported committed original geometry')
    ih,iw,mh,mw=(value>>16 for value in (ih,iw,mh,mw))
    publications={row['publication']:row for row in window['publications'] if row['accepted']}
    total=0; saved=[]
    for row in window['DMA_frames']:
        index=row['publication']; packet_path=window_path.parent/f'inputs/publication-{index}.z62m'
        packed_path=window_path.parent/f'frames/publication-{index}.p12'
        require(index in publications and digest(packet_path)==row['source_sha256']==publications[index]['packet_sha256'] and
            digest(packed_path)==row['packed_sha256'],'Saved original DMA/source identity changed')
        meta,data=parse_packet(packet_path.read_bytes()); state=row['device_state']
        require((meta.width,meta.height)==(iw,ih) and state['valid'] and state['external_main_policy0'] and
            state['output_shared_source_word']==0x200040 and state['publication']==index and
            state['frame']==meta.frame_id and state['time_ns']==meta.virtual_time_ns,
            'Original DMA descriptor or frame identity differs')
        require(state['bits']==12 and state['codec']==1 and len(state['lookup'])==256,'Unexpected transfer domain')
        ow,oh,stride=state['width'],state['height'],state['stride']
        source=np.frombuffer(data,dtype='<u2').reshape(ih,meta.stride//2)[:,:iw]
        expected=np.asarray(state['lookup'],dtype=np.uint16)[tile_resize(tile_resize(source,mw,mh),ow,oh)>>8]
        packed=np.frombuffer(packed_path.read_bytes(),dtype=np.uint8).reshape(oh,stride)
        triples=packed[:,:ow*12//8].reshape(oh,ow//2,3).astype(np.uint16)
        actual=np.empty((oh,ow),dtype=np.uint16)
        actual[:,0::2]=triples[:,:,0]|((triples[:,:,1]&15)<<8)
        actual[:,1::2]=(triples[:,:,1]>>4)|(triples[:,:,2]<<4)
        mismatch=int(np.count_nonzero(actual!=expected)); require(mismatch==0,'Original-window DMA sample mismatch')
        total+=ow*oh; saved.append({'publication':index,'pixels':ow*oh,'mismatches':mismatch,
            'packed_sha256':digest(packed_path),'source_virtual_time_ns':meta.virtual_time_ns})
    require(len(saved)==6 and total==9138504,'Unexpected retained original frame scope')
    front=[row for row in master if row['address']==0x20068210 and row['value']==0x18]
    raw=[row for row in master if row['address']==0x20068290 and row['value']==0x80]
    completed=window['final']['capturework']['completed']
    require(len(front)>=completed and len(raw)>=completed and all(row['cpu'] in (0,1) for row in front+raw),
        'Original CPU W1C acknowledgement history incomplete')
    require(window['controls_after_baseline_boot']==[] and not any(',data=' in value for value in window['effective_command']),
        'Host changed original software or supplied an executing test loop')
    patterns=Counter(row['kernel_event']['pattern'] for row in window['samples'] if 'kernel_event' in row)
    require(patterns,'No validated kernel control-block samples')
    with Image.open(window_path.parent/'final-lcd.png') as image:
        image.load(); lcd_size=list(image.size); lcd_black=not np.any(np.asarray(image.convert('RGB')))
    source_files=[Path(__file__),ROOT/'tools/z62_capturework_policy_device.py',ROOT/'tools/build_z62_capturework_policy.py',
        ROOT/'tools/run_z62_capturework_policy.py',hardware.DEFAULT_QEMU.parent.parent/'capturework-policy-build-manifest.json']
    source_files+=list((session/'source/tools').glob('*.py'))
    result={'schema':1,'completed_evidence_check':True,'QEMU_binary_sha256':build['binary_sha256'],
        'original_window_sha256':digest(window_path),'policy_native_result_sha256':digest(native_path),
        'original_code_window_ns':window['final']['virtual_time_ns'],'original_code_executed':True,
        'virtual_card_source_unchanged':True,'DMA_completed_counter':completed,
        'retained_DMA_frames':saved,'actual_original_window_pixels_checked':total,'sample_mismatches':0,
        'original_CPU_front_W1C_count':len(front),'original_CPU_packed_W1C_count':len(raw),
        'committed_geometry_from_CPU_trace':[iw,ih,mw,mh],
        'all_trace_writes_accepted_verified':False,'kernel_pattern_samples':dict(patterns),
        'kernel_samples_non_atomic':True,'kernel_setter_call_or_return_traced':False,
        'kernel_condition_never_satisfied_proven':False,'last_kernel_pattern':window['final']['kernel_event']['pattern'],
        'last_original_words':window['final']['original_words'],
        'last_other_pipeline_counters':window['final']['other_pipeline_counters'],
        'last_continuous_statistics':window['final']['continuous_statistics'],
        'LCD_size':lcd_size,'LCD_all_black':lcd_black,'LCD_sha256':digest(window_path.parent/'final-lcd.png'),
        'padding_preservation_in_original_window_verified':False,
        'downstream_ISP_integrated':False,'factory_mode_roundtrip_capture_AF_or_flash_safety_verified':False,
        'camera_accessed':False,'source_sha256':{str(path):digest(path) for path in source_files}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle: json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({key:value for key,value in result.items() if key not in ('retained_DMA_frames','source_sha256')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--window',type=Path,required=True)
    parser.add_argument('--native',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); verify(args.window,args.native,args.output)
