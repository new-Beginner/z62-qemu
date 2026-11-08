"""Validate six original STRB effects and the scope gap after index assignment."""
import argparse
import json
from pathlib import Path
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
from record_z62_action_evidence import workspace,digest,require

SPECS={0x1029a916:('r1',1),0x1029a8ea:('r3',0),0x1029a8ee:('r1',1)}


def analyze(case,output):
    case,output=map(workspace,(case,output));require(not output.exists(),'Use a new index semantics output')
    image_path=Path(__file__).resolve().parents[1]/'artifacts/z62-reference-1.70/master.bin'
    require(digest(image_path)=='bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4','Original master differs')
    image=image_path.read_bytes();base=0x10020000;decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
    trace_path=case/'reentry-observation.json';trace=json.loads(trace_path.read_text(encoding='utf-8'))['trace']
    record=json.loads((case/'result.json').read_text(encoding='utf-8'));writes=[]
    for row in trace['memory_writes']:
        r=row['registers'];pc=r['pc'];require(pc in SPECS and r['cpsr']&32,'Unknown writer or instruction-set mode')
        register,offset=SPECS[pc];insn=next(decoder.disasm(image[pc-base:pc-base+4],pc,count=1))
        expected_operands=register+', [r4'+(', #1]' if offset else ']')
        require((insn.mnemonic,insn.op_str,insn.size)==('strb',expected_operands,2),'Original byte-store differs')
        require(r['r4']==0xc1811e60 and row['after_original_step_registers']['pc']==pc+2,
            'Original store target or single-step PC differs')
        old=row['word_before_original_step'];new=row['word_after_original_step'];shift=offset*8
        require(new==((old&~(255<<shift))|((r[register]&255)<<shift)),'Actual original byte effect differs')
        writes.append({'pc':hex(pc),'virtual_time_ns':row['virtual_time_ns'],'byte_offset':offset,
            'stored_byte':r[register]&255,'old_word':hex(old),'new_word':hex(new),
            'original_instruction':insn.mnemonic+' '+insn.op_str,'single_step_effect_verified':True})
    require(len(writes)==6,'Expected complete two-stage index transition differs')
    # Actual original code places the active-index store before its optional
    # callback branch. This is ordering evidence, not proof the callback ran.
    expected={0x1029a8ea:('strb','r3, [r4]'),0x1029a8ee:('strb','r1, [r4, #1]'),
        0x1029a906:('blx','r3')}
    for pc,pair in expected.items():
        insn=next(decoder.disasm(image[pc-base:pc-base+4],pc,count=1))
        require((insn.mnemonic,insn.op_str)==pair,'Original manager ordering differs')
    last_flag=trace['final_words']['0xc1821eb8'];final_flag=record['final']['original_words']['0xc1821eb8'][0]
    require(last_flag==0 and final_flag==1,'Expected post-observer flag change differs')
    result={'schema':1,'completed_evidence_check':True,'original_result_sha256':digest(case/'result.json'),
        'watch_trace_sha256':digest(trace_path),'exact_original_byte_stores_verified':writes,
        'index_assignment_precedes_optional_callback_in_original_code':True,
        'optional_callback_execution_observed_in_this_case':False,
        'observed_flag_at_debugger_close':last_flag,'observed_flag_at_window_end':final_flag,
        'flag_change_after_prior_observer_close_proven':True,
        'prior_observer_close_ns':trace['post_half_index3_ns'],'window_end_ns':record['final']['virtual_time_ns'],
        'index3_does_not_prove_application_initialization_complete':True,
        'complete_original_reentry_path_verified':False,'camera_accessed':False,
        'source_sha256':{str(Path(__file__).resolve()):digest(Path(__file__))}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();analyze(args.case,args.output)
