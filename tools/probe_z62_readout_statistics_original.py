"""Original C1.70 with explicit C readout-derived finite statistics and DMA snapshots."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_input_readout_original as parent
import run_z62_readout_statistics as hardware
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,fixture,output,duration=16,wall_limit=480):
    qemu,output=map(workspace,(qemu,output));hardware.verify_build(qemu)
    stream=parent.finite.parent;previous_snapshot=stream.original.snapshot
    previous_configure=stream.input_driver.statistics.command_profile;frames=[];seen=set()
    sources={str(Path(p)):digest(Path(p)) for p in (__file__,hardware.__file__,parent.__file__)}
    def configure(*args,**kwargs):
        return previous_configure(*args,**kwargs)+['-global','nikon-z72-input-config.z62-readout-statistics=on']
    def stats(machine):
        return json.loads(machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'input-readout-statistics-status'}))
    def capture(machine):
        state=stats(machine)
        reason=machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'finite-reason'})
        if state['batches'] and state['batch_publication'] and state['finite_frames'] and reason=='success' and state['batches'] not in seen and len(frames)<4:
            descriptor=machine._words(0x2006a53c,6);bank=descriptor[0]&1
            destination=machine._words(0x2006a550+16*bank,1)[0]
            require(descriptor[3]==60,'Only declared finite61 snapshots are captured')
            path=output/f'finite-{len(frames)+1}.scalar'
            data=stream.original.read_physical(machine,destination,768)
            with path.open('xb') as handle:handle.write(data)
            saved={'source':state,'descriptor_words':descriptor,'destination':hex(destination),
                'scalar_path':path.name,'scalar_sha256':digest(path),
                'VM_stopped_at_original_ready_callback':True,'capture_pc':'0x102392fc'}
            frames.append(saved);seen.add(state['batches'])
    class DataWaitObserver(parent.ReadoutWaitObserver):
        def resume(self):
            if not getattr(self,'data_point_installed',False):
                pc=0x102392fc;image=Path(self.machine.args.master).read_bytes()
                expected=image[pc-0x10020000:pc-0x10020000+4]
                require(self.remote.read(pc,4)==expected,'Original finite-ready anchor differs')
                self.record['live_anchors'].append({'pc':hex(pc),'bytes':expected.hex(),'mode':'Thumb'})
                self.record['additional_data_breakpoint']=hex(pc);self.data_point_installed=True
            self.arm(0x102392fc)
            super().resume()
        def registers(self):
            r=super().registers()
            if r['pc']==0x102392fc:capture(self.machine)
            return r
    def snapshot(machine,layout):
        row=previous_snapshot(machine,layout);row['readout_statistics']=stats(machine)
        return row
    with (patch.object(stream.input_driver.statistics,'command_profile',configure),
            patch.object(stream.original,'snapshot',snapshot),patch.object(parent,'ReadoutWaitObserver',DataWaitObserver)):
        result,route=parent.run(qemu,card,group23,fixture,output,duration,wall_limit)
    require(all(digest(Path(p))==sha for p,sha in sources.items()),'Original statistics wrapper changed')
    receipt={'schema':1,'version':'2026.11.04-readout-statistics-original-r103',
        'result_sha256':digest(output/'result.json'),'source_route_receipt_sha256':digest(output/'input-readout-stream.json'),
        'source_sha256':sources,'scalar_DMA_snapshots':frames,'camera_accessed':False,
        'statistics_source':'completed C readout MAIN view','new_RAW_acquisitions':False,
        'firmware_software_or_ready_modified':False,'functional_acceptance_eligible':False}
    with (output/'readout-statistics-stream.json').open('x',encoding='utf-8') as handle:
        json.dump(receipt,handle,ensure_ascii=False,indent=2)
    print(json.dumps({'scalar_DMA_snapshots':len(frames),'completed_observation':result['completed_observation']}),flush=True)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=16);parser.add_argument('--wall-limit',type=float,default=480)
    args=parser.parse_args();result,receipt=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and result.get('process_exit_code')==0 else 1)
