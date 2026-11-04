"""Offline check of real AND-wait returns and virtual-clock source auditing."""
import argparse
import json
from pathlib import Path
from PIL import Image
import numpy as np
import z62_mmio_filtered_trace as mmio
from z62_main_stream import reconstruct
from record_z62_action_evidence import workspace,digest,require


def verify_trace(record):
    complete=record.get('completed_observation',len(record.get('waits',[]))==3)
    require(complete and record.get('detach')=='OK' and not record.get('cleanup_failure'),
        'RSP observation or detach incomplete')
    outcomes=[]
    for wait in record['waits']:
        returned=wait['return'];raw=wait['kernel_result']
        require(returned['registers']['sp']==wait['registers']['sp'] and
            raw['registers']['sp']==wait['registers']['sp']-16,'Wait return frame mismatch')
        require(wait['registers']['r1']==0x5b00000 and wait['event']['object']=='0xc188808c','Wrong original wait object/mask')
        success=returned['registers']['r0']==1
        require((raw['registers']['r0']==0)==success,'Raw kernel result and original boolean differ')
        if success:require(returned['output_bits']&0x5b00000==0x5b00000,'Successful AND wait omitted requested bits')
        outcomes.append({'success':success,'kernel_result':raw['registers']['r0'],
            'output_bits':returned['output_bits'],'duration_ns':returned['virtual_time_ns']-wait['virtual_time_ns']})
    for hit in record['hits']:
        if hit['label']=='kernel-pattern-store':
            reg=hit['registers']
            require(reg['r0']==int(hit['event']['pattern'],16)|reg['r6'] and
                int(hit['after_original_store']['pattern'],16)==reg['r0'],'Actual original pattern OR/store differs')
        if hit['label']=='kernel-and-test':
            require(hit['missing_after_original_bics']==hit['registers']['r7']&~hit['registers']['r3'],
                'Original BICS observation differs')
    return outcomes


def verify(slow_path,fast_path,output):
    slow_path,fast_path,output=map(workspace,(slow_path,fast_path,output))
    require(not output.exists(),'Use a new source/return verifier result')
    slow=json.loads(slow_path.read_text(encoding='utf-8'));fast=json.loads(fast_path.read_text(encoding='utf-8'))
    old=json.loads((slow_path.parent/'result.json').read_text(encoding='utf-8'))
    require(slow['original_result_sha256']==digest(slow_path.parent/'result.json'),'R96 original result changed')
    require(old['completed_observation'] and old['process_exit_code']==0 and not old.get('failure'),'R96 original window failed')
    slower=verify_trace(slow);faster=verify_trace(fast['ready_observer'])
    require(sum(row['success'] for row in slower)==2 and sum(not row['success'] for row in slower)==1,
        'Unexpected bounded slow-source outcomes')
    require(len(faster)==3 and all(row['success'] for row in faster),'Continuous-source wait test incomplete')
    require(fast['completed_observation'] and fast['process_exit_code']==0 and not fast.get('failure') and
        not fast.get('cleanup_failure') and fast['source_bytes_unchanged'] and fast['original_card_unchanged'],
        'Continuous-source original run failed')
    publications=fast['publications'];previous=None
    for row in publications:
        reconstruct(fast_path.parent/'main-source',row)
        if previous:
            require(row['publication']==previous['publication']+1 and row['frame']>previous['frame'] and
                row['time_ns']>previous['time_ns'],'Stream replayed a frame or time credit')
        require(row['frame']==row['time_ns']*30//1_000_000_000,'Source timeline differs from original virtual time')
        previous=row
    skipped=publications[-1]['frame']-publications[0]['frame']+1-len(publications)
    require(skipped==fast['source_frames_skipped'],'Source skip accounting differs')
    lines=(fast_path.parent/'closed-console.txt').read_text(encoding='utf-8').splitlines(keepends=True)
    require(lines and lines[-1].endswith('\n'),'Post-exit console has a truncated final line')
    rows=[]
    for line in lines:
        row=mmio.parse_line(line)
        if row is not None and row['cpu']==0:rows.append(row)
    require(any(r['address']==0x2006a548 and r['value']==60 for r in rows),'Original finite61 transition not observed')
    finite=fast['samples'][-1]['finite_statistics']
    require(finite['functional-finite-stats'] and finite['finite-frames']==0 and finite['finite-rejected']>0 and
        finite['finite-reason']=='source','Legacy finite source boundary changed')
    require(all(sample['legacy_RAW_accepted']==0 for sample in fast['samples']),'Source auditing incremented legacy RAW')
    image=Image.open(fast_path.parent/'final-lcd.png').convert('RGB')
    sources={str(Path(__file__)):digest(Path(__file__)),**fast['source_sha256']}
    for name,sha in fast['ready_observer']['source_sha256'].items():
        path=Path(name)
        if path.is_file():require(digest(path)==sha,'Ready observer source changed');sources[name]=sha
        else:require(path.name=='command.json' and digest(fast_path.parent/'closed-command.json')==sha,
            'Missing runtime metadata has no identical saved copy')
    result={'schema':1,'completed_evidence_check':True,'slow_observer_sha256':digest(slow_path),
        'fast_original_result_sha256':digest(fast_path),'slow_source_waits':slower,'continuous_source_waits':faster,
        'original_OR_store_publications_verified':sum(h['label']=='kernel-pattern-store' for h in slow['hits']),
        'accepted_MAIN_packets_reconstructed':len(publications),'source_frames_skipped':skipped,
        'mailbox_files':len(list((fast_path.parent/'main-source').glob('mailbox-*.z62m'))),
        'unique_payloads':len(list((fast_path.parent/'main-source').glob('*.linear16'))),
        'all_accepted_inputs_byte_exact_reconstructable':True,'retained_source_fake_RAW_acquisitions':False,
        'original_finite_count_minus_one':60,'finite_model_enabled':True,'finite_samples':0,
        'finite_reason':'source','LCD_all_black':not np.any(np.asarray(image)),
        'preview_batches':fast['final']['other_pipeline_counters']['preview-batches'],
        'functional_acceptance_eligible':False,'camera_accessed':False,'source_sha256':sources}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--slow',type=Path,required=True)
    parser.add_argument('--fast',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    verify(args.slow,args.fast,args.output)
