"""r94c passive reads of the independently recovered Z62 provider context."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from unittest.mock import patch
import probe_z62_group_parameter_layout as parent
from record_z62_action_evidence import workspace,digest,require

CONTEXT=0xc21835d4
SLOT=0xc1861ef0


def read_bytes(machine,address,size):
    require(not address&3 and not size&3,'Aligned bounded provider read required')
    out=bytearray()
    for offset in range(0,size,256):
        length=min(256,size-offset)
        out.extend(struct.pack('<'+'I'*(length//4),*machine._words(address+offset,length//4)))
    return bytes(out)


def run(qemu,card,group23,output,duration=8,wall_limit=300):
    qemu,card,group23,output=map(workspace,(qemu,card,group23,output))
    origin=parent.parent;before_capture=origin.capture;source_hash=digest(Path(__file__));payloads={}
    def capture(machine):
        running=machine.qmp.command('query-status')['running']
        if running:machine.qmp.command('stop')
        try:
            result=before_capture(machine)
            words=machine._words(CONTEXT,12);slot=machine._words(SLOT,1)[0];pointer=words[6]
            result['provider_context']={'literal_context':hex(CONTEXT),'published_context_slot':hex(SLOT),
                'slot_value':hex(slot),'context_words':words,'resource_pointer_at_18':hex(pointer)}
            if pointer and not pointer&3 and (0xc0000000<=pointer<=0xe0000000-0x2c00 or
                    0x13200000<=pointer<=0x14000000-0x2c00):
                if pointer not in payloads:
                    raw=read_bytes(machine,pointer,0x2c00)
                    path=output/f'provider-{pointer:08x}-first.bin'
                    with path.open('xb') as handle:handle.write(raw)
                    payloads[pointer]={'path':path.name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
                        'all_zero':not any(raw),'capture_scope':'bounded source span consumed by provider; resource identity pending'}
                result['provider_context']['source_first_capture']=payloads[pointer]
            return result
        finally:
            if running:machine.qmp.command('cont')
    with patch.object(origin,'capture',capture):
        result,receipt=parent.run(qemu,card,group23,output,duration,wall_limit)
    require(digest(Path(__file__))==source_hash,'Provider-context observer changed')
    summary={'schema':1,'version':'2026.11.04-group-provider-context-r94c',
        'result_sha256':digest(output/'result.json'),'layout_sha256':digest(output/'parameter-layout.json'),
        'source_sha256':{str(Path(__file__)):source_hash},'camera_accessed':False,
        'guest_memory_or_registers_written':False,'parameters_replaced':False,'payloads':payloads}
    with (output/'provider-context.json').open('x',encoding='utf-8') as handle:json.dump(summary,handle,ensure_ascii=False,indent=2)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=parent.parent.hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--duration',type=float,default=8)
    parser.add_argument('--wall-limit',type=float,default=300);args=parser.parse_args()
    result,receipt=run(args.qemu,args.card,args.group23,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and
        result.get('process_exit_code')==0 and receipt['observations'] else 1)
