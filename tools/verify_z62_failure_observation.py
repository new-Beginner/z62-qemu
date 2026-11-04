"""Verify source-bound original r99/r100 entry/return and error publications."""
import argparse
import json
from pathlib import Path
from record_z62_action_evidence import workspace,digest,require
import run_z62_capturework_finite as hardware


def verify(result_path,output):
    result_path,output=map(workspace,(result_path,output))
    require(not output.exists(),'New failure evidence result required')
    record=json.loads(result_path.read_text(encoding='utf-8'));obs=record['ready_observer']
    build=hardware.verify_build()
    require(record['binary_sha256']==build['binary_sha256'] and record['completed_observation'] and
        not record.get('failure') and not record.get('cleanup_failure') and record['process_exit_code']==0,
        'Original error observation did not close successfully')
    require(record['source_bytes_unchanged'] and record['original_card_unchanged'] and obs.get('detach')=='OK',
        'Original source/card identity or RSP detach failed')
    require(not obs['guest_memory_written'] and not obs['guest_registers_written'] and not obs['inferior_calls'] and
        not obs['completion_or_ready_injected'],'Observer mutated original state')
    master=Path(record['session'])/'inputs/master.bin'
    require(digest(master)==record['master_sha256'],'Original master changed')
    image=master.read_bytes();base=0x10020000
    for anchor in obs['live_anchors']:
        pc=int(anchor['pc'],16);require(bytes.fromhex(anchor['bytes'])==image[pc-base:pc-base+4],'Original anchor changed')
    calls={call['sequence']:call for call in obs['calls']};matched=[];appends=[]
    for row in obs['returns']:
        call=calls[row['call_sequence']];a=call['registers'];b=row['registers']
        require(row['thread']==call['thread'] and b['sp']==a['sp'] and row['pc']==call['return_anchor']['pc'],
            'Return not paired to the original CPU/SP/PC frame')
        require(row['virtual_time_ns']>=call['virtual_time_ns'],'Return precedes call')
        matched.append({'label':call['label'],'call_pc':call['pc'],'return_pc':row['pc'],
            'arguments':[a['r0'],a['r1'],a['r2'],a['r3']],'result_r0':b['r0'],
            'call_time_ns':call['virtual_time_ns'],'duration_ns':row['virtual_time_ns']-call['virtual_time_ns'],
            'output_hex':row.get('output_hex')})
        if call['label']=='status-append-call':
            require(a['r0'] in row['status_codes'],'Original status append not present after return')
            appends.append({'code':a['r0'],'before':call['status_codes'],'after':row['status_codes'],
                'virtual_time_ns':call['virtual_time_ns']})
    require(appends and any(row['code']==0x3f for row in appends),'No actual 0x3f publication observed')
    sources={str(Path(__file__)):digest(Path(__file__)),**record['source_sha256'],**obs['source_sha256']}
    for name in ('failure-observation.json','finite-stream.json','stop-observation.json'):
        path=result_path.parent/name
        if path.is_file():
            wrapper=json.loads(path.read_text(encoding='utf-8'))
            require(wrapper['result_sha256']==digest(result_path),'Wrapper refers to another original run')
            sources.update(wrapper['source_sha256'])
    fallbacks={}
    for name,sha in sources.items():
        path=Path(name)
        if not path.is_file() and path.name=='command.json':
            path=result_path.parent/'closed-command.json';fallbacks[name]=str(path)
        require(path.is_file() and digest(path)==sha,'Observer bound source missing or changed: '+name)
    first=next((s for s in record['samples'] if 0x3f in (s.get('firmware_status_codes') or [])),None)
    require(first is not None,'Status list 0x3f missing from independent HMP samples')
    result={'schema':1,'completed_evidence_check':True,'original_result_sha256':digest(result_path),
        'binary_sha256':build['binary_sha256'],'matched_original_calls':matched,'status_appends':appends,
        'first_sample_with_0x3f_ns':first['virtual_time_ns'],'original_window_ns':record['final']['virtual_time_ns'],
        'accepted_MAIN_publications':record['accepted_publications'],
        'finite_samples':record['samples'][-1]['finite_statistics']['finite-frames'],
        'finite_batches':record['samples'][-1]['finite_statistics']['finite-batches'],
        'incomplete_calls':obs['incomplete_calls'],'saved_identical_command_fallbacks':fallbacks,
        'observation_timing_perturbed':True,'functional_acceptance_eligible':False,'camera_accessed':False,
        'source_sha256':sources}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();verify(args.result,args.output)
