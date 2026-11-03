"""Independently decode saved r89 guest DMA and verify exact build/source binds."""
import argparse
import json
from pathlib import Path

import numpy as np

from record_z62_action_evidence import workspace,digest,require
from probe_z62_capturework_pixels import profile
from verify_z62_capturework_pixels_evidence import tile_resize
from z62_main_frame import parse_packet
import run_z62_capturework as hardware
import z62_capturework_device as device

ROOT=Path(__file__).resolve().parents[1]


def verify(native_path,state_path,regression_path,output):
    native_path,state_path,regression_path,output=map(workspace,(native_path,state_path,regression_path,output))
    require(not output.exists(),'Use new evidence receipt path')
    native=json.loads(native_path.read_text(encoding='utf-8'))
    state=json.loads(state_path.read_text(encoding='utf-8'))
    require(native['completed'] and not native['firmware_executed'] and native['synthetic_ARM_loops_only'] and
        native['process_exit_codes']==[0,0] and native['state_sha256']==digest(state_path),'Native window incomplete')
    for name,expected in native['source_sha256'].items(): require(digest(Path(name))==expected,'Native source changed')
    source_archive=json.loads((native_path.parent/'source-archive.json').read_text(encoding='utf-8'))
    require(source_archive['result_sha256']==digest(native_path),'Native archive/result binding differs')
    for name,expected in source_archive['source_sha256'].items():
        require(digest(native_path.parent/'source-snapshot'/name)==expected,'Native source archive differs')
    dimensions,bits,stride,lut=profile(state); iw,ih,mw,mh,ow,oh=dimensions
    require(bits==12 and [row['publication'] for row in native['frames']]==[1,2,3,4,6,8],'Unexpected native frame set')
    total=0; frames=[]
    for row in native['frames']:
        index=row['publication']; packet=native_path.parent/f'frames/publication-{index}.z62m'
        packed=native_path.parent/f'frames/publication-{index}.p12'
        require(digest(packet)==row['packet_sha256'] and digest(packed)==row['packed_sha256'],'Native frame bytes changed')
        meta,source_bytes=parse_packet(packet.read_bytes())
        observed=row['device_state']
        require(observed['valid'] and observed['bits']==bits and observed['codec']==1 and observed['lookup']==lut and
            (observed['publication'],observed['frame'],observed['time_ns'],observed['address'])==
            (index,meta.frame_id,meta.virtual_time_ns,int(row['address'],16)),'Frozen output descriptor differs')
        require((meta.width,meta.height)==(iw,ih) and observed['pending_front']==0x18 and
            observed['pending_raw']==0x80,'MAIN geometry or completion causes differ')
        source=np.frombuffer(source_bytes,dtype='<u2').reshape(ih,meta.stride//2)[:,:iw]
        expected=np.asarray(lut,dtype=np.uint16)[tile_resize(tile_resize(source,mw,mh),ow,oh)>>8]
        rows=np.frombuffer(packed.read_bytes(),dtype=np.uint8).reshape(oh,stride)
        values=rows[:,:ow*12//8].reshape(oh,ow//2,3).astype(np.uint16)
        actual=np.empty((oh,ow),dtype=np.uint16)
        actual[:,0::2]=values[:,:,0]|((values[:,:,1]&15)<<8)
        actual[:,1::2]=(values[:,:,1]>>4)|(values[:,:,2]<<4)
        mismatches=int(np.count_nonzero(actual!=expected))
        require(mismatches==0 and np.all(rows[:,ow*12//8:]==0xa5),'Saved guest DMA numerical/padding check failed')
        total+=ow*oh
        frames.append({'publication':index,'bank':observed['bank'],'slot':observed['slot'],
            'pixels_checked':ow*oh,'mismatches':mismatches,'packed_sha256':digest(packed)})
    require(total==native['actual_pixels_checked']==9138504 and native['actual_successful_DMA_frames_total']==6,
        'Native full-frame sample scope differs')
    require(len(native['irq_notifications'])==36 and native['irq_notifications'].count('IRQ raise 0')==6 and
        native['irq_notifications'].count('IRQ raise 1')==6 and native['irq_notifications'].count('IRQ raise 2')==6,
        'Actual three-output event notification history differs')
    binding=hardware.verify_build(); work=hardware.DEFAULT_QEMU.parent.parent
    require(binding['binary_sha256']==native['QEMU_binary_sha256'],'Native executable differs')
    root=json.loads((work/'reference-build-manifest.json').read_text(encoding='utf-8'))
    for name,expected in root['runtime_dll_sha256'].items(): require(digest(work/'runtime'/name)==expected,'Runtime DLL changed')
    require(digest(ROOT/'.build/z62-output-lineage-2026.11.03-r69/runtime/qemu-system-arm.exe')==
        binding['parent_binary_sha256'],'Frozen r69 executable changed')
    regression=json.loads(regression_path.read_text(encoding='utf-8'))
    require(regression['completed'] and (regression['tests'],regression['failures'],regression['errors'],regression['skipped'])==
        (698,0,0,0) and digest(regression_path.with_suffix('.log'))==regression['log_sha256'],'Full Python regression incomplete')
    raw_path=native_path.parent.parent/'legacy-raw-1.json'
    lineage_path=native_path.parent.parent/'legacy-lineage-1.json'
    raw=json.loads(raw_path.read_text(encoding='utf-8'))
    lineage=json.loads(lineage_path.read_text(encoding='utf-8'))
    require(raw['binary_sha256']==binding['binary_sha256'] and not raw['firmware_loaded'] and
        raw['checks'][1]['four_slots_full_readback'] and raw['checks'][1]['row_padding_and_guards'] and
        raw['checks'][1]['raw_complete_success_only'],'Legacy real RAW check incomplete')
    require(lineage['completed'] and lineage['qemu_sha256']==binding['binary_sha256'] and
        lineage['actual_photo_provenance'] and lineage['actual_video_provenance'] and
        lineage['default_off_preserves_data'],'Legacy ISP/lineage check incomplete')
    for session in native['sessions']:
        index=native['sessions'].index(session)+1
        require(session['exit_code']==0 and digest(native_path.parent/f'qemu-{index}.log')==session['log_sha256'],
            'Native session did not close with preserved logs')
    sources=[Path(__file__),ROOT/'tools/build_z62_capturework.py',ROOT/'tools/z62_capturework_device.py',
        ROOT/'tools/run_z62_capturework.py',work/'capturework-build-manifest.json',work/'reference-build-manifest.json']
    sources += [device.DIRECTORY/name for name in device.HEADERS]
    sources += [Path(root['source'])/name for name in binding['generated_source_sha256']]
    result={'schema':1,'completed_evidence_check':True,'QEMU_binary_sha256':binding['binary_sha256'],
        'native_result_sha256':digest(native_path),'regression_result_sha256':digest(regression_path),
        'legacy_RAW_result_sha256':digest(raw_path),'legacy_ISP_lineage_result_sha256':digest(lineage_path),
        'native_sources_archived':len(source_archive['source_sha256']),'frames':frames,
        'actual_QEMU_DMA_pixels_checked':total,'sample_mismatches':0,'padding_preserved':True,
        'three_IRQ_outputs_observed':True,'all_native_children_clean_exit':True,
        'legacy_RAW_and_ISP_checks_recorded_separately':True,'r69_executable_unchanged':True,
        'QEMU_device_integrated':True,'source_and_numerical_layer':'C explicit MAIN and nearest/LUT packing',
        'full_current_Python_tests':698,'full_current_Python_failures_errors_skips':[0,0,0],
        'original_firmware_executed_in_native_checks':False,'factory_functional_acceptance_eligible':False,
        'factory_mode_roundtrip_verified':False,'downstream_ISP_CaptureWork_input_integrated':False,
        'complete_snapshot_supported':False,'inflight_worker_cancel_race_exhaustively_verified':False,
        'AF_verified':False,'camera_accessed':False,
        'source_sha256':{str(path):digest(path) for path in sources}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle: json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('frames','source_sha256')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native',type=Path,required=True); parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--regression',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); verify(args.native,args.state,args.regression,args.output)
