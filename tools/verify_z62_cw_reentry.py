"""Verify actual original call pairs without promoting a debug run to acceptance."""
import argparse
import json
from pathlib import Path
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
import z62_cw_reentry_observer as observation
from verify_z62_cw_preview_recovery import verify as verify_data
from record_z62_action_evidence import workspace,digest,require


def verify(case,output):
    case,output=map(workspace,(case,output));require(not output.exists(),'Use a new reentry evidence output')
    raw=json.loads((case/'reentry-observation.json').read_text(encoding='utf-8'))
    base=json.loads((case/'result.json').read_text(encoding='utf-8'))
    require(raw['result_sha256']==digest(case/'result.json') and
        raw['recovery_observer_sha256']==digest(case/'recovery-observer.json'),'Reentry receipt belongs to another run')
    require(raw['actual_independent_guest_GDB_attached'] and raw['functional_acceptance_eligible'] is False,
        'Independent diagnostic attachment is not classified as timing perturbed')
    trace=raw['trace'];require(trace['attached'] and trace.get('detach')=='OK','Diagnostic did not attach/detach cleanly')
    data_path=output.parent/'source-and-data.json';data=verify_data(case,data_path)
    image=(observation.Path(__file__).resolve().parents[1]/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    require(observation.contract(image)==trace['static_anchors'],'Static original anchors changed')
    for anchor in trace['live_anchors']:
        pc=int(anchor['pc'],16);require(bytes.fromhex(anchor['bytes'])==image[pc-observation.BASE:pc-observation.BASE+4],
            'Live point not original C1.70')
    calls={r['sequence']:r for r in trace['calls']};pairs=[];decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
    require(len(calls)==len(trace['calls']),'Call identity duplicated')
    for ret in trace['returns']:
        call=calls[ret['call_sequence']];pc=int(call['pc'],16);r=call['registers'];after=ret['registers']
        require(call['thread']==ret['thread'] and r['sp']==after['sp'],'Return frame does not match call')
        expected=pc+4 if pc in observation.WAIT_CALLS else r['lr']&~1
        require(after['pc']==expected and ret['virtual_time_ns']>=call['virtual_time_ns'] and
            ret['elapsed_virtual_ns']==ret['virtual_time_ns']-call['virtual_time_ns'],'Actual return PC/time mismatch')
        anchor=call['return_anchor'];require(bytes.fromhex(anchor['bytes'])==image[expected-observation.BASE:expected-observation.BASE+4],
            'Original dynamic return anchor differs')
        row={'label':call['label'],'call_sequence':call['sequence'],'return_sequence':ret['sequence'],
            'call_pc':hex(pc),'return_pc':hex(expected),'entry_virtual_ns':call['virtual_time_ns'],
            'return_virtual_ns':ret['virtual_time_ns'],'elapsed_virtual_ns':ret['elapsed_virtual_ns'],
            'input_r0_r3':[r['r'+str(i)] for i in range(4)],'result_r0':after['r0'],'status_codes':ret['status_codes']}
        if pc in observation.WAIT_CALLS:
            insn=next(decoder.disasm(bytes.fromhex(anchor['bytes']),expected,count=1))
            require(insn.mnemonic in ('cbz','cbnz') and insn.op_str.startswith('r0,'),'Unexpected original wait-result branch')
            row['following_original_instruction']={'mnemonic':insn.mnemonic,'operands':insn.op_str}
            row['following_branch_condition_from_result']=(after['r0']==0 if insn.mnemonic=='cbz' else after['r0']!=0)
            row['branch_execution_independently_observed']=False
        pairs.append(row)
    for hit in trace['hits']:
        require(len(bytes.fromhex(hit['stack_hex']))==256,'Raw bounded stack missing')
    sources={**data['source_sha256'],**raw['source_sha256'],str(Path(__file__).resolve()):digest(Path(__file__))}
    canonical={}
    for name,sha in sources.items():
        path=Path(name).resolve();require(path.is_file() and digest(path)==sha,'Diagnostic source changed: '+name)
        key=str(path);require(key not in canonical or canonical[key]==sha,'Canonical source identity conflict');canonical[key]=sha
    out={'schema':1,'completed_evidence_check':True,'original_result_sha256':digest(case/'result.json'),
        'reentry_receipt_sha256':digest(case/'reentry-observation.json'),'source_and_data_verification_sha256':digest(data_path),
        'binary_sha256':base['binary_sha256'],'original_accepted_packets_reconstructed':data['original_accepted_packets_reconstructed'],
        'completed_original_observation':data['completed_original_observation'],'actual_original_call_pairs':pairs,
        'call_count':len(trace['calls']),'return_count':len(trace['returns']),'incomplete_calls':trace['incomplete_calls'],
        'attach_menu_time_ns':trace.get('attach_menu_time_ns'),'half_request_ns':trace.get('half_request_ns'),
        'post_half_index3_ns':trace.get('post_half_index3_ns'),'close_reason':trace.get('close_reason'),
        'scope_limit_reached':trace.get('scope_limit_reached',False),'input_start_store_hits':len(trace['stores']),
        'guest_debug_timing_perturbed':True,'functional_acceptance_eligible':False,
        'parent_no_debugger_flags_are_only_builtin_observer_scope':True,
        'complete_camera_or_AF_or_flash_safety_verified':False,'camera_accessed':False,'source_sha256':canonical}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(out,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in out.items() if k!='source_sha256'}),flush=True)
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();verify(args.case,args.output)
