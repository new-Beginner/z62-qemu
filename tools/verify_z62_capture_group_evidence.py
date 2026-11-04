"""Verify r93 native numerical payloads and the original zero-input boundary."""
import argparse
from collections import Counter
import json
from pathlib import Path
import numpy as np
from PIL import Image
import probe_z62_capture_group as native
import run_z62_capture_group as hardware
import z62_capture_group_device as device
import z62_mmio_filtered_trace as trace
from prepare_reference_firmware import PROFILES
from z62_main_frame import parse_packet
from record_z62_action_evidence import workspace,digest,require


def verify(native_path,window_path,contract_path,output):
    native_path,window_path,contract_path,output=map(workspace,(native_path,window_path,contract_path,output))
    require(not output.exists(),'Use new group evidence receipt')
    n=json.loads(native_path.read_text(encoding='utf-8'));w=json.loads(window_path.read_text(encoding='utf-8'))
    contract=json.loads(contract_path.read_text(encoding='utf-8'));build=hardware.verify_build()
    require(n['completed'] and len(n['frames'])==7 and len(n['negative_cases'])==5 and
        all(code==0 for code in n['process_exit_codes']),'Native group matrix incomplete')
    require(n['QEMU_binary_sha256']==w['QEMU_binary_sha256']==build['binary_sha256'],
        'Native/original binary identity differs')
    require(w['completed_observation'] and w['process_exit_code']==0 and not w.get('failure') and
        not w.get('cleanup_failure') and w['original_card_unchanged'] and w['driver_sources_unchanged'],
        'Original observation incomplete')
    sources={str(Path(__file__)):digest(Path(__file__))}
    for record in (n,w,contract):sources.update(record['source_sha256'])
    supplement=window_path.parent/'group-window.json';extra=json.loads(supplement.read_text(encoding='utf-8'))
    require(extra['result_sha256']==digest(window_path) and extra['original_zero_parameters_not_replaced'],
        'Original group wrapper binding differs')
    sources.update(extra['source_sha256'])
    older=json.loads((window_path.parent/'bridge-window.json').read_text(encoding='utf-8'))
    require(older['base_result_sha256']==digest(window_path) and older['wrapper_sources_unchanged'],'Original statistics wrapper differs')
    sources.update(older['wrapper_sources_sha256'])
    work=hardware.DEFAULT_QEMU.parent.parent
    reference=work/'reference-build-manifest.json'
    source=Path(json.loads(reference.read_text(encoding='utf-8'))['source'])
    for path in (Path(native.__file__),Path(hardware.__file__),Path(device.__file__),
            device.ROOT/'tools/build_z62_capture_group.py',reference,work/'capture-group-build-manifest.json',
            *(source/name for name in build['generated_source_sha256']),
            *(device.DIRECTORY/name for name in device.HEADERS)):
        sources[str(path)]=digest(path)
    for name,sha in sources.items():require(digest(Path(name))==sha,'Bound source changed: '+name)
    checked=0
    for frame in n['frames']:
        path=native_path.parent/frame['MAIN_path'];require(digest(path)==frame['MAIN_sha256'],'Saved native MAIN changed')
        meta,_=parse_packet(path.read_bytes());status=frame['source']
        require((meta.epoch,meta.publish_id,meta.frame_id,meta.virtual_time_ns)==
            (status['epoch'],status['publication'],status['frame'],status['time_ns']),'Native MAIN identity differs')
        profile={int(k,16):v for k,v in frame['profile'].items()}
        expected=native.expected(path.read_bytes(),profile,status['cursor'],status['bank'],frame['unclassified_marker'])
        for row in frame['outputs']:
            data_path=native_path.parent/row['path'];data=data_path.read_bytes()
            require(digest(data_path)==row['sha256'] and data==expected[row['family']],
                'Independent re-computation of group payload differs')
            checked+=len(data)
        require(frame['result_write_ignored'],'Native result readonly check incomplete')
    require(checked==18528,'Unexpected native output family scope')
    for row in n['negative_cases']:
        require(row['status']['completed']==0 and row['status']['pending']==0 and row['status']['rejected']>0,
            'Negative profile produced group data')
    session=workspace(w['session'])
    for _,(name,size,sha) in PROFILES['z62']['members'].items():
        path=session/'inputs'/name;require(path.stat().st_size==size and digest(path)==sha,'Original firmware changed')
    rows=[r for r in trace.parse_lines((window_path.parent/'console.txt').read_text(encoding='utf-8').splitlines())
        if r['board_view']=='master']
    configured={r['address']:r['value'] for r in rows}
    require(all(configured.get(0x2006b880+i*4)==0 for i in range(65)) and
        all(configured.get(0x2006b820+f*32+i*4)==0 for f in range(3) for i in range(8)),
        'Original zero-parameter boundary changed')
    final=w['final'];group=final['capture_group']
    require(group['enabled'] and group['committed'] and group['completed']==0 and group['rejected']>0 and
        group['reason']==3 and group['pending']==0,'Original group did not preserve explicit numeric rejection')
    require(final['capturework']['completed']>0 and final['continuous_statistics']['continuous-frames']>0 and
        all(r['legacy_RAW_accepted']==0 for r in w['samples']),'Independent CW/statistics regressed')
    image=Image.open(window_path.parent/'final-lcd.png').convert('RGB')
    patterns=Counter(r.get('kernel_event',{}).get('pattern','unavailable') for r in w['samples'])
    result={'schema':1,'completed_evidence_check':True,'binary_sha256':build['binary_sha256'],
        'native_result_sha256':digest(native_path),'original_result_sha256':digest(window_path),
        'contract_sha256':digest(contract_path),'native_frames_independently_recomputed':7,
        'native_output_bytes_independently_recomputed':checked,'native_output_mismatches':0,
        'original_window_ns':final['virtual_time_ns'],'original_group_completed':0,
        'original_group_rejected':group['rejected'],'original_group_reason':group['reason'],
        'original_CW_completed':final['capturework']['completed'],
        'original_statistics_frames':final['continuous_statistics']['continuous-frames'],
        'curve_and_filter_words_explicitly_written_zero':True,'physical_erasure_proven':False,
        'parameters_or_ready_replaced':False,'original_group_numerical_acceptance':False,
        'legacy_RAW_accepted_always_zero':True,'LCD_size':image.size,'LCD_all_black':not np.any(np.asarray(image)),
        'kernel_pattern_samples_non_atomic':dict(patterns),'kernel_setter_or_return_traced':False,
        'preview_batches':final['other_pipeline_counters']['preview-batches'],
        'virtual_card_source_unchanged':True,'process_exit_code':w['process_exit_code'],'camera_accessed':False,
        'whole_camera_AF_or_flash_safety_verified':False,'source_sha256':sources}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_sha256','kernel_pattern_samples_non_atomic')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--native',type=Path,required=True)
    parser.add_argument('--window',type=Path,required=True);parser.add_argument('--contract',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    verify(args.native,args.window,args.contract,args.output)
