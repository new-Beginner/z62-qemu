"""Original C1.70 plus explicit C inline readout input, separate from RAW DMA.

Extend the source scheduler with actual readout eligibility and route each
accepted packet to its real QOM port. No observed state or firmware condition
is rewritten. All source publications retain the existing byte-exact audit.
"""
import argparse
import json
from pathlib import Path
import struct
from unittest.mock import patch
import probe_z62_finite_main_stream as finite
import run_z62_input_readout as hardware
from z62_stop_wait_observer import StopWaitObserver,CALLBACK,PRODUCER
from z62_development_status import firmware_health
from record_z62_action_evidence import workspace,digest,require


class ReadoutWaitObserver(StopWaitObserver):
    def hit(self,label,registers,thread):
        row=super().hit(label,registers,thread)
        if label=='kernel-pattern-store':
            # One witnessed producer/store is enough. Keep the two true wait
            # pairs, rather than trapping every subsequent frame callback.
            self.disarm(CALLBACK);self.disarm(PRODUCER)
        return row


def run(qemu,card,group23,fixture,output,duration=16,wall_limit=480):
    qemu,output=map(workspace,(qemu,output));hardware.verify_build(qemu)
    stream=finite.parent;previous_run=stream.run;previous_snapshot=stream.original.snapshot
    previous_configure=stream.input_driver.statistics.command_profile;previous_cadence=stream.FrameCadence
    state={'machine':None,'qmp':None,'command':None};routes=[]
    sources={str(Path(p)):digest(Path(p)) for p in (__file__,hardware.__file__,finite.__file__,
        __import__('z62_stop_wait_observer').__file__)}
    def readout():
        machine=state['machine']
        if machine is None:return {'eligible':False,'pending':False}
        return json.loads(machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'input-readout-status'}))
    class Cadence(previous_cadence):
        def suggest(self,now,eligible=True):
            actual=readout()
            return super().suggest(now,eligible or (actual['eligible'] and not actual['pending']))
    def snapshot(machine,layout):
        if state['machine'] is None:
            state['machine']=machine;state['qmp']=machine.qmp;state['command']=machine.qmp.command
            def command(name,arguments=None,*args,**kwargs):
                actual_arguments=arguments
                if name=='qom-set' and arguments.get('path')=='/machine/master-input' and arguments.get('property')=='capturework-main-file':
                    current=json.loads(state['command']('qom-get',{'path':'/machine/master-input','property':'input-readout-status'}))
                    port='input-readout-file' if current['eligible'] else 'capturework-main-file'
                    actual_arguments=dict(arguments,property=port)
                    with Path(arguments['value']).open('rb') as handle:header=handle.read(96)
                    require(len(header)==96 and header[:4]==b'Z62M','Source packet header missing')
                    identity=struct.unpack_from('<4Q',header,32)
                    result=state['command'](name,actual_arguments,*args,**kwargs)
                    routes.append(dict(zip(('epoch','publication','frame','time_ns'),identity),port=port))
                    return result
                return state['command'](name,actual_arguments,*args,**kwargs)
            machine.qmp.command=command
        row=previous_snapshot(machine,layout);row.update(firmware_health(machine))
        row['input_readout']=readout();return row
    def configure(*args,**kwargs):
        return previous_configure(*args,**kwargs)+['-global','nikon-z72-input-config.z62-input-readout=on']
    def observed_run(qemu,card,group23,fixture,output,duration,wall_limit,observe,legacy_finite):
        return previous_run(qemu,card,group23,fixture,output,duration,wall_limit,True,legacy_finite)
    try:
        with (patch.object(stream,'FrameCadence',Cadence),patch.object(stream,'ReadyObserver',ReadoutWaitObserver),
                patch.object(stream,'run',observed_run),patch.object(stream.original,'snapshot',snapshot),
                patch.object(stream.input_driver.statistics,'command_profile',configure)):
            result=finite.run(qemu,card,group23,fixture,output,duration,wall_limit)
    finally:
        if state['qmp'] is not None:state['qmp'].command=state['command']
    require(all(digest(Path(p))==sha for p,sha in sources.items()),'Original C readout wrapper changed')
    require(len(routes)==result['accepted_publications'],'Source-port audit has missing accepted packets')
    receipt={'schema':1,'version':'2026.11.04-input-readout-original-r102','result_sha256':digest(output/'result.json'),
        'source_sha256':sources,'actual_accepted_source_routes':routes,'camera_accessed':False,
        'C_inline_readout':True,'physical_sensor_equivalence':False,'guest_RAW_DMA_from_readout':False,
        'firmware_software_or_ready_modified':False,'functional_acceptance_eligible':False}
    with (output/'input-readout-stream.json').open('x',encoding='utf-8') as handle:
        json.dump(receipt,handle,ensure_ascii=False,indent=2)
    print(json.dumps({'source_routes':len(routes),'inline_readout_publications':sum(r['port']=='input-readout-file' for r in routes)}),flush=True)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=16);parser.add_argument('--wall-limit',type=float,default=480)
    args=parser.parse_args();result,receipt=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and result.get('process_exit_code')==0 else 1)
