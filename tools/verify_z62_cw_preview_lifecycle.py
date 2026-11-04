"""Classify the first r104 lifecycle attempt without converting it into a PASS."""
import argparse
import json
from pathlib import Path
from PIL import Image
import probe_z62_capturework_preview as native
from verify_z62_capturework_preview_evidence import lcd_color
from z62_main_stream import reconstruct
from record_z62_action_evidence import workspace,digest,require


def verify(result_path,output):
    result_path,output=map(workspace,(result_path,output));require(not output.exists(),'Use new lifecycle evidence output')
    record=json.loads(result_path.read_text(encoding='utf-8'))
    receipt=json.loads((result_path.parent/'preview-lifecycle.json').read_text(encoding='utf-8'))
    require(receipt['result_sha256']==digest(result_path),'Lifecycle receipt belongs to another run')
    require(not record['completed_observation'] and record['process_exit_code']==1 and
        record['failure']['type']=='TimeoutError' and not record.get('cleanup_failure'),
        'Expected terminated incomplete first lifecycle attempt differs')
    require(len(receipt['events'])==4 and len(receipt['LCD_captures'])==5,'Original first attempt evidence incomplete')
    samples=record['samples'];publications={r['publication']:r for r in record['publications']};colors={};verified=[]
    for label in ('color-blue','color-orange'):
        capture=next(r for r in receipt['LCD_captures'] if r['label']==label)
        path=result_path.parent/capture['path'];require(digest(path)==capture['sha256'],'Captured LCD image changed')
        sample=max((r for r in samples if r['virtual_time_ns']<=capture['virtual_time_ns']),key=lambda r:r['virtual_time_ns'])
        candidates=[]
        for frame in sample['CW_preview_source']['frames']:
            row=publications[frame['publication']]
            packet=reconstruct(result_path.parent/'main-source',row)
            expected=lcd_color(native.linear(packet,(2020,1342,1514,1342,1514,1006),2272))
            candidates.append((frame['publication'],expected))
        image=Image.open(path).convert('RGB');points=[]
        for y in (200,300,400,500):
            for x in (200,400,600,800):
                rgb=image.getpixel((x,y));require(rgb in {c for _,c in candidates},'Color challenge does not match an actual source')
                points.append({'xy':[x,y],'rgb':rgb})
        colors[label]=tuple(points[0]['rgb']);verified.append({'label':label,'time_ns':capture['virtual_time_ns'],
            'LCD_sha256':digest(path),'RGB':colors[label],'points':len(points),'matching_source_publications':[p for p,c in candidates if c==colors[label]]})
    require(colors['color-blue']!=colors['color-orange'],'Two input color challenges produced the same LCD output')
    transitions=[]
    for i,row in enumerate(samples):
        if not i or row['application']['index']!=samples[i-1]['application']['index']:
            transitions.append({'virtual_time_ns':row['virtual_time_ns'],'index':row['application']['index']})
    first_half=next(e for e in receipt['events'] if e['action']=='half-return-1')
    require(first_half['application_before']['index']==3,'Fixed first half press was not before actual menu entry')
    sources={str(Path(__file__)):digest(Path(__file__)),str(Path(native.__file__)):digest(Path(native.__file__)),
        **record['source_sha256'],**receipt['source_sha256']}
    for name in ('finite-stream.json','input-readout-stream.json','readout-statistics-stream.json',
        'no-debugger-statistics.json','capturework-preview-stream.json'):
        data=json.loads((result_path.parent/name).read_text(encoding='utf-8'))
        require(data['result_sha256']==digest(result_path),'Lifecycle wrapper identity differs');sources.update(data['source_sha256'])
    for name,sha in sources.items():require(Path(name).is_file() and digest(Path(name))==sha,'Lifecycle source changed: '+name)
    result={'schema':1,'completed_evidence_check':True,'original_result_sha256':digest(result_path),
        'binary_sha256':record['binary_sha256'],'LCD_color_challenges':verified,'two_input_colors_reached_LCD':True,
        'application_index_transitions':transitions,'fixed_first_half_press_preceded_menu_entry':True,
        'last_good_sample_ns':samples[-1]['virtual_time_ns'],'last_good_preview_batches':samples[-1]['other_pipeline_counters']['preview-batches'],
        'host_communication_timeout_preserved':record['failure'],'process_exit_code':1,
        'full_requested_observation_completed':False,'two_menu_cycles_passed':False,'preview_resume_verified':False,
        'timeout_root_cause_verified':False,'camera_accessed':False,'source_sha256':sources}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();verify(args.result,args.output)
