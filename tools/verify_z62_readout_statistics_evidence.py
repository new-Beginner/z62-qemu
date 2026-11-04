"""Audit native and original C input statistics, data provenance and real waits."""
import argparse
import json
from pathlib import Path
import struct
import numpy as np
import run_z62_readout_statistics as hardware
from z62_main_stream import reconstruct
from z62_main_frame import parse_packet
from prepare_reference_firmware import PROFILES
from record_z62_action_evidence import workspace,digest,require


def means(packet):
    meta,payload=parse_packet(packet)
    require((meta.width,meta.height)==(2020,136),'Unknown statistics source geometry')
    image=np.frombuffer(payload,dtype='<u2').reshape(meta.height,meta.stride//2)[:,:meta.width]>>4
    integral=np.pad(image.astype(np.uint64).cumsum(0).cumsum(1),((1,0),(1,0)))
    out=bytearray(768)
    for y in range(12):
        for x in range(30):
            y0,y1=y*136//12,(y+1)*136//12;x0,x1=x*2020//30,(x+1)*2020//30
            total=int(integral[y1,x1])+int(integral[y0,x0])-int(integral[y0,x1])-int(integral[y1,x0])
            count=(y1-y0)*(x1-x0);struct.pack_into('<H',out,y*64+x*2,(total+count//2)//count)
    return bytes(out)


def closed_run(path,binary_sha):
    record=json.loads(path.read_text(encoding='utf-8'))
    require(record['binary_sha256']==binary_sha and record['completed_observation'] and record['process_exit_code']==0
        and not record.get('failure') and not record.get('cleanup_failure') and record['source_bytes_unchanged']
        and record['original_card_unchanged'],'Original statistics window incomplete or identity changed')
    for _,(name,size,sha) in PROFILES['z62']['members'].items():
        member=Path(record['session'])/'inputs'/name
        require(member.stat().st_size==size and digest(member)==sha,'Original firmware member changed')
    require(all(s['legacy_RAW_accepted']==0 for s in record['samples']),'Statistics data incremented legacy RAW acquisitions')
    return record


def verify(native_path,traced_path,plain_path,output):
    native_path,traced_path,plain_path,output=map(workspace,(native_path,traced_path,plain_path,output))
    require(not output.exists(),'Use new statistics evidence result')
    native=json.loads(native_path.read_text(encoding='utf-8'));build=hardware.verify_build()
    require(native['completed'] and native['binary_sha256']==build['binary_sha256'] and
        all(code==0 for code in native['process_exit_codes']),'Native data/ownership checks incomplete')
    native_bytes=0
    for batch in native['batches']:
        source=native_path.parent/batch['source'];data=native_path.parent/batch['outputs']
        require(data.read_bytes()==means(source.read_bytes())*61,'Independent native integral-grid result differs')
        native_bytes+=data.stat().st_size
    require(native_bytes==93696,'Native 122 actual DMA samples not retained')
    traced=closed_run(traced_path,build['binary_sha256']);plain=closed_run(plain_path,build['binary_sha256'])
    obs=traced['ready_observer'];require(obs.get('detach')=='OK' and len(obs['waits'])==2,'Original direct waits incomplete')
    waits=[]
    for w in obs['waits']:
        ret=w['return'];raw=w['kernel_result']
        require(w['thread']==ret['thread']==raw['thread'] and ret['registers']['sp']==w['registers']['sp']
            and raw['registers']['sp']==w['registers']['sp']-16,'Original wait CPU/SP pairing differs')
        require(raw['registers']['r0']==0 and ret['registers']['r0']==1 and ret['output_bits']&0x800,
            'The original stop wait did not return actual kernel success')
        waits.append({'call_ns':w['virtual_time_ns'],'duration_ns':ret['virtual_time_ns']-w['virtual_time_ns'],
            'kernel_result':0,'boolean_result':1,'pattern_at_call':w['event']['pattern']})
    require(obs['publications'] and all(int(p['after_original_store']['pattern'],16)&0x800 for p in obs['publications']),
        'Actual original 0x800 pattern store not witnessed')
    require(plain['ready_observer']['attached'] is False,'The plain window attached GDB')
    sources={str(Path(__file__)):digest(Path(__file__)),**native['source_sha256']}
    run_summaries=[];plain_packets={};all_receipts=[]
    for path,record in ((traced_path,traced),(plain_path,plain)):
        sources.update(record['source_sha256']);sources.update(record['ready_observer'].get('source_sha256',{}))
        for name in ('finite-stream.json','input-readout-stream.json','readout-statistics-stream.json','no-debugger-statistics.json'):
            receipt_path=path.parent/name
            if not receipt_path.is_file():continue
            receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
            require(receipt['result_sha256']==digest(path),'Statistics wrapper bound to another run')
            sources.update(receipt['source_sha256']);all_receipts.append((receipt_path,receipt))
        route=json.loads((path.parent/'input-readout-stream.json').read_text(encoding='utf-8'))
        ports={r['publication']:r for r in route['actual_accepted_source_routes']}
        require(len(ports)==record['accepted_publications']==len(record['publications']),'Accepted source route audit incomplete')
        packets={}
        for row in record['publications']:
            packet=reconstruct(path.parent/'main-source',row);meta,_=parse_packet(packet);port=ports[meta.publish_id]
            require((meta.epoch,meta.frame_id,meta.virtual_time_ns)==(port['epoch'],port['frame'],port['time_ns']),
                'Actual source port identity differs')
            if port['port']=='input-readout-file':
                require((meta.width,meta.height)==(2020,136),'Statistics readout used unknown geometry')
            else:require(port['port']=='capturework-main-file','Unknown source port')
            packets[meta.publish_id]=packet
        final=record['final'];last=record['samples'][-1]
        require(final['readout_statistics']['batches']==2 and final['readout_statistics']['finite_frames']==122
            and last['finite_statistics']['finite-batches']==2,'Original finite data batches incomplete')
        require(all(s['retained_finite_source']['batches_prepared']==0 for s in record['samples']),
            'Original statistics bypassed the new source with retained CW')
        require(0x3f not in final['firmware_status_codes'],'Original 0x3f stop error remains')
        run_summaries.append({'result_sha256':digest(path),'virtual_time_ns':final['virtual_time_ns'],
            'accepted_packets_reconstructed':len(packets),'CW_DMA_completed':final['capturework']['completed'],
            'inline_readouts':final['input_readout']['completed'],'statistics_batches':2,'finite_DMA_samples':122,
            'final_status_codes':final['firmware_status_codes'],'grid_groups':final['other_pipeline_counters']['grid-groups'],
            'preview_batches':final['other_pipeline_counters']['preview-batches']})
        if path==plain_path:plain_packets=packets
    plain_receipt=json.loads((plain_path.parent/'no-debugger-statistics.json').read_text(encoding='utf-8'))
    require(len(plain_receipt['scalar_DMA_snapshots'])==2 and not plain_receipt['GDB_attached'],
        'Original coherent scalar snapshots incomplete')
    actual_bytes=0;batch_sources=[]
    for frame in plain_receipt['scalar_DMA_snapshots']:
        state=frame['source'];packet=plain_packets[state['batch_publication']];meta,_=parse_packet(packet)
        require((meta.epoch,meta.frame_id,meta.virtual_time_ns)==
            (state['batch_epoch'],state['batch_frame'],state['batch_time_ns']),'Original batch source identity differs')
        path=plain_path.parent/frame['scalar_path'];require(digest(path)==frame['scalar_sha256'],
            'Original scalar bytes changed')
        require(frame['VM_stopped_for_coherent_read'] and path.read_bytes()==means(packet),
            'Independent original scalar DMA means differ')
        actual_bytes+=path.stat().st_size
        batch_sources.append({'publication':meta.publish_id,'frame':meta.frame_id,'time_ns':meta.virtual_time_ns})
    binding_path=hardware.device.ROOT/'analysis/z62-readout-statistics-r103/build-binding/result.json'
    binding=json.loads(binding_path.read_text(encoding='utf-8'));sources.update(binding['source_sha256'])
    regressions={}
    for name in ('legacy-readout-1','legacy-retained-finite-1'):
        path=native_path.parent.parent/name/'result.json';legacy=json.loads(path.read_text(encoding='utf-8'))
        require(legacy['completed'] and all(code==0 for code in legacy['process_exit_codes']),
            'Old readout/retained-finite native regression failed')
        regressions[name]=digest(path);sources.update(legacy['source_sha256'])
    fallback={}
    for name,sha in sources.items():
        path=Path(name)
        if not path.is_file() and path.name=='command.json':
            candidates=[traced_path.parent/'closed-command.json',plain_path.parent/'closed-command.json']
            path=next((p for p in candidates if digest(p)==sha),path);fallback[name]=str(path)
        require(path.is_file() and digest(path)==sha,'Bound statistics evidence source missing or changed: '+name)
    result={'schema':1,'completed_evidence_check':True,'binary_sha256':build['binary_sha256'],
        'native_result_sha256':digest(native_path),'build_binding_sha256':digest(binding_path),
        'native_actual_DMA_bytes_independently_recomputed':native_bytes,'original_scalar_DMA_bytes_independently_recomputed':actual_bytes,
        'sample_mismatches':0,'actual_original_stop_waits':waits,'actual_original_pattern_stores_verified':len(obs['publications']),
        'traced_window':run_summaries[0],'no_GDB_window':run_summaries[1],'original_batch_sources':batch_sources,
        'first_traced_scalar_capture_missing_preserved':not json.loads((traced_path.parent/'readout-statistics-stream.json').read_text())['scalar_DMA_snapshots'],
        'coherent_scalar_capture_QMP_pauses':plain_receipt['QMP_scalar_capture_pauses'],
        'observation_timing_perturbed':True,'statistics_are_retained_per_batch_not_new_RAW_acquisitions':True,
        'legacy_RAW_accepted_always_zero':True,'legacy_native_regressions':regressions,
        'physical_sensor_or_AF_equivalence':False,'complete_camera_or_flash_safety_verified':False,'camera_accessed':False,
        'source_sha256':sources,'saved_identical_command_fallbacks':fallback}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_sha256','saved_identical_command_fallbacks')}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--native',type=Path,required=True)
    parser.add_argument('--traced',type=Path,required=True);parser.add_argument('--plain',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    verify(args.native,args.traced,args.plain,args.output)
