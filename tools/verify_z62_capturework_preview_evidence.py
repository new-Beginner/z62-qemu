"""Verify source-backed CW cohorts, private domains and actual original LCD pixels."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image
import probe_z62_capturework_preview as native
import run_z62_capturework_preview as hardware
from z62_main_stream import reconstruct
from z62_main_frame import parse_packet
from verify_z62_readout_statistics_evidence import means
from prepare_reference_firmware import PROFILES
from record_z62_action_evidence import workspace,digest,require


def lcd_color(linear):
    y,u,v=native.color_pixels(linear);c=max(0,y-16);d=u-128;e=v-128
    return tuple(max(0,min(255,n)) for n in
        ((298*c+409*e+128)>>8,(298*c-100*d-208*e+128)>>8,(298*c+516*d+128)>>8))


def verify(native_path,bank_path,original_path,output):
    native_path,bank_path,original_path,output=map(workspace,(native_path,bank_path,original_path,output))
    require(not output.exists(),'Use new preview evidence result')
    n=json.loads(native_path.read_text(encoding='utf-8'));b=json.loads(bank_path.read_text(encoding='utf-8'))
    w=json.loads(original_path.read_text(encoding='utf-8'));build=hardware.verify_build()
    require(n['completed'] and b['completed'] and n['binary_sha256']==b['binary_sha256']==w['binary_sha256']==build['binary_sha256']
        and all(code==0 for code in n['process_exit_codes']+b['process_exit_codes']),'Native preview/domain checks incomplete')
    dims=(2020,1342,1514,1342,1514,1006);stride=2272;native_hash_bytes=0
    for key in ('first_source','second_source','third_source'):
        view=n[key];require(len({r['publication'] for r in view['frames']})==4,'Native source duplicated a frame')
        for frame in view['frames']:
            packet=(native_path.parent/f'source-{frame["publication"]}.z62m').read_bytes()
            data=native.linear(packet,dims,stride);require(hashlib.sha256(data).hexdigest()==frame['linear_sha256'],
                'Native full linear cohort differs from independent RAW transfer')
            native_hash_bytes+=len(data)
    require(w['completed_observation'] and w['process_exit_code']==0 and not w.get('failure') and not w.get('cleanup_failure')
        and w['source_bytes_unchanged'] and w['original_card_unchanged'],'Original preview run incomplete')
    require(w['ready_observer']['attached'] is False,'Original run unexpectedly attached GDB')
    routes=json.loads((original_path.parent/'input-readout-stream.json').read_text(encoding='utf-8'))
    require(routes['result_sha256']==digest(original_path),'Original source-route binding differs')
    ports={r['publication']:r for r in routes['actual_accepted_source_routes']}
    rows={r['publication']:r for r in w['publications']};packets={};by_payload={}
    require(len(rows)==len(ports)==w['accepted_publications'],'Accepted source packets/routes incomplete')
    for publication,row in rows.items():
        packet=reconstruct(original_path.parent/'main-source',row);meta,_=parse_packet(packet);route=ports[publication]
        require((meta.epoch,meta.frame_id,meta.virtual_time_ns)==(route['epoch'],route['frame'],route['time_ns']),
            'Source packet identity differs from actual accepted port')
        packets[publication]=packet
    cohorts={};sample_count=0
    for sample in [*w['samples'],w['final']]:
        require(sample['legacy_RAW_accepted']==0 and sample['other_pipeline_counters']['raw-stream-frames']==0
            and sample['metadata_clock_completions']==0,'Preview bridge changed legacy counters or used metadata clock')
        view=sample['CW_preview_source']
        if not view['owns_source'] or not view['source_valid']:continue
        require(len({r['publication'] for r in view['frames']})==4,'Original source was not four distinct frames')
        for frame in view['frames']:
            publication=frame['publication'];packet=packets[publication];meta,_=parse_packet(packet)
            require(ports[publication]['port']=='capturework-main-file' and
                (frame['epoch'],frame['frame'],frame['time_ns'])==(meta.epoch,meta.frame_id,meta.virtual_time_ns),
                'Original cohort includes an unrelated source')
            payload_key=rows[publication]['payload']['sha256']
            if payload_key not in by_payload:
                linear=native.linear(packet,dims,stride)
                by_payload[payload_key]=(hashlib.sha256(linear).hexdigest(),lcd_color(linear))
            require(by_payload[payload_key][0]==frame['linear_sha256'],'Original private linear bytes differ from source/transfer')
        cohorts[(view['generation'],view['cohort'])]=view;sample_count+=1
    final=w['final'];view=final['CW_preview_source']
    require(final['firmware_status_codes']==[] and final['other_pipeline_counters']['preview-batches']>0,
        'Original preview did not complete with a clean bounded status')
    require(view['owns_source'] and view['source_valid'] and view['source_seq']==view['consumed_seq'],
        'Final source is not a consumed immutable cohort')
    candidates=[]
    for frame in view['frames']:
        if frame['time_ns']>=final['virtual_time_ns']-1_000_000_000:
            rgb=by_payload[rows[frame['publication']]['payload']['sha256']][1]
            candidates.append((frame['publication'],rgb))
    require(candidates,'No recent consumed source for LCD comparison')
    image_path=original_path.parent/'final-lcd.png';image=Image.open(image_path).convert('RGB')
    require(image.size==(1024,682),'Unknown original LCD geometry')
    points=[]
    for y in (200,300,400,500):
        for x in (200,400,600,800):
            color=image.getpixel((x,y));require(color in {rgb for _,rgb in candidates},'Original LCD pixel does not match a recent actual source')
            points.append({'xy':[x,y],'rgb':color})
    scalar=json.loads((original_path.parent/'no-debugger-statistics.json').read_text(encoding='utf-8'))
    require(scalar['result_sha256']==digest(original_path) and len(scalar['scalar_DMA_snapshots'])==2,'Original finite scalar snapshots missing')
    for frame in scalar['scalar_DMA_snapshots']:
        path=original_path.parent/frame['scalar_path'];require(digest(path)==frame['scalar_sha256'] and
            path.read_bytes()==means(packets[frame['source']['batch_publication']]),'Original finite statistics regressed')
    for _,(name,size,sha) in PROFILES['z62']['members'].items():
        path=Path(w['session'])/'inputs'/name;require(path.stat().st_size==size and digest(path)==sha,'Original firmware member changed')
    sources={str(Path(__file__)):digest(Path(__file__)),str(Path(native.__file__)):digest(Path(native.__file__)),
        **n['source_sha256'],**b['source_sha256'],**w['source_sha256']}
    for name in ('finite-stream.json','input-readout-stream.json','readout-statistics-stream.json',
            'no-debugger-statistics.json','capturework-preview-stream.json'):
        receipt=json.loads((original_path.parent/name).read_text(encoding='utf-8'))
        require(receipt['result_sha256']==digest(original_path),'Original wrapper binding differs');sources.update(receipt['source_sha256'])
    bind_path=hardware.device.ROOT/'analysis/z62-capturework-preview-r104/build-binding/result.json'
    sources.update(json.loads(bind_path.read_text(encoding='utf-8'))['source_sha256'])
    regressions={}
    for path in (native_path.parent.parent/'legacy-preview-1.json',native_path.parent.parent/'legacy-readout-statistics-1/result.json'):
        data=json.loads(path.read_text(encoding='utf-8'));require(data['completed'] and data['binary_sha256']==build['binary_sha256'],
            'Legacy preview/statistics regression failed');regressions[path.name]=digest(path)
        sources.update(data.get('source_sha256',{}))
    for name,sha in sources.items():require(Path(name).is_file() and digest(Path(name))==sha,'Bound preview source changed: '+name)
    result={'schema':1,'completed_evidence_check':True,'binary_sha256':build['binary_sha256'],
        'native_result_sha256':digest(native_path),'bank_result_sha256':digest(bank_path),'original_result_sha256':digest(original_path),
        'build_binding_sha256':digest(bind_path),'native_full_linear_bytes_independently_hashed':native_hash_bytes,
        'native_NV12_bytes_independently_verified':n['NV12_bytes_independently_verified']+b['NV12_bytes_independently_verified'],
        'encoded_guest_RAW_bytes_preservation_checked':b['encoded_guest_RAW_bytes_independently_verified'],
        'original_accepted_packets_reconstructed':len(packets),'original_cohort_samples_verified':sample_count,
        'unique_original_cohorts_observed':len(cohorts),'distinct_original_payloads_recomputed':len(by_payload),
        'original_CW_DMA_frames':final['capturework']['completed'],'original_source_cohorts':final['CW_cohort']['cohorts'],
        'original_preview_batches':final['other_pipeline_counters']['preview-batches'],'original_virtual_ns':final['virtual_time_ns'],
        'original_status_codes':final['firmware_status_codes'],'LCD_sha256':digest(image_path),'LCD_points':points,
        'LCD_matching_recent_publications':[p for p,rgb in candidates if rgb==points[0]['rgb']],
        'unique_displayed_frame_identified':False,'original_finite_scalar_bytes_recomputed':1536,
        'legacy_RAW_counters_unchanged':True,'metadata_event6_injected':False,'legacy_native_regressions':regressions,
        'physical_ISP_or_AF_equivalence':False,'preview_resume_verified':False,'complete_camera_or_flash_safety_verified':False,
        'camera_accessed':False,'source_sha256':sources}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_sha256','LCD_points')}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--native',type=Path,required=True)
    parser.add_argument('--banks',type=Path,required=True);parser.add_argument('--original',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    verify(args.native,args.banks,args.original,args.output)
