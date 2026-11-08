"""Replay the frozen CW admission masks from actual CPU MMIO writes, read-only."""
import argparse
import json
from pathlib import Path
import re
import run_z62_capturework_preview as hardware
from record_z62_action_evidence import workspace,digest,require

PATTERN=re.compile(r'nikon_z62_mmio_write cpu (\d+) mr ([0-9a-fA-F]+) addr (0x[0-9a-f]+) value (0x[0-9a-f]+) size (\d+)')
ADDRESSES={0x20068000,0x20068004,0x20068008,0x2006800c,0x20068010,0x20068014}
REQUIRED=0x20d


def analyze(case,output):
    case,output=map(workspace,(case,output));require(not output.exists(),'Use a new mask replay output')
    hardware.verify_build();root=hardware.DEFAULT_QEMU.parent.parent
    build=json.loads((root/'reference-build-manifest.json').read_text(encoding='utf-8'))
    model=Path(build['source'])/'hw/arm/nikon-z62-capturework-device.h'
    text=model.read_text(encoding='utf-8')
    require('(c->held&0x20d)' in text and '(c->allowed&c->running&0x20d)!=0x20d' in text,
        'Frozen model admission masks differ')
    held=allowed=running=0;writes=[];transitions=[];last=None;cpus=set();last_enable=None
    trace=case/'closed-console.txt'
    for line_number,line in enumerate(trace.read_text(encoding='utf-8',errors='strict').splitlines(),1):
        match=PATTERN.search(line)
        if not match:continue
        cpu,mr,address,value,size=match.groups();address,value=int(address,16),int(value,16)
        if address not in ADDRESSES:continue
        require(int(size)==4 and int(cpu) in (0,1),'Control replay encountered another engine or access width')
        cpus.add(int(cpu))
        if address==0x20068000:held|=value&0xfff
        elif address==0x20068004:held&=~value
        elif address==0x20068008:running|=value&0xfff
        elif address==0x2006800c:running&=~value
        elif address==0x20068010:allowed|=value&0xfff
        elif address==0x20068014:allowed&=~value;running&=~value
        gate=not(held&REQUIRED) and (allowed&running&REQUIRED)==REQUIRED
        row={'line':line_number,'cpu':int(cpu),'address':hex(address),'value':hex(value),
            'held':hex(held),'allowed':hex(allowed),'running':hex(running),'control_mask_gate':gate}
        writes.append(row)
        if address==0x20068008:last_enable=row
        if gate!=last:transitions.append(row);last=gate
    require(writes and any(t['control_mask_gate'] for t in transitions),'Trace never reached the proven CW running mask')
    final=json.loads((case/'result.json').read_text(encoding='utf-8'))['final']
    require(not writes[-1]['control_mask_gate'] and final['capturework']['reason']=='configuration'
        and final['capturework']['rejected']==0,'Final model gate/result evidence differs')
    out={'schema':1,'completed_control_replay':True,'original_result_sha256':digest(case/'result.json'),
        'trace_sha256':digest(trace),'trace_lines':line_number,'control_writes':len(writes),'observed_CPUs':sorted(cpus),
        'required_mask':hex(REQUIRED),'transitions':transitions,'final_masks':writes[-1],
        'last_running_enable_write':last_enable,'tail_control_writes':writes[-24:],
        'final_CW_completed':final['capturework']['completed'],'final_preview_batches':final['other_pipeline_counters']['preview-batches'],
        'final_application_index':final['application']['index'],'final_status_codes':final['firmware_status_codes'],
        'data_rejected_after_source_admission':False,
        'scope':'Frozen model control-mask gate only. Does not identify the original CPU reason for omitting restart writes.',
        'physical_hardware_semantics_proven':False,'firmware_or_device_state_modified':False,'camera_accessed':False,
        'source_sha256':{str(Path(__file__).resolve()):digest(Path(__file__)),str(model.resolve()):digest(model)}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(out,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in out.items() if k not in ('source_sha256','tail_control_writes')},ensure_ascii=False),flush=True)
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();analyze(args.case,args.output)
