"""r103b bounded original run without a GDB attachment, coherent scalar reads.

Two brief explicit QMP pauses preserve per-batch DMA snapshots. This is not a
claim of unperturbed physical timing or complete camera functionality.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_readout_statistics_original as parent
from record_z62_action_evidence import workspace,digest,require


class NoDebugger:
    def __init__(self,binary):
        self.remote=None
        self.record={'schema':1,'version':'2026.11.04-no-debugger-r103b',
            'enabled':False,'attached':False,'waits':[],'callbacks':[],
            'guest_memory_written':False,'guest_registers_written':False,
            'inferior_calls':False,'completion_or_ready_injected':False,'camera_accessed':False}
    def tick(self,machine,layout):pass
    def close(self):pass


def run(qemu,card,group23,fixture,output,duration=24,wall_limit=600):
    output=workspace(output);stream=parent.parent.finite.parent;previous=stream.original.snapshot
    frames=[];seen=set();sources={str(Path(p)):digest(Path(p)) for p in (__file__,parent.__file__)}
    def stats(machine):
        return json.loads(machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'input-readout-statistics-status'}))
    def snapshot(machine,layout):
        row=previous(machine,layout);state=stats(machine)
        reason=machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'finite-reason'})
        if state['batches'] and state['batch_publication'] and state['finite_frames'] and reason=='success' and state['batches'] not in seen and len(frames)<4:
            running=machine.qmp.command('query-status')['running']
            if running:machine.qmp.command('stop')
            try:
                require(not machine.qmp.command('query-status')['running'],'Scalar capture did not stop own VM')
                state=stats(machine);descriptor=machine._words(0x2006a53c,6);bank=descriptor[0]&1
                destination=machine._words(0x2006a550+16*bank,1)[0]
                require(descriptor[3]==60,'Only declared finite61 snapshots are captured')
                if state['batches'] not in seen:
                    path=output/f'scalar-no-debug-{len(frames)+1}.scalar'
                    data=stream.original.read_physical(machine,destination,768)
                    with path.open('xb') as handle:handle.write(data)
                    frames.append({'source':state,'descriptor_words':descriptor,'destination':hex(destination),
                        'scalar_path':path.name,'scalar_sha256':digest(path),'VM_stopped_for_coherent_read':True})
                    seen.add(state['batches'])
            finally:
                if running:machine.qmp.command('cont')
        return row
    with (patch.object(parent.parent,'ReadoutWaitObserver',NoDebugger),patch.object(stream.original,'snapshot',snapshot)):
        result,prior=parent.run(qemu,card,group23,fixture,output,duration,wall_limit)
    require(all(digest(Path(p))==sha for p,sha in sources.items()),'No-debugger wrapper changed')
    require(result['ready_observer']['attached'] is False,'Unexpected GDB attachment')
    receipt={'schema':1,'version':'2026.11.04-readout-statistics-no-debugger-r103b',
        'result_sha256':digest(output/'result.json'),'source_sha256':sources,'scalar_DMA_snapshots':frames,
        'GDB_attached':False,'QMP_scalar_capture_pauses':len(frames),'observation_timing_perturbed':bool(frames),
        'camera_accessed':False,'firmware_software_or_ready_modified':False}
    with (output/'no-debugger-statistics.json').open('x',encoding='utf-8') as handle:
        json.dump(receipt,handle,ensure_ascii=False,indent=2)
    print(json.dumps({'scalar_DMA_snapshots':len(frames),'GDB_attached':False,
        'completed_observation':result['completed_observation']}),flush=True)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=parent.hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=24);parser.add_argument('--wall-limit',type=float,default=600)
    args=parser.parse_args();result,receipt=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and result.get('process_exit_code')==0 else 1)
