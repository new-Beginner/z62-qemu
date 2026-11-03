"""Verify actual kernel publication and AND-wait results separately from camera acceptance."""
import argparse
import json
from pathlib import Path

from record_z62_action_evidence import workspace,digest,require
from z62_kernel_event_layout import contract


def assess(row, require_transition=False):
    require(row['completed_observation'] and row.get('detach')=='OK' and not row.get('failure') and
            not row.get('cleanup_error') and row['sources_unchanged'], 'Incomplete kernel observation')
    require(not row['controls_sent'] and all(r['method']=='GET' for r in row['http_requests']) and
            row['functional_acceptance_eligible'] is False and row['guest_memory_written'] is False and
            row['guest_registers_written'] is False and row['inferior_functions_called'] is False,
            'Kernel observation crossed its read-only boundary')
    require(row['initial_gate']['capture_flow']['active_word']==row['after_detach']['capture_flow']['active_word']==0,
            'Original capture became active')
    for software in (row['software_before'],row['software_after']):
        require(not software['half_pressed'] and not software['full_pressed'] and not software['card']['images'],
                'Kernel observation used controls or created photos')
    identifier=row['initial_event']['identifier']; cb=row['initial_event']['control_block']
    sets=[]; pending=None
    for hit in row['hits']:
        event=hit['event']; reg=hit['registers']
        require(event['identifier']==identifier and event['control_block']==cb and
                event['raw_words'][2]==int(identifier,16) and event['raw_words'][5]==int(event['pattern'],16) and
                int(event['pattern_address'],16)==int(cb,16)+20, 'Event CB identity or pattern differs')
        if hit['label']=='kernel-set-entry':
            require(pending is None and reg['r0']==identifier and reg['r1']=='0x800000','Wrong setter entry')
            pending={'entry':hit}
        elif hit['label']=='kernel-pattern-store':
            require(pending is not None and reg['r4']==cb and
                    int(reg['sp'],16)==int(pending['entry']['registers']['sp'],16)-40,'Setter frame differs')
            before=int(event['pattern'],16); after=hit['after_original_store']
            require(int(reg['r0'],16)==before|int(reg['r6'],16) and after['identifier']==identifier and
                    int(after['pattern'],16)==int(reg['r0'],16),'Original kernel OR publication differs')
            pending['publication']={'before':hex(before),'after':after['pattern'],'sequence':hit['sequence']}
        elif hit['label']=='kernel-set-return':
            require(pending is not None and 'publication' in pending and reg['r0']=='0x0' and
                    hit['kernel_result_signed']==0 and hit['thread']==pending['entry']['thread'] and
                    int(reg['sp'],16)==int(pending['entry']['registers']['sp'],16)-40,'Setter result/frame differs')
            sets.append(pending['publication']); pending=None
    require(pending is None and sets,'No completed original setter')
    zero_to_bit=any(s['before']=='0x0' and s['after']=='0x800000' for s in sets)
    require(not require_transition or zero_to_bit,'No actual zero-to-bit publication observed')
    waits={h['label']:h for h in row['hits'] if h['label'] in
           ('wait-call','kernel-wait-entry','kernel-and-test','kernel-wait-result','wait-return')}
    require(len(waits)==5,'Incomplete target wait')
    call,kernel,test,result,returned=(waits[k] for k in
        ('wait-call','kernel-wait-entry','kernel-and-test','kernel-wait-result','wait-return'))
    require(kernel['registers']['r0']==identifier and kernel['registers']['r1']=='0x5b00000' and
            kernel['registers']['r2']=='0x0' and kernel['timeout_argument']==200,'Original wait ABI differs')
    require(test['registers']['r4']==cb and test['registers']['r6']=='0x0' and
            int(test['missing_mask_after_original_bics'],16)==
            (int(test['registers']['r7'],16)&~int(test['registers']['r3'],16)),'Original AND result differs')
    require(result['registers']['pc']=='0x1035d450' and result['before_boolean_conversion'] is True and
            int(result['registers']['sp'],16)==int(call['registers']['sp'],16)-16 and
            result['registers']['r0']=='0xffce0000' and result['kernel_result_signed']==-3276800,
            'Raw kernel wait result differs')
    require(returned['registers']['sp']==call['registers']['sp'] and returned['registers']['r0']=='0x0' and
            returned['output_at_sp']=='0x0','Boolean wrapper result differs')
    pattern=int(returned['event']['pattern'],16)
    return {'setter_publications':sets,'zero_to_00800000_proven':zero_to_bit,
        'kernel_wait_result':'0xffce0000','kernel_wait_result_signed':-3276800,
        'kernel_wait_main_error_signed':-50,'wrapper_wait_result':0,'wait_output':0,
        'wait_duration_ns':returned['virtual_time_ns']-call['virtual_time_ns'],
        'actual_pattern_at_wait_return':hex(pattern),'missing_mask_at_wait_return':hex(0x5b00000&~pattern)}


def verify(session,case,output):
    session,case,output=map(workspace,(session,case,output)); hashes={}
    def read(path):
        hashes[str(path)]=digest(path); return json.loads(path.read_text(encoding='utf-8'))
    layout=contract((session/'inputs/master.bin').read_bytes())
    failed=read(case/'events-1/result.json')
    recovery=read(case/'recovery-2/result.json')
    require(failed['completed_observation'] is False and failed.get('cleanup_error') and
            recovery['completed_recovery'] is True and recovery['detach']=='OK' and
            recovery['failed_result_sha256']==digest(case/'events-1/result.json') and
            recovery['owner']['ProcessId']==failed['owner']['ProcessId'],'Failed observer/recovery scope differs')
    for removed in recovery['removed']:
        require(removed['response']=='OK' or (removed['response']=='E22' and
                removed.get('probe_insert')==removed.get('probe_remove')=='OK'),'Breakpoint clear not established')
    results={}
    for name in ('events-2','events-3'):
        row=read(case/name/'result.json'); require(row['layout']==layout,'Target layout differs')
        require(row['owner']['ProcessId']==failed['owner']['ProcessId'],'VM changed between observations')
        for table in (row['source_sha256'],read(case/name/'source-binding.json')['source_sha256']):
            require(all(digest(Path(p))==sha for p,sha in table.items()),'Kernel observer source changed')
        results[name]=assess(row,require_transition=name=='events-3')
    reference=read(case/'kernel-contract-1.json')
    require(reference['layout']==layout and reference['public_selector_matches_target'] is False and
            reference['target_rtos_product_or_version_proven'] is False,'Reference boundary differs')
    root=Path(__file__).resolve().parents[1]
    for name,item in reference['public_reference']['files'].items():
        require(digest(root/'references/rtos/tkernel_2'/name)==item['sha256'],'Public reference changed')
    record={'schema':1,'completed_evidence_check':True,'verifier_sha256':digest(Path(__file__)),
        'artifact_sha256':hashes,'layout':layout,'observations':results,
        'first_probe_incomplete_preserved':True,'same_vm_recovered_without_restart':True,
        'actual_kernel_pattern_read':True,'original_setter_zero_result_proven':True,
        'original_zero_to_00800000_publication_proven':True,'AND_wait_not_satisfied':True,
        'target_rtos_product_or_version_proven':False,'camera_accessed':False,
        'factory_capture_verified':False,'functional_acceptance_eligible':False,'AF_verified':False}
    with output.open('x',encoding='utf-8') as handle: json.dump(record,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in record.items() if k not in ('artifact_sha256','layout')},ensure_ascii=False))
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',type=Path,required=True); parser.add_argument('--case',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    verify(args.session,args.case,args.output)
