"""r98b preserve actual scalar DMA and its retained encoded CW source."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_finite_main_stream as parent
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,fixture,output,duration=16,wall_limit=480):
    qemu,card,group23,fixture,output=map(workspace,(qemu,card,group23,fixture,output))
    base=parent.parent.original;previous=base.snapshot;seen=set();saved=[];source_sha=digest(Path(__file__))
    def snapshot(machine,layout):
        row=previous(machine,layout)
        status=json.loads(machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'capturework-finite-status'}))
        reason=machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'finite-reason'})
        key=(status['batches_prepared'],status['batch_source_serial'])
        if status['finite_frames'] and reason=='success' and key not in seen and len(saved)<4:
            running=machine.qmp.command('query-status')['running']
            if running:machine.qmp.command('stop')
            try:
                status=json.loads(machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'capturework-finite-status'}))
                cw=json.loads(machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'capturework-status'}))
                key=(status['batches_prepared'],status['batch_source_serial'])
                descriptor=machine._words(0x2006a53c,6);bank=descriptor[0]&1
                destination=machine._words(0x2006a550+16*bank,1)[0]
                require(descriptor[3]==60,'Only source-declared finite61 payloads are captured')
                if key not in seen and cw['publication']==status['batch_publication']==status['latest_publication'] and cw['epoch']==status['batch_epoch']:
                    ordinal=len(saved)+1;raw_path=output/f'finite-{ordinal}-retained.p12';scalar_path=output/f'finite-{ordinal}.scalar'
                    raw=base.read_physical(machine,status['source_address'],cw['height']*cw['stride'])
                    scalar=base.read_physical(machine,destination,768)
                    for path,data in ((raw_path,raw),(scalar_path,scalar)):
                        with path.open('xb') as handle:handle.write(data)
                    frame={'source':status,'CW_output':cw,'descriptor_words':descriptor,'destination':hex(destination),
                        'RAW_path':raw_path.name,'RAW_sha256':digest(raw_path),'scalar_path':scalar_path.name,
                        'scalar_sha256':digest(scalar_path),'VM_stopped_for_coherent_read':True}
                    saved.append(frame);seen.add(key);row['finite_retained_DMA']=frame
            finally:
                if running:machine.qmp.command('cont')
        return row
    with patch.object(base,'snapshot',snapshot):result=parent.run(qemu,card,group23,fixture,output,duration,wall_limit)
    require(digest(Path(__file__))==source_sha,'Retained DMA observer changed')
    receipt={'schema':1,'version':'2026.11.04-retained-finite-dma-r98b','result_sha256':digest(output/'result.json'),
        'finite_stream_sha256':digest(output/'finite-stream.json'),'frames':saved,
        'source_sha256':{str(Path(__file__)):source_sha},'camera_accessed':False,
        'finite_samples_are_not_new_RAW_acquisitions':True,'debug_stop_timing_perturbed':True}
    with (output/'retained-dma.json').open('x',encoding='utf-8') as handle:json.dump(receipt,handle,ensure_ascii=False,indent=2)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=parent.hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=16);parser.add_argument('--wall-limit',type=float,default=480);args=parser.parse_args()
    result,receipt=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and
        result.get('process_exit_code')==0 and receipt['frames'] else 1)
