"""Offline r92 native five-plane and original CW/ACK evidence verification.

Original statistics values were not retained: do not turn counters or ACKs
into a claim of independent original-window five-plane numerical validation.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import numpy as np
from PIL import Image

import probe_z62_capturework_statistics as native
import run_z62_capturework_statistics as hardware
import z62_mmio_filtered_trace as trace
from z62_main_frame import parse_packet
from prepare_reference_firmware import PROFILES
from record_z62_action_evidence import workspace,digest,require


def verify(native_path,window_path,output):
    native_path,window_path,output=map(workspace,(native_path,window_path,output))
    require(not output.exists(),'Use a new r92 evidence receipt')
    n=json.loads(native_path.read_text(encoding='utf-8')); w=json.loads(window_path.read_text(encoding='utf-8'))
    build=hardware.verify_build(); wrapper=window_path.parent/'bridge-window.json'
    wrapper_record=json.loads(wrapper.read_text(encoding='utf-8'))
    require(n['completed'] and len(n['frames'])==6 and all(code==0 for code in n['process_exit_codes']),
        'Native source bridge validation incomplete')
    require(w['completed_observation'] and w['process_exit_code']==0 and not w.get('failure') and
        not w.get('cleanup_failure') and w['original_firmware_executed'] and w['driver_sources_unchanged'] and
        w['original_card_unchanged'],'Original window incomplete')
    require(n['QEMU_binary_sha256']==w['QEMU_binary_sha256']==build['binary_sha256'],
        'Native and original binaries differ')
    require(wrapper_record['base_result_sha256']==digest(window_path) and wrapper_record['bridge_enabled'] and
        wrapper_record['wrapper_sources_unchanged'],'Original wrapper differs')
    sources={str(Path(__file__)):digest(Path(__file__)),**wrapper_record['wrapper_sources_sha256']}
    for receipt_path in (native_path,window_path):
        record=json.loads(receipt_path.read_text(encoding='utf-8'))
        archive=json.loads((receipt_path.parent/'source-archive.json').read_text(encoding='utf-8'))
        require(archive['result_sha256']==digest(receipt_path),'Result/archive binding differs')
        for name,sha in record['source_sha256'].items():
            require(digest(Path(name))==sha,'Bound runtime source changed: '+name)
            sources[name]=sha
        for name,sha in archive['source_sha256'].items():
            require(digest(receipt_path.parent/'source-snapshot'/name)==sha,'Archived source differs')
    for name,sha in sources.items(): require(digest(Path(name))==sha,'Wrapper/verifier source changed')
    session=workspace(w['session'])
    for _,(name,size,sha) in PROFILES['z62']['members'].items():
        path=session/'inputs'/name
        require(path.stat().st_size==size and digest(path)==sha,'Original firmware member changed')
    command=w['effective_command']
    require('nikon-z72-boot-config.z62-card-detect=on' in command and
        'nikon-z72-input-config.z62-capturework-statistics=on' in command,'Missing explicit experiment qualification')
    rows=[r for r in trace.parse_lines((window_path.parent/'console.txt').read_text(encoding='utf-8').splitlines())
        if r['board_view']=='master']
    addresses=(0x20069d00,0x20069d04,0x20069e78,0x20069e7c,0x20069f00)
    shadow={}; geometry=[]
    for row in rows:
        if row['address'] in addresses: shadow[row['address']]=row['value']
        if row['address'] in (0x20068100,0x20068104) and row['value']&4 and all(a in shadow for a in addresses):
            geometry.append(tuple(shadow[a] for a in addresses))
    require(geometry and len(set(geometry))==1,'Need generation-specific committed original geometry')
    ih,iw,mh,mw,enable=geometry[0]
    require(not (ih|iw|mh|mw)&0xffff and enable==0x11,'Unsupported original geometry')
    iw,ih,mw,mh=iw>>16,ih>>16,mw>>16,mh>>16
    native_output_bytes=0
    for frame in n['frames']:
        packet_path=native_path.parent/frame['MAIN_path']
        require(digest(packet_path)==frame['MAIN_sha256'],'Native MAIN bytes changed')
        oracle=native.expected(packet_path.read_bytes(),(iw,ih,mw,mh,1514,1006))
        require(len(frame['outputs'])==5 and frame['legacy_RAW_accepted']==0,'Native output provenance incomplete')
        for row in frame['outputs']:
            path=native_path.parent/row['path']; data=path.read_bytes()
            require(digest(path)==row['sha256'] and data==oracle[row['channel']],
                'Native independently recomputed statistics differ')
            native_output_bytes+=len(data)
    pixels=0
    for frame in w['DMA_frames']:
        index=frame['publication']; packet_path=window_path.parent/f'inputs/publication-{index}.z62m'
        packed_path=window_path.parent/f'frames/publication-{index}.p12'
        require(digest(packet_path)==frame['source_sha256'] and digest(packed_path)==frame['packed_sha256'],
            'Original MAIN or DMA bytes changed')
        meta,raw=parse_packet(packet_path.read_bytes()); status=frame['device_state']
        require((meta.width,meta.height)==(iw,ih) and status['codec']==1 and status['bits']==12,
            'Original source/transfer differs')
        source=np.frombuffer(raw,dtype='<u2').reshape(meta.height,meta.stride//2)[:,:meta.width]
        ow,oh,stride=status['width'],status['height'],status['stride']
        expected=np.asarray(status['lookup'],dtype=np.uint16)[native.cw.tile_resize(
            native.cw.tile_resize(source,mw,mh),ow,oh)>>8]
        data=np.frombuffer(packed_path.read_bytes(),dtype=np.uint8).reshape(oh,stride)
        triples=data[:,:ow*12//8].reshape(oh,ow//2,3).astype(np.uint16)
        actual=np.empty((oh,ow),dtype=np.uint16)
        actual[:,0::2]=triples[:,:,0]|((triples[:,:,1]&15)<<8)
        actual[:,1::2]=(triples[:,:,1]>>4)|(triples[:,:,2]<<4)
        require(np.array_equal(actual,expected),'Original retained DMA samples differ')
        pixels+=ow*oh
    require(len(w['DMA_frames'])==6 and pixels==9138504,'Incomplete original retained DMA scope')
    final=w['final']; cw=final['capturework']; bridge=final['capturework_statistics']; stats=final['continuous_statistics']
    ack20=sum(r['address']==0x20068270 and bool(r['value']&0x20) for r in rows)
    ack80=sum(r['address']==0x20068270 and bool(r['value']&0x80) for r in rows)
    require(cw['completed']==bridge['published']==bridge['consumed']==stats['continuous-frames']==ack20==13 and
        stats['continuous-batches']==ack80==2,'Original statistics DMA/source/CPU ACK counts differ')
    require(all(r['legacy_RAW_accepted']==0 and r['other_pipeline_counters']['raw-stream-frames']==0
        for r in w['samples']),'Legacy RAW counters changed')
    image=Image.open(window_path.parent/'final-lcd.png').convert('RGB')
    patterns=Counter(r.get('kernel_event',{}).get('pattern','unavailable') for r in w['samples'])
    result={'schema':1,'completed_evidence_check':True,'binary_sha256':build['binary_sha256'],
        'native_result_sha256':digest(native_path),'original_result_sha256':digest(window_path),
        'original_wrapper_sha256':digest(wrapper),'native_statistics_frames':6,
        'native_five_plane_output_bytes_independently_recomputed':native_output_bytes,
        'native_statistics_byte_mismatches':0,'original_retained_DMA_samples_checked':pixels,
        'original_DMA_sample_mismatches':0,'original_window_ns':final['virtual_time_ns'],
        'original_CW_DMA_and_statistics_frames':13,'original_statistics_batches':2,
        'original_CPU_statistics_slot_ACK_count':ack20,'original_CPU_statistics_batch_ACK_count':ack80,
        'legacy_RAW_counters_always_zero':True,'original_statistics_values_independently_verified':False,
        'kernel_pattern_samples_non_atomic':dict(patterns),'kernel_setter_or_return_traced':False,
        'condition_never_satisfied_proven':False,'LCD_size':image.size,'LCD_all_black':not np.any(np.asarray(image)),
        'preview_batches':final['other_pipeline_counters']['preview-batches'],
        'grid_reason_is_not_a_direct_supported_property':True,'virtual_card_source_unchanged':True,
        'process_exit_code':w['process_exit_code'],'camera_accessed':False,
        'whole_camera_capture_AF_or_flash_safety_verified':False,'source_sha256':sources}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle: json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--native',type=Path,required=True)
    parser.add_argument('--window',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); verify(args.native,args.window,args.output)
