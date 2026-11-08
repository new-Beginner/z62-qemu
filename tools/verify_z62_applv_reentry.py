"""r109 APPLV object/predicate evidence; do not treat flags as a causal repair."""
import argparse
import json
from pathlib import Path
import struct
from unittest.mock import patch
import z62_cw_app_transition_observer as old
import z62_applv_reentry_observer as current
from verify_z62_cw_app_transition import verify as verify_calls
from record_z62_action_evidence import workspace,digest,require


def verify(case,output):
    case,output=map(workspace,(case,output));require(not output.exists(),'Use a new APPLV evidence output')
    receipt=json.loads((case/'applv-reentry-observation.json').read_text(encoding='utf-8'))
    parent=json.loads((case/'reentry-observation.json').read_text(encoding='utf-8'))
    require(receipt['result_sha256']==digest(case/'result.json') and
        receipt['parent_receipt_sha256']==digest(case/'app-transition-observation.json'),'APPLV receipt differs')
    trace=parent['trace'];call_output=output.parent/'manager-and-calls.json'
    with (patch.object(old,'POINTS',current.POINTS),patch.object(old,'CALLS',current.CALLS),patch.object(old,'contract',current.contract)):
        calls=verify_calls(case,call_output)
    entries={r['sequence']:r for r in trace['calls']};objects=[];setters=[];snapshots=0
    for row in trace['hits']:
        require(row['snapshot_after_original_single_step'] and len(bytes.fromhex(row['applv_object_c181d9e4_hex']))==128
            and len(bytes.fromhex(row['applv_flags_c181d9a0_hex']))==64,'APPLV stopped source snapshot incomplete')
        snapshots+=1
        if row.get('argument_object_pointer'):
            raw=bytes.fromhex(row['argument_object_hex']);require(len(raw)==128,'Argument object incomplete')
            objects.append({'sequence':row['sequence'],'label':row['label'],'pointer':row['argument_object_pointer'],
                'object_field_28':hex(struct.unpack_from('<I',raw,0x28)[0]),
                'object_method_3c':hex(struct.unpack_from('<I',raw,0x3c)[0]),
                'captured_after_original_single_step':True,'method_target_execution_independently_observed':False})
    for returned in trace['returns']:
        entry=entries[returned['call_sequence']]
        if int(entry['pc'],16)!=0x105b3358:continue
        after=entry['after_original_step_registers']
        require(after['r1']+4==0xc1821eb8,'Original setter address base differs')
        require(returned['observed_C1821EB8']==entry['registers']['r0'],
            'Returned original setter did not leave its actual argument in the flag')
        setters.append({'call_sequence':entry['sequence'],'return_sequence':returned['sequence'],
            'entry_ns':entry['virtual_time_ns'],'return_ns':returned['virtual_time_ns'],
            'actual_argument':entry['registers']['r0'],'before':entry['observed_C1821EB8'],
            'after':returned['observed_C1821EB8'],'original_link':hex(entry['registers']['lr']),
            'original_store_destination':hex(after['r1']+4)})
    sources={**calls['source_sha256'],**receipt['source_sha256'],str(Path(__file__).resolve()):digest(Path(__file__))}
    canonical={}
    for name,sha in sources.items():
        p=Path(name).resolve();require(p.is_file() and digest(p)==sha,'APPLV source changed: '+name)
        key=str(p);require(key not in canonical or canonical[key]==sha,'Canonical source conflict');canonical[key]=sha
    selected=[r for r in calls['original_call_pairs'] if int(r['call_pc'],16) in current.EXTRA_FUNCTIONS or
        int(r['call_pc'],16) in current.EXTRA_CALLS]
    result={'schema':1,'completed_evidence_check':True,'original_result_sha256':digest(case/'result.json'),
        'applv_receipt_sha256':digest(case/'applv-reentry-observation.json'),
        'manager_call_verification_sha256':digest(call_output),
        'original_accepted_packets_reconstructed':calls['original_accepted_packets_reconstructed'],
        'completed_original_observation':calls['completed_original_observation'],
        'APPLV_stopped_snapshots':snapshots,'APPLV_actual_call_pairs':selected,'object_snapshots':objects,
        'original_flag_setter_pairs':setters,'original_flag_production_observed':bool(setters),
        'flag_is_cause_of_missing_capture_restart_proven':False,
        'incomplete_calls':calls['incomplete_calls'],'scope_limit_reached':calls['scope_limit_reached'],
        'functional_acceptance_eligible':False,'complete_camera_or_AF_or_flash_safety_verified':False,
        'camera_accessed':False,'source_sha256':canonical}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_sha256','APPLV_actual_call_pairs','object_snapshots')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();verify(args.case,args.output)
