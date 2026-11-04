"""Independent original stop-wait result, source counter and source-binding checks."""
import argparse
import json
from pathlib import Path
from record_z62_action_evidence import workspace,digest,require
from z62_kernel_event_layout import contract
import run_z62_capturework_finite as hardware


def verify(result_path,output):
    result_path,output=map(workspace,(result_path,output));require(not output.exists(),'Use new stop-wait verifier result')
    record=json.loads(result_path.read_text(encoding='utf-8'));obs=record['ready_observer']
    require(record['completed_observation'] and record['process_exit_code']==0 and not record.get('failure')
        and not record.get('cleanup_failure') and record['source_bytes_unchanged'] and record['original_card_unchanged'],
        'Original stop-wait run did not close with original sources/card')
    require(obs.get('detach')=='OK' and len(obs['waits'])==2 and not obs.get('scope_limit_reached'),
        'Original two stop waits not observed and detached')
    require(not obs['guest_memory_written'] and not obs['guest_registers_written'] and
        not obs['inferior_calls'] and not obs['completion_or_ready_injected'],'Observer changed original state')
    image_path=Path(record['session'])/'inputs/master.bin';image=image_path.read_bytes();contract(image)
    require(digest(image_path)==record['master_sha256'],'Original image identity changed')
    build=hardware.verify_build();require(build['binary_sha256']==record['binary_sha256'],'Frozen r98 kernel changed')
    for anchor in obs['live_anchors']:
        pc=int(anchor['pc'],16);require(image[pc-0x10020000:pc-0x10020000+4]==bytes.fromhex(anchor['bytes']),
            'Live original anchor changed')
    outcomes=[]
    for index,wait in enumerate(obs['waits']):
        returned=wait['return'];kernel=wait['kernel_result'];entry=wait['kernel_entry'] if 'kernel_entry' in wait else None
        require(wait['registers']['r0']==0xc18a7634 and wait['registers']['r1']==0x800 and wait['timeout_argument']==100,
            'Wrong original stop event/mask/limit')
        require(wait['thread']==returned['thread']==kernel['thread'] and returned['registers']['sp']==wait['registers']['sp']
            and kernel['registers']['sp']==wait['registers']['sp']-16,'Wait raw/boolean return frame differs')
        require(kernel['registers']['r0']==(0 if index==0 else 0xffce0000) and returned['registers']['r0']==(1 if index==0 else 0),
            'Original kernel/boolean outcome differs')
        require((int(wait['event']['pattern'],16)&0x800)!=0 if index==0 else not int(wait['event']['pattern'],16)&0x800,
            'Original event predicate at call differs')
        if index==0:require(returned['output_bits']&0x800,'Success omitted requested original event bit')
        for hit in (wait,kernel,returned):
            sensor=hit['sensor']
            require(sensor['functional-raw-completion'] and not sensor['laboratory-frame-completion'] and
                sensor['raw-source-events']==sensor['raw-completions']==sensor['frame-completions']==0 and sensor['init-completions']==1,
                'Observed sensor data/init source counters differ')
        if index==1:
            require(wait['sensor_config'][0]&0x11==0x11 and wait['sensor_mode_status_mask'][0]&0xc000==0x8000
                and wait['sensor_mode_status_mask'][2]&2 and wait['input_geometry']==[136<<16,2020<<16],
                'Original second sensor profile/mask/136-row phase differs')
        outcomes.append({'kernel_result':kernel['registers']['r0'],'boolean_result':returned['registers']['r0'],
            'output_bits':returned['output_bits'],'call_ns':wait['virtual_time_ns'],
            'duration_ns':returned['virtual_time_ns']-wait['virtual_time_ns'],
            'event_control_block':wait['event']['control_block'],'pattern':wait['event']['pattern']})
    require(all(s['sensor_source']['raw-source-events']==0 for s in record['samples']),'A source edge occurred outside wait snapshots')
    sources={str(Path(__file__)):digest(Path(__file__)),**record['source_sha256'],**obs['source_sha256']}
    for name in ('stop-wait-source.json','finite-stream.json'):
        receipt=json.loads((result_path.parent/name).read_text(encoding='utf-8'))
        require(receipt['result_sha256']==digest(result_path),'Wrapper belongs to another original run')
        sources.update(receipt['source_sha256'])
    fallback={}
    for name,sha in sources.items():
        path=Path(name)
        if not path.is_file() and path.name=='command.json':path=result_path.parent/'closed-command.json';fallback[name]=str(path)
        require(path.is_file() and digest(path)==sha,'Bound wait source changed: '+name)
    result={'schema':1,'completed_evidence_check':True,'original_result_sha256':digest(result_path),
        'binary_sha256':record['binary_sha256'],'original_waits':outcomes,
        'sensor_raw_source_events_always_zero':True,'sensor_initialization_completions':1,
        'second_wait_consumer_armed_in_mode2':True,'legacy_RAW_accepted_always_zero':all(s['legacy_RAW_accepted']==0 for s in record['samples']),
        'raw_kernel_failure_ffce0000_proven':True,'source_edges_in_observed_callback_window':len(obs['callbacks']),
        'original_code_or_AF_modified':False,'camera_accessed':False,'functional_acceptance_eligible':False,
        'source_sha256':sources,'saved_identical_command_fallbacks':fallback}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_sha256','saved_identical_command_fallbacks')}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();verify(args.result,args.output)
