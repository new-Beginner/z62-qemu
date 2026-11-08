"""Independently classify r105 cycles, actual fresh sources, LCD pixels and faults."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image
import probe_z62_capturework_preview as numerical
from verify_z62_capturework_preview_evidence import lcd_color
from z62_main_stream import reconstruct
from z62_main_frame import parse_packet
from record_z62_action_evidence import workspace,digest,require


def verify(case,output):
    case,output=map(workspace,(case,output));require(not output.exists(),'Use a new recovery verification output')
    result_path=case/'result.json';receipt_path=case/'recovery-observer.json'
    result=json.loads(result_path.read_text(encoding='utf-8'));receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
    require(receipt['result_sha256']==digest(result_path),'Observer belongs to another result')
    sources={str(Path(__file__).resolve()):digest(Path(__file__)),**result['source_sha256'],**receipt['source_sha256']}
    for name in ('finite-stream.json','input-readout-stream.json','readout-statistics-stream.json',
            'no-debugger-statistics.json','capturework-preview-stream.json'):
        wrapper=json.loads((case/name).read_text(encoding='utf-8'))
        require(wrapper['result_sha256']==digest(result_path),'Parent source binding differs: '+name)
        sources.update(wrapper['source_sha256'])
    canonical={}
    for name,sha in sources.items():
        physical=Path(name).resolve();require(physical.is_file() and digest(physical)==sha,'Bound observer changed: '+name)
        key=str(physical);require(key not in canonical or canonical[key]==sha,'Canonical source identity conflicts')
        canonical[key]=sha
    ports=json.loads((case/'input-readout-stream.json').read_text(encoding='utf-8'))['actual_accepted_source_routes']
    rows={r['publication']:r for r in result['publications']};route={r['publication']:r for r in ports}
    require(len(rows)==len(route)==result['accepted_publications'],'Accepted input audit incomplete')
    for publication,row in rows.items():
        packet=reconstruct(case/'main-source',row);meta,_=parse_packet(packet);target=route[publication]
        require((meta.epoch,meta.frame_id,meta.virtual_time_ns)==(target['epoch'],target['frame'],target['time_ns']),
            'Actual input route identity mismatch')
    event_sources=[];by_payload={}
    for event in receipt['events']:
        for frame in event['source'].get('frames',[]):
            row=rows[frame['publication']];target=route[frame['publication']]
            packet=reconstruct(case/'main-source',row);meta,_=parse_packet(packet)
            require(target['port']=='capturework-main-file' and
                (frame['epoch'],frame['frame'],frame['time_ns'])==(meta.epoch,meta.frame_id,meta.virtual_time_ns),
                'Cycle source was not the actual completed CW input')
            key=row['payload']['sha256']
            if key not in by_payload:
                linear=numerical.linear(packet,(2020,1342,1514,1342,1514,1006),2272)
                by_payload[key]=(hashlib.sha256(linear).hexdigest(),lcd_color(linear))
            require(by_payload[key][0]==frame['linear_sha256'],'Frozen private linear frame differs')
            event_sources.append(frame['publication'])
    sequences=[];pixel_checks=[]
    for cycle in range(1,receipt['completed_cycles']+1):
        events=[e for e in receipt['events'] if e['cycle']==cycle]
        require([e['action'] for e in events]==['menu','half','recovered'],'Completed cycle actions incomplete')
        menu,half,recovered=events
        require([e['application_before']['index'] for e in events]==[3,1,3],
            'Controls did not follow actual application state')
        require(all(not e['application_before']['queued_keys'] and not e['application_before']['held'] for e in events),
            'Next action was submitted while prior input remained pending')
        require(menu['virtual_time_ns']<half['virtual_time_ns']<recovered['virtual_time_ns'] and
            recovered['preview_batches']>half['preview_batches'],'Recovery did not complete new preview work')
        old=max((f['publication'] for f in half['source'].get('frames',[])),default=0)
        fresh=recovered['source']['frames']
        require(len(fresh)==4 and len({f['publication'] for f in fresh})==4 and
            all(f['publication']>old and f['time_ns']>half['virtual_time_ns'] for f in fresh),
            'Recovered source is not four fresh post-return frames')
        capture=next(c for c in receipt['LCD_captures'] if c['label']=='recovered-'+str(cycle))
        image_path=case/capture['path'];require(digest(image_path)==capture['sha256'],'Recovery LCD changed')
        image=Image.open(image_path).convert('RGB');require(image.size==(1024,682),'Unknown LCD geometry')
        candidates=[]
        views=[capture['source'],*(s['CW_preview_source'] for s in result['samples'] if
            capture['virtual_time_ns']-500_000_000<=s['virtual_time_ns']<=capture['virtual_time_ns'])]
        for view in views:
            for frame in view.get('frames',[]):
                if frame['publication']<=old or frame['time_ns']<=half['virtual_time_ns']:continue
                row=rows[frame['publication']];key=row['payload']['sha256']
                if key not in by_payload:
                    packet=reconstruct(case/'main-source',row)
                    linear=numerical.linear(packet,(2020,1342,1514,1342,1514,1006),2272)
                    by_payload[key]=(hashlib.sha256(linear).hexdigest(),lcd_color(linear))
                candidates.append((frame['publication'],by_payload[key][1]))
        points=[]
        for y in (200,300,400,500):
            for x in (200,400,600,800):
                color=image.getpixel((x,y));require(color in {c for _,c in candidates},'Recovered LCD does not match a fresh input')
                points.append({'xy':[x,y],'rgb':color})
        pixel_checks.append({'cycle':cycle,'LCD_sha256':capture['sha256'],'points':points,
            'matching_new_publications':sorted({p for p,c in candidates if c==points[0]['rgb']})})
        sequences.append({'cycle':cycle,'menu_ns':menu['virtual_time_ns'],'half_ns':half['virtual_time_ns'],
            'recovered_ns':recovered['virtual_time_ns'],'new_publications':[f['publication'] for f in fresh]})
    for sample in result['samples']:
        require(sample['legacy_RAW_accepted']==0 and sample['other_pipeline_counters']['raw-stream-frames']==0
            and sample['metadata_clock_completions']==0,'Legacy counts or metadata clock changed')
    faults=receipt['host_faults'];quality=[]
    for fault in faults:
        require(fault['python_traceback'] and fault['python_thread_stacks'] and not fault['replayed'],
            'Fault lost Python call site or replay boundary')
        capture=fault.get('capture',{})
        quality.append({k:capture.get(k) for k in ('completed_capture','qemu_symbols_resolved','stack_trace_present',
            'library_list_parse_error','host_debugger_attached','detach_reported','owner_alive_after')})
    complete=bool(result['completed_observation'] and result['process_exit_code']==0 and not result.get('failure')
        and not result.get('cleanup_failure') and result['source_bytes_unchanged'] and result['original_card_unchanged'])
    accepted=bool(complete and not faults and receipt['completed_cycles']==2 and len(pixel_checks)==2
        and result['final']['firmware_status_codes']==[])
    out={'schema':1,'completed_evidence_check':True,'original_result_sha256':digest(result_path),
        'observer_sha256':digest(receipt_path),'binary_sha256':result['binary_sha256'],
        'original_accepted_packets_reconstructed':len(rows),'event_frame_sources_verified':len(event_sources),
        'completed_original_observation':complete,'completed_state_driven_cycles':len(sequences),
        'cycle_sequences':sequences,'fresh_LCD_checks':pixel_checks,'host_timeout_count':len(faults),
        'host_capture_quality':quality,'original_failure':result.get('failure'),
        'two_menu_cycles_and_preview_resume_verified':accepted,'unique_displayed_frame_identified':False,
        'complete_camera_or_AF_or_flash_safety_verified':False,'camera_accessed':False,'source_sha256':canonical}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(out,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in out.items() if k not in ('source_sha256','fresh_LCD_checks')}),flush=True)
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();verify(args.case,args.output)
