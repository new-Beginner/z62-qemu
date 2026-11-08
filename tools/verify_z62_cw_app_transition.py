"""Verify real callback/notification pairs past index assignment on r108."""
import argparse
import json
from pathlib import Path
import z62_cw_app_transition_observer as observation
from verify_z62_cw_preview_recovery import verify as verify_data
from record_z62_action_evidence import workspace,digest,require


def verify(case,output):
    case,output=map(workspace,(case,output));require(not output.exists(),'Use a new application evidence output')
    parent=json.loads((case/'reentry-observation.json').read_text(encoding='utf-8'))
    receipt=json.loads((case/'app-transition-observation.json').read_text(encoding='utf-8'))
    require(parent['result_sha256']==receipt['result_sha256']==digest(case/'result.json') and
        receipt['parent_receipt_sha256']==digest(case/'reentry-observation.json'),'Application receipt belongs to another run')
    trace=parent['trace'];require(trace['attached'] and trace.get('detach')=='OK','Application observer did not detach')
    require(parent['functional_acceptance_eligible'] is False and receipt['functional_acceptance_eligible'] is False,
        'Guest debug window incorrectly qualifies functionality')
    data_path=output.parent/'source-and-data.json';data=verify_data(case,data_path)
    image=(Path(__file__).resolve().parents[1]/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    require(observation.contract(image)==trace['static_anchors'],'Original application contract differs')
    for a in trace['live_anchors']:
        pc=int(a['pc'],16);require(bytes.fromhex(a['bytes'])==image[pc-observation.BASE:pc-observation.BASE+4],
            'Live application anchor differs')
    calls={r['sequence']:r for r in trace['calls']};pairs=[];callbacks=[]
    for ret in trace['returns']:
        call=calls[ret['call_sequence']];pc=int(call['pc'],16);r=call['registers'];after=ret['registers']
        expected=pc+observation.CALLS[pc] if pc in observation.CALLS else r['lr']&~1
        require(call['thread']==ret['thread'] and r['sp']==after['sp'] and after['pc']==expected,
            'Application return frame differs')
        require(ret['elapsed_virtual_ns']==ret['virtual_time_ns']-call['virtual_time_ns']>=0,'Application return time differs')
        require(bytes.fromhex(call['return_anchor']['bytes'])==image[expected-observation.BASE:expected-observation.BASE+4],
            'Return code differs from original')
        pairs.append({'label':call['label'],'call_sequence':call['sequence'],'return_sequence':ret['sequence'],
            'call_pc':hex(pc),'return_pc':hex(expected),'entry_ns':call['virtual_time_ns'],'return_ns':ret['virtual_time_ns'],
            'elapsed_ns':ret['elapsed_virtual_ns'],'input_r0_r3':[r['r'+str(i)] for i in range(4)],
            'result_r0':after['r0'],'manager_index_word_at_entry':call['manager_words'][4],
            'observed_C1821EB8_at_entry':call['observed_C1821EB8'],'observed_C1821EB8_at_return':ret['observed_C1821EB8']})
    for call in trace['calls']:
        pc=int(call['pc'],16)
        if pc!=0x1029a906:continue
        target=call['registers']['r3']&~1;after=call['after_original_step_registers']
        require(after['pc']==target and call['callback_target']==hex(target),'Actual BLX target differs')
        require(bytes.fromhex(call['callback_target_anchor']['bytes'])==image[target-observation.BASE:target-observation.BASE+4],
            'Original callback entry differs')
        require(all(after['r'+str(i)]==call['registers']['r'+str(i)] for i in range(3)),
            'BLX unexpectedly changed callback arguments')
        callbacks.append({'call_sequence':call['sequence'],'target':hex(target),
            'instruction_set':'Thumb' if call['registers']['r3']&1 else 'ARM',
            'arguments_r0_r2':[call['registers']['r'+str(i)] for i in range(3)],
            'virtual_time_ns':call['virtual_time_ns'],'actual_original_BLX_entry_verified':True})
    markers=[r for r in trace['stores'] if int(r['pc'],16) in (0x1029a8ea,0x1029a916)]
    require(markers and all(r['after_original_step_registers']['pc']==int(r['pc'],16)+2 for r in markers),
        'Mandatory manager execution-point positive control missing')
    first=trace.get('first_post_half_index3_ns')
    require(first and trace.get('index_assignment_did_not_end_observation') and trace['close_reason']=='bounded-window-end',
        'Observer ended at the index assignment again')
    sources={**data['source_sha256'],**parent['source_sha256'],**receipt['source_sha256'],str(Path(__file__).resolve()):digest(Path(__file__))}
    canonical={}
    for name,sha in sources.items():
        path=Path(name).resolve();require(path.is_file() and digest(path)==sha,'Application observer source changed: '+name)
        key=str(path);require(key not in canonical or canonical[key]==sha,'Canonical source identity conflicts');canonical[key]=sha
    result={'schema':1,'completed_evidence_check':True,'original_result_sha256':digest(case/'result.json'),
        'app_receipt_sha256':digest(case/'app-transition-observation.json'),'source_and_data_verification_sha256':digest(data_path),
        'original_accepted_packets_reconstructed':data['original_accepted_packets_reconstructed'],
        'completed_original_observation':data['completed_original_observation'],
        'original_call_pairs':pairs,'actual_indirect_callbacks':callbacks,'call_count':len(trace['calls']),
        'return_count':len(trace['returns']),'incomplete_calls':trace['incomplete_calls'],
        'manager_execution_point_positive_control_hits':len(markers),
        'first_post_half_index3_ns':first,'last_post_half_index3_sample_ns':trace.get('post_half_index3_ns'),
        'post_index3_call_pairs':[p for p in pairs if p['entry_ns']>=first],
        'scope_limit_reached':trace.get('scope_limit_reached',False),'guest_debug_timing_perturbed':True,
        'functional_acceptance_eligible':False,'complete_camera_or_AF_or_flash_safety_verified':False,
        'camera_accessed':False,'source_sha256':canonical}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_sha256','original_call_pairs','post_index3_call_pairs')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();verify(args.case,args.output)
