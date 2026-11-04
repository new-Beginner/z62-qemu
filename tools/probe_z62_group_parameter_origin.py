"""Read-only r94 parameter-origin observations on the frozen r93 kernel.

The VM is briefly stopped for coherent HMP reads of the Z62 parameter object
and its real curve pointer. No guest memory/register/parameter writes, input
controls, ready notifications, IRQs or speculative calibration are added.
"""
import argparse
import json
from pathlib import Path
import struct
from unittest.mock import patch
import probe_z62_capture_group_original as parent
import run_z62_capture_group as hardware
from record_z62_action_evidence import workspace,digest,require

BASE=0xc26a0884
VERSION='2026.11.04-group-parameter-origin-r94'


def capture(machine):
    running=machine.qmp.command('query-status')['running']
    if running:machine.qmp.command('stop')
    try:
        words=machine._words(BASE,44);blob=struct.pack('<44I',*words)
        pointer=words[0x80//4]
        result={'parameter_base':hex(BASE),'parameter_words':words,'parameter_bytes_hex':blob.hex(),
            'coefficient_bytes_24_hex':blob[0x58:0x70].hex(),'curve_pointer':hex(pointer),
            'guest_paused_for_coherent_read':True,'input_or_ready_injected':False}
        if pointer and not pointer&1 and ((0x10020000<=pointer<=0x12400000-132) or
                (0x13200000<=pointer<=0x14000000-132) or (0xc0000000<=pointer<=0xe0000000-132)):
            start=pointer&~3;delta=pointer-start;count=(delta+130+3)//4
            raw=struct.pack('<'+'I'*count,*machine._words(start,count))[delta:delta+130]
            result['curve_u16_65']=list(struct.unpack('<65H',raw));result['curve_bytes_hex']=raw.hex()
        else:result['curve_read_rejected']='Not a bounded known Z62 code/parameter/RAM pointer'
        return result
    finally:
        if running:machine.qmp.command('cont')


def run(qemu,card,group23,output,duration=8,wall_limit=300):
    qemu,card,group23,output=map(workspace,(qemu,card,group23,output))
    hardware.verify_build(qemu);base=parent.previous.original;prior=base.snapshot;observations=[];next_capture=0
    source_sha={str(Path(p)):digest(Path(p)) for p in (__file__,parent.__file__,hardware.__file__)}
    def snapshot(machine,layout):
        nonlocal next_capture
        row=prior(machine,layout)
        if row['capturework']['completed'] and row['virtual_time_ns']>=next_capture and len(observations)<8:
            observed=capture(machine);observed['virtual_time_ns']=row['virtual_time_ns']
            observations.append(observed);row['group_parameter_origin']=observed
            next_capture=row['virtual_time_ns']+750_000_000
            print('PARAMETER_ORIGIN',row['virtual_time_ns'],observed['curve_pointer'],
                any(observed.get('curve_u16_65',[])),flush=True)
        return row
    with patch.object(base,'snapshot',snapshot):result=parent.run(qemu,card,group23,output,duration,wall_limit)
    require(all(digest(Path(name))==sha for name,sha in source_sha.items()),'Origin observer source changed')
    receipt={'schema':1,'version':VERSION,'kernel_version':'2026.11.04-r93',
        'base_result_sha256':digest(output/'result.json'),'source_sha256':source_sha,
        'completed_observation':result['completed_observation'],'process_exit_code':result.get('process_exit_code'),
        'observations':observations,'guest_memory_or_registers_written':False,
        'new_parameter_file_supplied':False,'timing_perturbed_by_debug_stop':True,
        'functional_acceptance_eligible':False,'camera_accessed':False}
    with (output/'parameter-origin.json').open('x',encoding='utf-8') as handle:json.dump(receipt,handle,ensure_ascii=False,indent=2)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--duration',type=float,default=8)
    parser.add_argument('--wall-limit',type=float,default=300);args=parser.parse_args()
    result,receipt=run(args.qemu,args.card,args.group23,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and
        result.get('process_exit_code')==0 and receipt['observations'] else 1)
