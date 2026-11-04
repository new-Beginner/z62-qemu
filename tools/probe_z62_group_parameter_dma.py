"""r95b retain actual original-window group DMA, with coherent source identity."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_group_parameter_input as parent
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,fixture,output,duration=8,wall_limit=300):
    qemu,card,group23,fixture,output=map(workspace,(qemu,card,group23,fixture,output))
    previous=parent.origin.capture;saved=[];seen=set();before=digest(Path(__file__))
    def capture(machine):
        running=machine.qmp.command('query-status')['running']
        if running:machine.qmp.command('stop')
        try:
            result=previous(machine)
            state=json.loads(machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'capture-group-status'}))
            publication=state['publication']
            if state['completed'] and publication not in seen:
                outputs=[]
                for family,(address,size) in enumerate(zip(state['addresses'],state['sizes'])):
                    if not size:continue
                    data=parent.original.read_physical(machine,address,size)
                    path=output/f'group-publication-{publication}-family-{family}.dat'
                    with path.open('xb') as handle:handle.write(data)
                    outputs.append({'family':family,'path':path.name,'address':hex(address),'bytes':size,'sha256':digest(path)})
                frame={'source':state,'outputs':outputs,'VM_stopped_for_coherent_DMA_read':True}
                saved.append(frame);seen.add(publication);result['actual_group_DMA']=frame
            return result
        finally:
            if running:machine.qmp.command('cont')
    with patch.object(parent.origin,'capture',capture):result,receipt=parent.run(qemu,card,group23,fixture,output,duration,wall_limit)
    require(digest(Path(__file__))==before,'Original DMA observer changed')
    summary={'schema':1,'version':'2026.11.04-group-parameter-dma-r95b',
        'result_sha256':digest(output/'result.json'),'input_receipt_sha256':digest(output/'parameter-input.json'),
        'frames':saved,'source_sha256':{str(Path(__file__)):before},'camera_accessed':False,
        'guest_software_state_written':False,'physical_AF_or_ISP_equivalence':False}
    with (output/'parameter-dma.json').open('x',encoding='utf-8') as handle:json.dump(summary,handle,ensure_ascii=False,indent=2)
    return result,summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=parent.hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=8);parser.add_argument('--wall-limit',type=float,default=300)
    args=parser.parse_args();result,summary=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and
        result.get('process_exit_code')==0 and summary['frames'] else 1)
