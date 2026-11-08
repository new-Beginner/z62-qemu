"""Verify original RAM write stops and coverage without inferring a full call stack."""
import argparse
import json
from pathlib import Path
from verify_z62_cw_preview_recovery import verify as verify_data
from z62_cw_reentry_watch import WATCHES,MASTER_SHA
from record_z62_action_evidence import workspace,digest,require


def verify(case,output):
    case,output=map(workspace,(case,output));require(not output.exists(),'Use a new RAM evidence output')
    root=Path(__file__).resolve().parents[1];image_path=root/'artifacts/z62-reference-1.70/master.bin'
    require(digest(image_path)==MASTER_SHA,'Original master differs');image=image_path.read_bytes()
    receipt=json.loads((case/'reentry-write-observation.json').read_text(encoding='utf-8'))
    parent=json.loads((case/'reentry-observation.json').read_text(encoding='utf-8'))
    require(receipt['result_sha256']==digest(case/'result.json') and
        receipt['parent_receipt_sha256']==digest(case/'reentry-observation.json'),'RAM observation belongs to another window')
    trace=parent['trace'];require(trace['attached'] and trace.get('detach')=='OK','RAM window did not attach/detach cleanly')
    require(receipt['functional_acceptance_eligible'] is False and parent['functional_acceptance_eligible'] is False,
        'Timing-perturbed diagnostic must not qualify functionality')
    data_path=output.parent/'source-and-data.json';data=verify_data(case,data_path)
    previous={int(a,16):v for a,v in trace['initial_words'].items()};changes=[];writers=[]
    for hit in trace['memory_writes']:
        address=int(hit['address'],16);require(address in WATCHES,'Unknown RAM stop')
        r=hit['registers'];after=hit['after_original_step_registers'];start=int(hit['original_instruction_window_start'],16)
        raw=bytes.fromhex(hit['original_instruction_window_hex'])
        require(len(raw)==32 and raw==image[start-0x10020000:start-0x10020000+32],'Writer code window differs')
        require(start==r['pc']-8 and len(bytes.fromhex(hit['stack_hex']))==256,'Original context incomplete')
        require('cpsr' in r and 'cpsr' in after,'Instruction-set mode was not captured')
        require(hit['all_watched_words_before'][hex(address)]==hit['word_before_original_step'] and
            hit['all_watched_words_after'][hex(address)]==hit['word_after_original_step'],'RAM word receipt inconsistent')
        last=previous[address];new=hit['word_after_original_step']
        if last!=new:changes.append({'address':hex(address),'previous_observed_word':last,'new_word':new,
            'virtual_time_ns':hit['virtual_time_ns'],'watch_stop_pc':hex(r['pc']),'after_step_pc':hex(after['pc'])})
        previous.update({int(a,16):v for a,v in hit['all_watched_words_after'].items()})
        writers.append({'label':hit['label'],'address':hex(address),'watch_stop_pc':hex(r['pc']),
            'instruction_set':'Thumb' if r['cpsr']&32 else 'ARM','link':hex(r['lr']),
            'virtual_time_ns':hit['virtual_time_ns'],'word_at_stop':hit['word_before_original_step'],
            'word_after_original_step':new,'caller':hit['caller'],'complete_call_chain_verified':False})
    sources={**data['source_sha256'],**parent['source_sha256'],**receipt['source_sha256'],str(Path(__file__).resolve()):digest(Path(__file__))}
    canonical={}
    for name,sha in sources.items():
        p=Path(name).resolve();require(p.is_file() and digest(p)==sha,'RAM observer source changed: '+name)
        key=str(p);require(key not in canonical or canonical[key]==sha,'Canonical source mismatch');canonical[key]=sha
    out={'schema':1,'completed_evidence_check':True,'original_result_sha256':digest(case/'result.json'),
        'RAM_receipt_sha256':digest(case/'reentry-write-observation.json'),
        'source_and_data_verification_sha256':digest(data_path),'original_accepted_packets_reconstructed':data['original_accepted_packets_reconstructed'],
        'completed_original_observation':data['completed_original_observation'],'memory_write_hits':len(writers),
        'writers':writers,'observed_word_changes':changes,
        'actual_index_write_observed':any(c['address']=='0xc1811e60' for c in changes),
        'watched_index_value_at_attach':trace['initial_words'].get('0xc1811e60'),
        'watched_index_value_at_close':trace['final_words'].get('0xc1811e60'),
        'half_request_ns':trace.get('half_request_ns'),'post_half_index3_ns':trace.get('post_half_index3_ns'),
        'scope_limit_reached':trace.get('scope_limit_reached',False),'close_reason':trace.get('close_reason'),
        'exact_write_instruction_identified':False,'complete_call_chain_verified':False,
        'guest_debug_timing_perturbed':True,'functional_acceptance_eligible':False,
        'complete_camera_or_AF_or_flash_safety_verified':False,'camera_accessed':False,'source_sha256':canonical}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(out,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in out.items() if k!='source_sha256'}),flush=True)
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();verify(args.case,args.output)
