"""Verify actual request branches and sampled parameter qualification, no repair claim."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import z62_cw_app_transition_observer as old
import z62_request_qualification_observer as current
from verify_z62_cw_app_transition import verify as verify_calls
from record_z62_action_evidence import workspace,digest,require


def verify(case,output):
    case,output=map(workspace,(case,output));require(not output.exists(),'Use new qualification evidence')
    receipt=json.loads((case/'request-qualification-observation.json').read_text(encoding='utf-8'))
    parent=json.loads((case/'reentry-observation.json').read_text(encoding='utf-8'))
    require(receipt['result_sha256']==digest(case/'result.json') and
        receipt['parent_receipt_sha256']==digest(case/'app-transition-observation.json'),'Qualification receipt differs')
    trace=parent['trace'];call_path=output.parent/'manager-and-calls.json'
    with (patch.object(old,'POINTS',current.POINTS),patch.object(old,'CALLS',current.CALLS),
            patch.object(old,'MARKERS',current.MARKERS),patch.object(old,'contract',current.contract)):
        data=verify_calls(case,call_path)
    proof=[]
    for row in trace['hits']:
        require(row['mode_snapshot_after_original_single_step'] and
            len(bytes.fromhex(row['mode_state_c181b47c_after_step_hex']))==64,'Mode snapshot incomplete')
        pc=int(row['pc'],16);r=row['registers'];after=row['after_original_step_registers']
        if pc==0x10634902:
            equal=r['r8']==r['r5'];require(bool(after['cpsr']&0x40000000)==equal,'Original CMP flags differ')
            proof.append({'label':row['label'],'old_value_r8':r['r8'],'new_value_r5':r['r5'],
                'equal':equal,'original_CMP_Z_verified':True,'virtual_time_ns':row['virtual_time_ns']})
        elif pc in (0x1063490a,0x10542a02,0x10540f68):
            if pc==0x10542a02:condition=r['r4']==0;target=0x10542a6c
            else:condition=bool(r['cpsr']&0x40000000);target=0x10634914 if pc==0x1063490a else 0x1054104e
            expected=target if condition else pc+2
            require(after['pc']==expected,'Original conditional branch result differs')
            proof.append({'label':row['label'],'condition':condition,'actual_after_PC':hex(after['pc']),
                'r0':r['r0'],'r4':r['r4'],'r9':r['r9'],'r10':r['r10'],'virtual_time_ns':row['virtual_time_ns'],
                'original_branch_execution_verified':True})
        elif pc in (0x10634922,0x10542aa8):
            value=r['r9'] if pc==0x10634922 else r['r4']
            require(after['r0']==value,'Original returned-value MOV differs')
            proof.append({'label':row['label'],'actual_return_value':value,'virtual_time_ns':row['virtual_time_ns']})
    queries=[p for p in data['original_call_pairs'] if p['label']=='parameter-19-query']
    require(len(queries)==4 and all(p['input_r0_r3'][0]==0x19 for p in queries),'Bounded query sample differs')
    branches=[p for p in proof if p['label']=='parameter-19-branch']
    require(len(branches)==4 and trace['setter_and_clear_call_still_armed'],'Qualification sampling removed global observations')
    request_pairs=[p for p in data['original_call_pairs'] if p['label'] in ('request-mode-conversion','transition-request',
        'changed-mode-query','changed-mode-operation','changed-mode-dispatch')]
    sources={**data['source_sha256'],**receipt['source_sha256'],str(Path(__file__).resolve()):digest(Path(__file__))}
    canonical={}
    for name,sha in sources.items():
        path=Path(name).resolve();require(path.is_file() and digest(path)==sha,'Qualification source changed: '+name)
        key=str(path);require(key not in canonical or canonical[key]==sha,'Canonical source conflict');canonical[key]=sha
    result={'schema':1,'completed_evidence_check':True,'original_result_sha256':digest(case/'result.json'),
        'qualification_receipt_sha256':digest(case/'request-qualification-observation.json'),
        'call_verification_sha256':digest(call_path),'original_accepted_packets_reconstructed':data['original_accepted_packets_reconstructed'],
        'completed_original_observation':data['completed_original_observation'],'actual_request_call_pairs':request_pairs,
        'actual_original_branch_and_value_proofs':proof,'parameter_19_first_four_queries':queries,
        'parameter_19_all_queries_in_window_sampled':False,
        'clear_call_marker_hits':sum(r['label']=='parameter-clear-call-marker' for r in trace['hits']),
        'special_zero_assignment_hits':sum(r['label']=='request-special-zero' for r in trace['hits']),
        'setter_arguments':[r['registers']['r0'] for r in trace['calls'] if r['label']=='observed-flag-setter'],
        'incomplete_calls':data['incomplete_calls'],'scope_limit_reached':data['scope_limit_reached'],
        'missing_capture_restart_root_cause_verified':False,'functional_acceptance_eligible':False,
        'complete_camera_or_AF_or_flash_safety_verified':False,'camera_accessed':False,'source_sha256':canonical}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_sha256','parameter_19_first_four_queries')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();verify(args.case,args.output)
