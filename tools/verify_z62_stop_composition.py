"""Bind r100b real stop returns to the original C1.70 error-composition branch."""
import argparse
import json
from pathlib import Path
import struct
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
from record_z62_action_evidence import workspace,digest,require


def verify(result_path,proof_path,preliminary_path,output):
    result_path,proof_path,preliminary_path,output=map(workspace,(result_path,proof_path,preliminary_path,output))
    require(not output.exists(),'Use a new stop-composition verification path')
    record=json.loads(result_path.read_text(encoding='utf-8'));proof=json.loads(proof_path.read_text(encoding='utf-8'))
    preliminary=json.loads(preliminary_path.read_text(encoding='utf-8'))
    require(proof['completed_evidence_check'] and proof['original_result_sha256']==digest(result_path),
        'Original stop window has not passed source/frame validation')
    require(preliminary['completed_observation'] and preliminary['process_exit_code']==0 and
        preliminary['ready_observer'].get('scope_limit_reached') and preliminary['ready_observer']['stops']==128,
        'Preliminary scope budget result differs')
    require(not any(c['label']=='status-append-call' for c in preliminary['ready_observer']['calls']),
        'Preliminary original error publication unexpectedly present')
    calls={c['sequence']:c for c in record['ready_observer']['calls']}
    pairs=[(calls[r['call_sequence']],r) for r in record['ready_observer']['returns']]
    stops=sorted([(c,r) for c,r in pairs if c['label']=='capture-stop'],key=lambda pair:pair[0]['virtual_time_ns'])
    require(len(stops)==2 and [c['registers']['r0'] for c,r in stops]==[1,0] and
        [r['registers']['r0'] for c,r in stops]==[0,0x80],'Original stop argument/return composition differs')
    results=[]
    for call,returned in stops:
        enclosed=[(c,r) for c,r in pairs if c['virtual_time_ns']>=call['virtual_time_ns'] and
            r['virtual_time_ns']<=returned['virtual_time_ns'] and c['sequence']!=call['sequence']]
        modes=[(c,r) for c,r in enclosed if c['label'] in ('mode0-stop','mode2-stop')]
        require(len(modes)==1 and all(r['registers']['r0']==0 for c,r in enclosed),
            'A nested stop or cleanup contributes another error bit')
        require({c['label'] for c,r in enclosed}>={'cleanup-a','cleanup-b','cleanup-c','cleanup-d'},
            'Original cleanup return coverage incomplete')
        results.append({'argument':call['registers']['r0'],'result':returned['registers']['r0'],
            'call_time_ns':call['virtual_time_ns'],'return_time_ns':returned['virtual_time_ns'],
            'time_before_mode_entry_ns':modes[0][0]['virtual_time_ns']-call['virtual_time_ns'],
            'mode':modes[0][0]['label'],'all_nested_observed_results_zero':True,
            'nested_returns':[{'label':c['label'],'result':r['registers']['r0']} for c,r in enclosed]})
    image_path=Path(record['session'])/'inputs/master.bin';image=image_path.read_bytes();base=0x10020000
    require(digest(image_path)==record['master_sha256'],'Original image changed')
    decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
    decoded={i.address:(i.mnemonic,i.op_str) for i in decoder.disasm(image[0x102dbb9c-base:0x102dbbf4-base],0x102dbb9c)}
    expected={0x102dbba4:('movs','r3, #0x64'),0x102dbba8:('movw','r1, #0x800'),
        0x102dbbac:('bl','#0x1035d43a'),0x102dbbb0:('cbnz','r0, #0x102dbbb4'),
        0x102dbbb2:('movs','r5, #0x80'),0x102dbbc0:('orr.w','r4, r0, r5')}
    require(all(decoded.get(pc)==instruction for pc,instruction in expected.items()),'Original stop branch differs')
    literal_address=((0x102dbba2+4)&~3)+0x290
    event_object=struct.unpack_from('<I',image,literal_address-base)[0]
    require(event_object==0xc18a7634,'Original stop event object changed')
    sources={str(Path(__file__)):digest(Path(__file__)),**proof['source_sha256']}
    for name in ('scoped-stop-observation.json','stop-observation.json','failure-observation.json','finite-stream.json'):
        wrapper=json.loads((result_path.parent/name).read_text(encoding='utf-8'))
        require(wrapper['result_sha256']==digest(result_path),'Stop wrapper identity changed')
        sources.update(wrapper['source_sha256'])
    fallback=proof['saved_identical_command_fallbacks']
    for name,sha in sources.items():
        path=Path(name)
        if not path.is_file() and name in fallback:path=workspace(fallback[name])
        require(path.is_file() and digest(path)==sha,'Bound composition source changed: '+name)
    result={'schema':1,'completed_evidence_check':True,'original_result_sha256':digest(result_path),
        'frame_verification_sha256':digest(proof_path),'preliminary_result_sha256':digest(preliminary_path),
        'binary_sha256':record['binary_sha256'],'original_stop_results':results,
        'original_wait_object':hex(event_object),'wait_mask':0x800,'wait_limit_argument':100,
        'first_wait_failed_from_original_0x80_branch_and_zero_nested_returns':True,
        'direct_wait_CALL_RETURN_or_raw_kernel_error_traced':False,
        'raw_kernel_timeout_claimed':False,'original_status_0x3f_after_second_stop':True,
        'preliminary_128_stop_scope_exhaustion_preserved':True,
        'device_completion_root_cause_or_fix_verified':False,'guest_software_modified':False,
        'camera_accessed':False,'functional_acceptance_eligible':False,
        'source_sha256':sources,'saved_identical_command_fallbacks':fallback}
    require(any(row['code']==63 and row['virtual_time_ns']>=stops[1][1]['virtual_time_ns'] for row in proof['status_appends']),
        'Status publication did not follow the actual failing stop')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_sha256','saved_identical_command_fallbacks')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--proof',type=Path,required=True);parser.add_argument('--preliminary',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    verify(args.result,args.proof,args.preliminary,args.output)
