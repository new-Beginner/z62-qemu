"""Independent C inline readout data/route audit, preserving original failure."""
import argparse
import json
from pathlib import Path
import struct
import numpy as np
import run_z62_input_readout as hardware
from z62_main_stream import reconstruct
from z62_main_frame import parse_packet
from prepare_reference_firmware import PROFILES
from record_z62_action_evidence import workspace,digest,require


def numerical(packet):
    meta,payload=parse_packet(packet)
    words=np.frombuffer(payload,dtype='<u2').reshape(meta.height,meta.stride//2)[:,:meta.width]
    raw=words.astype('<u2').tobytes();value=14695981039346656037
    for byte in raw:value=((value^byte)*1099511628211)&0xffffffffffffffff
    return int(words.astype(np.uint64).sum()),value,len(raw)


def verify(native_path,original_path,output):
    native_path,original_path,output=map(workspace,(native_path,original_path,output))
    require(not output.exists(),'Use new readout evidence result')
    native=json.loads(native_path.read_text(encoding='utf-8'));original=json.loads(original_path.read_text(encoding='utf-8'))
    build=hardware.verify_build()
    require(native['completed'] and all(code==0 for code in native['process_exit_codes']) and
        native['binary_sha256']==original['binary_sha256']==build['binary_sha256'],'Native readout/build identities differ')
    packet=(native_path.parent/'source-1.z62m').read_bytes();total,fnv,size=numerical(packet)
    require((native['output_status']['sum_u16'],native['output_status']['fnv1a64'],native['output_status']['last_bytes'])==
        (total,fnv,size) and size==549440,'Native all-row byte consumption differs')
    require(original['completed_observation'] and original['process_exit_code']==0 and not original.get('failure')
        and not original.get('cleanup_failure') and original['source_bytes_unchanged'] and original['original_card_unchanged'],
        'Original readout experiment incomplete')
    route_path=original_path.parent/'input-readout-stream.json';route=json.loads(route_path.read_text(encoding='utf-8'))
    require(route['result_sha256']==digest(original_path),'Source port audit belongs to another run')
    routes={r['publication']:r for r in route['actual_accepted_source_routes']}
    require(len(routes)==len(original['publications'])==original['accepted_publications'],'Source port audit incomplete')
    packets={};numerics={};cache={};readout_routes=[]
    for row in original['publications']:
        content=reconstruct(original_path.parent/'main-source',row);meta,_=parse_packet(content)
        actual=routes[meta.publish_id]
        require((meta.epoch,meta.frame_id,meta.virtual_time_ns)==(actual['epoch'],actual['frame'],actual['time_ns']),
            'Source port identity differs from actual packet')
        if actual['port']=='input-readout-file':
            require((meta.width,meta.height)==(2020,136),'Inline packet has unsupported geometry')
            key=row['payload']['sha256']
            if key not in cache:cache[key]=numerical(content)
            numerics[meta.publish_id]=cache[key];readout_routes.append(actual)
        else:require(actual['port']=='capturework-main-file','Unknown source port')
        packets[meta.publish_id]=meta
    observed=0
    for sample in [*original['samples'],original['final']]:
        state=sample['input_readout']
        if not state['completed']:continue
        publication=state['publication'];meta=packets[publication];total,fnv,size=numerics[publication]
        require((state['sum_u16'],state['fnv1a64'],state['last_bytes'],state['rows'])==(total,fnv,size,136),
            'Actual original C consumer summary differs from supplied pixels')
        require((state['epoch'],state['frame'],state['time_ns'])==(meta.epoch,meta.frame_id,meta.virtual_time_ns)
            and state['bytes']==state['completed']*549440,'Consumed source identity/byte count differs')
        observed+=1
    final=original['final'];readout=final['input_readout'];waits=original['ready_observer']['waits']
    require(len(waits)==2 and original['ready_observer'].get('detach')=='OK','Original stop observation incomplete')
    for index,wait in enumerate(waits):
        returned=wait['return'];raw=wait['kernel_result']
        require(wait['thread']==returned['thread']==raw['thread'] and returned['registers']['sp']==wait['registers']['sp']
            and raw['registers']['sp']==wait['registers']['sp']-16,'Original wait return frame differs')
        require(raw['registers']['r0']==(0 if index==0 else 0xffce0000) and returned['registers']['r0']==(1 if index==0 else 0),
            'Original bounded failure changed')
    require(readout_routes and min(r['time_ns'] for r in readout_routes)>waits[1]['return']['virtual_time_ns'],
        'Inline source was admitted before the original failed wait returned')
    require(readout['accepted']==readout['completed']==len(readout_routes) and readout['cancelled']==readout['rejected']==0,
        'Original inline input completion/rejection accounting differs')
    require(final['firmware_status_codes']==[63] and final['other_pipeline_counters']['preview-batches']==0,
        'Original failure/preview boundary differs')
    require(all(s['legacy_RAW_accepted']==0 for s in original['samples']),'Inline model increased legacy RAW acquisitions')
    for _,(name,bytes_,sha) in PROFILES['z62']['members'].items():
        path=Path(original['session'])/'inputs'/name
        require(path.stat().st_size==bytes_ and digest(path)==sha,'Original firmware member changed')
    sources={str(Path(__file__)):digest(Path(__file__)),**native['source_sha256'],**original['source_sha256'],
        **original['ready_observer']['source_sha256'],**route['source_sha256']}
    wrappers=json.loads((original_path.parent/'finite-stream.json').read_text(encoding='utf-8'))
    sources.update(wrappers['source_sha256'])
    binding_path=hardware.device.ROOT/'analysis/z62-input-readout-r102/build-binding/result.json'
    binding=json.loads(binding_path.read_text(encoding='utf-8'));sources.update(binding['source_sha256'])
    regressions={}
    for name in ('legacy-CW-1','legacy-retained-finite-1'):
        path=native_path.parent.parent/name/'result.json';data=json.loads(path.read_text(encoding='utf-8'))
        require(data['completed'] and all(code==0 for code in data['process_exit_codes']),'Legacy native regression incomplete')
        regressions[name]=digest(path);sources.update(data['source_sha256'])
    fallback={}
    for name,sha in sources.items():
        path=Path(name)
        if not path.is_file() and path.name=='command.json':path=original_path.parent/'closed-command.json';fallback[name]=str(path)
        require(path.is_file() and digest(path)==sha,'Readout evidence source missing or changed: '+name)
    result={'schema':1,'completed_evidence_check':True,'binary_sha256':build['binary_sha256'],
        'native_result_sha256':digest(native_path),'original_result_sha256':digest(original_path),
        'source_route_receipt_sha256':digest(route_path),'build_binding_sha256':digest(binding_path),
        'accepted_packets_byte_exact_reconstructed':len(packets),'original_CW_publications':len(packets)-len(readout_routes),
        'original_inline_readouts':readout['completed'],'original_inline_bytes_consumed':readout['bytes'],
        'observed_original_consumer_summaries_independently_recomputed':observed,
        'distinct_inline_payloads_recomputed':len(cache),'native_inline_bytes_independently_recomputed':549440,
        'original_kernel_stop_wait_results':[w['kernel_result']['registers']['r0'] for w in waits],
        'first_inline_source_time_ns':min(r['time_ns'] for r in readout_routes),
        'failed_wait_return_time_ns':waits[1]['return']['virtual_time_ns'],
        'original_window_ns':final['virtual_time_ns'],'original_final_status_codes':[63],'preview_batches':0,
        'legacy_native_regressions':regressions,'guest_RAW_DMA_from_inline_readout':False,
        'legacy_RAW_accepted_always_zero':True,'physical_sensor_equivalence':False,
        'all_original_intermediate_outputs_separately_retained':False,'original_stop_error_fixed':False,
        'complete_camera_or_AF_or_flash_safety_verified':False,'camera_accessed':False,
        'source_sha256':sources,'saved_identical_command_fallbacks':fallback}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_sha256','saved_identical_command_fallbacks')}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--native',type=Path,required=True)
    parser.add_argument('--original',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();verify(args.native,args.original,args.output)
