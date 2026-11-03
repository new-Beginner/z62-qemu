"""Real QEMU policy0 checks with the original nonzero shared9530 value."""
import argparse
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import probe_z62_capturework_device as native
import run_z62_capturework_policy as hardware
from record_z62_action_evidence import workspace,digest,require


def check(qemu,state_path,output):
    qemu,state_path,output=map(workspace,(qemu,state_path,output))
    require(not output.exists(),'Use a new native policy result')
    output.parent.mkdir(parents=True,exist_ok=True)
    result={'schema':1,'completed':False,'firmware_executed':False,'synthetic_ARM_loops_only':True,
        'camera_accessed':False,'artifact_root':str(output.parent),'QEMU_binary_sha256':digest(qemu),
        'state_sha256':digest(state_path),'source_sha256':{str(path):digest(path) for path in
            (Path(__file__),Path(native.__file__),Path(hardware.__file__))}}
    try:
        help_result=subprocess.run([str(qemu),'-device','nikon-z72-input-config,help'],
            capture_output=True,text=True,timeout=20)
        require(help_result.returncode==0 and 'z62-capturework-policy0' in help_result.stdout+help_result.stderr,
            'Missing explicit external MAIN policy0 property')
        build=hardware.verify_build(qemu)
        result['policy_build_version']=build['version']
        dims,bits,stride,lut=native.profile(json.loads(state_path.read_text(encoding='utf-8')))
        old_config=native.configure
        def configure(session,*args,**kwargs):
            value=old_config(session,*args,**kwargs)
            session.write(0x20069530,0x200040); session.write(0x20068104,0x80)
            return value
        # The finite r89 recipe remains strict when policy0 is not selected.
        with native.session(qemu,True,result) as session:
            configure(session,dims,bits,stride,lut); native.fill(session,stride*dims[5])
            native.upload(session,dims,1); native.idle(session)
            require(native.status(session)['completed']==0 and native.status(session)['reason']=='configuration',
                'Policy default-off accepted the nonzero physical source word')
            require(session.read(native.raw.SLOTS[0],stride*dims[5])==b'\xa5'*(stride*dims[5]) and
                native.status(session)['pending_front']==0 and native.status(session)['pending_raw']==0,
                'Rejected policy changed pixels or completion state')
        result['default_policy_off_preserves_strict_recipe']=True
        original=subprocess.Popen
        class PolicyPopen(original):
            def __init__(self,command,*args,**kwargs):
                command=list(command)
                if '-M' in command and 'nikon-z72-input-config.z62-capturework=on' in command:
                    command+=['-global','nikon-z72-input-config.z62-capturework-policy0=on']
                super().__init__(command,*args,**kwargs)
        with patch.object(native,'configure',configure),patch.object(native.subprocess,'Popen',PolicyPopen):
            native.check(qemu,state_path,result)
        require(all(row['device_state']['external_main_policy0'] and
            row['device_state']['output_shared_source_word']==0x200040 for row in result['frames']),
            'Output did not preserve the committed nonzero shared-source provenance')
        # Other nonzero words remain unqualified even with the explicit policy.
        with patch.object(native.subprocess,'Popen',PolicyPopen),native.session(qemu,True,result) as session:
            configure(session,dims,bits,stride,lut)
            session.write(0x20069530,0x200041); session.write(0x20068104,0x80)
            native.fill(session,stride*dims[5]); native.upload(session,dims,1); native.idle(session)
            require(native.status(session)['completed']==0,'Unknown physical source selection was accepted')
            require(session.read(native.raw.SLOTS[0],stride*dims[5])==b'\xa5'*(stride*dims[5]) and
                native.status(session)['pending_front']==0 and native.status(session)['pending_raw']==0,
                'Unknown shared selection wrote pixels or completion')
        result['unknown_shared_source_word_rejected']=True
        require(all(code==0 for code in result['process_exit_codes']),'Policy native child did not close cleanly')
        require(all(digest(Path(path))==expected for path,expected in result['source_sha256'].items()),'Policy test source changed')
        result['completed']=True
    except Exception as exc: result['failure']={'type':type(exc).__name__,'message':str(exc)}
    with output.open('x',encoding='utf-8') as handle: json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({key:result.get(key) for key in ('completed','failure','QEMU_binary_sha256',
        'default_policy_off_preserves_strict_recipe','unknown_shared_source_word_rejected',
        'actual_pixels_checked','process_exit_codes')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--state',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); result=check(args.qemu,args.state,args.output)
    raise SystemExit(0 if result['completed'] else 1)
