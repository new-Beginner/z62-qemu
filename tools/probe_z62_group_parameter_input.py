"""r95 original-code observation with one explicit virtual group17 input.

The input is loaded into the existing parameter-storage window before CPU
execution. No original firmware/AF changes, post-boot RAM fixups, registers,
ready objects, callbacks or completion injections are supplied by this driver.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_capturework_original as original
import probe_z62_capturework_statistics_original as statistics
import probe_z62_group_parameter_origin as origin
import probe_z62_group_provider_context as provider
import run_z62_capture_group as hardware
import z62_original_clock_guard as clock
import z62_workspace_paths as paths
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,fixture,output,duration=8,wall_limit=300):
    qemu,card,group23,fixture,output=map(workspace,(qemu,card,group23,fixture,output))
    hardware.verify_build(qemu)
    meta=json.loads(fixture.with_name(fixture.name+'.json').read_text(encoding='utf-8'))
    require(digest(fixture)==meta['output_sha256'] and not meta['factory_calibration'] and
        meta['outside_declared_fields_unchanged'],'Explicit virtual input binding differs')
    before=original.snapshot;captures=[];next_capture=0;payloads={};clock_reads=[]
    sources=(Path(__file__),Path(clock.__file__),Path(origin.__file__),Path(provider.__file__),
        Path(statistics.__file__),Path(hardware.__file__))
    source_hashes={str(p):digest(p) for p in sources}
    def profile(command,group23,policy0=False):
        require(policy0,'Explicit external MAIN policy required')
        result=statistics.command_profile(command,group23,True,True)
        result+=['-global','nikon-z72-input-config.z62-capture-group=on',
            '-device',f'loader,file={paths.WorkspacePath(fixture)},addr=0x132c0000,force-raw=on']
        return result
    def snapshot(machine,layout):
        nonlocal next_capture
        if not clock_reads:clock_reads.extend(clock.wait_for_clock(machine))
        row=before(machine,layout)
        row['capture_group']=json.loads(machine.qmp.command('qom-get',{
            'path':'/machine/master-input','property':'capture-group-status'}))
        row['capturework_statistics']=json.loads(machine.qmp.command('qom-get',{
            'path':'/machine/master-input','property':'capturework-statistics-status'}))
        row['legacy_RAW_accepted']=machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'raw-accepted'})
        if row['capturework']['completed'] and row['capture_group']['committed'] and row['virtual_time_ns']>=next_capture and len(captures)<4:
            running=machine.qmp.command('query-status')['running']
            if running:machine.qmp.command('stop')
            try:
                captured=origin.capture(machine);blob=bytes.fromhex(captured['parameter_bytes_hex'])
                captured['legacy_58_is_not_coefficients']=captured.pop('coefficient_bytes_24_hex')
                captured['packed_coefficients_24_hex']=blob[0x3e:0x56].hex()
                captured['coefficient_argument']=hex(origin.BASE+0x3e)
                captured['group_curve_words']=machine._words(0x2006b880,65)
                captured['group_coefficient_words']=machine._words(0x2006b820,24)
                context=machine._words(provider.CONTEXT,12);pointer=context[6]
                captured['provider_context_words']=context;captured['provider_source']=hex(pointer)
                if 0xc0000000<=pointer<=0xe0000000-0x2c00 and not pointer&3:
                    if pointer not in payloads:
                        payload=provider.read_bytes(machine,pointer,0x2c00)
                        path=output/f'resource-source-{pointer:08x}.bin'
                        with path.open('xb') as handle:handle.write(payload)
                        payloads[pointer]={'path':path.name,'sha256':digest(path),'bytes':len(payload)}
                    captured['provider_source_file']=payloads[pointer]
                captured['virtual_time_ns']=row['virtual_time_ns'];captures.append(captured)
                row['group_parameter_input']=captured;next_capture=row['virtual_time_ns']+1_000_000_000
                print('GROUP_INPUT',meta['mode'],row['virtual_time_ns'],row['capture_group']['completed'],flush=True)
            finally:
                if running:machine.qmp.command('cont')
        return row
    with (patch.object(original,'snapshot',snapshot),patch.object(original,'command_profile',profile),
            patch.object(original,'VERSION','2026.11.04-group-parameter-input-r95')):
        result=original.run(qemu,card,group23,output,duration,wall_limit,True)
    require(all(digest(Path(name))==sha for name,sha in source_hashes.items()),'Input experiment driver changed')
    receipt={'schema':1,'version':'2026.11.04-group-parameter-input-r95','kernel_version':'2026.11.04-r93',
        'result_sha256':digest(output/'result.json'),'fixture_manifest':meta,'fixture_sha256':digest(fixture),
        'source_sha256':source_hashes,'captures':captures,'clock_reads':clock_reads,
        'explicit_preboot_parameter_input':True,'parameter_storage_address':hex(0x132c0000),
        'post_boot_software_RAM_or_register_fixups':False,'ready_or_completion_injected':False,
        'debug_stop_timing_perturbed':True,'functional_acceptance_eligible':False,
        'factory_calibration':False,'camera_accessed':False}
    with (output/'parameter-input.json').open('x',encoding='utf-8') as handle:json.dump(receipt,handle,ensure_ascii=False,indent=2)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=8);parser.add_argument('--wall-limit',type=float,default=300)
    args=parser.parse_args();result,receipt=run(args.qemu,args.card,args.group23,args.fixture,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and result.get('process_exit_code')==0 and
        not result.get('failure') and receipt['captures'] else 1)
