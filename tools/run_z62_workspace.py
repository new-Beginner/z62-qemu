"""Launch existing Z62 profiles with all task outputs physically in this workspace."""
import argparse
from contextlib import ExitStack
import importlib
import inspect
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.11.03-workspace-storage-r73'


def alias_drive():
    alias=Path('Q:/')
    if alias.exists():
        if not alias.samefile(ROOT):
            raise ValueError('Q: is occupied by another location; choose a free ASCII workspace alias')
    else:
        result=subprocess.run(['subst.exe','Q:',str(ROOT)],capture_output=True)
        if result.returncode or not alias.is_dir() or not alias.samefile(ROOT):
            raise ValueError('Could not create a workspace-only ASCII access alias')
    return alias


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    parser=argparse.ArgumentParser(description=__doc__,add_help=False)
    parser.add_argument('--entry',default='run_z62_paired_diagnostic_console')
    parser.add_argument('--help',action='store_true')
    parser.add_argument('--storage-check',action='store_true')
    parser.add_argument('--native-host-check',type=Path)
    parser.add_argument('--native-persistent-fault-check',type=Path)
    own,rest=parser.parse_known_args(argv)
    if own.help:
        parser.print_help(); return
    if '--version' in rest:
        print(VERSION); return
    if not re.fullmatch(r'run_z62_[a-z0-9_]+|run_reference_console|z72_latest_reference',own.entry) or not (ROOT/'tools'/(own.entry+'.py')).is_file():
        raise ValueError('Choose an existing Z62 project entry')
    alias=alias_drive(); runtime=ROOT/'.runtime'
    for name in ('sessions','tmp','cache/pip','cache/uv','java-home','appdata','local-appdata'):
        (runtime/name).mkdir(parents=True,exist_ok=True)
    environment={'Z62_PROJECT_ROOT':str(ROOT),'Z62_PROJECT_DRIVE':str(alias),
        'TEMP':str(alias/'.runtime/tmp'),'TMP':str(alias/'.runtime/tmp'),
        'PI_SCRATCH_DIR':str(alias/'.runtime/tmp'),
        'Z62_RUNTIME_ROOT':str(alias/'.runtime/migrated/c-runtime'),
        'PYTHONDONTWRITEBYTECODE':'1','PIP_CACHE_DIR':str(alias/'.runtime/cache/pip'),
        'UV_CACHE_DIR':str(alias/'.runtime/cache/uv'),
        'APPDATA':str(alias/'.runtime/appdata'),'LOCALAPPDATA':str(alias/'.runtime/local-appdata')}
    java_options=os.environ.get('JAVA_TOOL_OPTIONS','')
    environment['JAVA_TOOL_OPTIONS']=(java_options+' -Djava.io.tmpdir='+str(alias/'.runtime/tmp')+
                                      ' -Duser.home='+str(alias/'.runtime/java-home')).strip()
    if shutil.disk_usage(runtime).free<6*1024**3 and not own.storage_check:
        raise ValueError('Need 6 GiB free in workspace before staging the SD snapshot')
    with patch.dict(os.environ,environment),patch.object(tempfile,'gettempdir',lambda:environment['TEMP']):
        import z62_workspace_paths as paths
        import z62_workspace_console as host_paths
        import z62_virtual_sd as virtual_sd
        import z62_host_timeout_capture as host_capture
        import run_reference_console as reference
        paths.ensure_alias()
        if own.storage_check:
            print(json.dumps({'workspace':str(ROOT),'alias':str(alias),'same_physical_directory':alias.samefile(ROOT),
                'temporary_directory':tempfile.gettempdir(),'runtime_directory':str(runtime),
                'fixture_exists':paths.WorkspacePath(paths.OLD_RUNTIME/'fixtures/group23.bin').is_file(),
                'workspace_free':shutil.disk_usage(runtime).free},ensure_ascii=False),flush=True)
            return
        original_run=runpy.run_path
        def execute(path,*args,**kwargs):
            selected=Path(path).absolute()
            if selected.name in ('z62_console.py','web_console.py') and selected.parent.name=='tools' and selected.parent.parent.name=='source':
                host_paths.apply_console(selected.parent.parent)
            return original_run(path,*args,**kwargs)
        module=importlib.import_module(own.entry)
        if own.native_host_check or own.native_persistent_fault_check:
            import probe_z62_host_timeout_capture as native
            import run_z62_output_lineage as hardware
            with ExitStack() as stack:
                stack.enter_context(patch.object(host_capture,'Path',paths.WorkspacePath))
                for name,loaded in tuple(sys.modules.items()):
                    if name.startswith('probe_z62') and hasattr(loaded,'Path'):
                        stack.enter_context(patch.object(loaded,'Path',paths.WorkspacePath))
                if own.native_persistent_fault_check:
                    import probe_z62_persistent_fault as fault
                    import z62_persistent_diagnostic_console as persistent
                    stack.enter_context(patch.object(persistent,'Path',paths.WorkspacePath))
                    fault.check(paths.WorkspacePath(own.native_persistent_fault_check),
                                paths.WorkspacePath(hardware.DEFAULT_QEMU))
                    return
                output=paths.WorkspacePath(own.native_host_check).absolute(); output.mkdir(parents=True,exist_ok=False)
                try:
                    record=native.check(output,paths.WorkspacePath(hardware.DEFAULT_QEMU))
                except Exception as exc:
                    with (output/'workspace-host-failure.json').open('x',encoding='utf-8') as handle:
                        json.dump({'completed':False,'failure':{'type':type(exc).__name__,
                                  'message':str(exc)},'workspace_storage':True},handle,indent=2)
                    raise
                record.update(workspace_storage=True,workspace=str(ROOT),alias=str(alias))
                with (output/'workspace-host-check.json').open('x',encoding='utf-8') as handle:
                    json.dump(record,handle,indent=2)
                print(json.dumps({'completed':record['completed'],'workspace_storage':True,
                    'qmp_after_detach':record['qmp_still_responds_after_detach'],'process_closed':record['process_closed']}),flush=True)
            return
        if own.entry in ('run_z62_paired_console','run_z62_paired_diagnostic_console','run_z62_paired_managed_console',
                         'run_z62_persistent_diagnostic_console','run_z62_committed_photo_console',
                         'run_z62_action_queue_console'):
            if '--group23-fixture' not in rest and not any(s.startswith('--group23-fixture=') for s in rest):
                rest+=['--group23-fixture',str(alias/'.runtime/migrated/c-runtime/fixtures/group23.bin')]
            if '--sd-card' not in rest and not any(s.startswith('--sd-card=') for s in rest):
                rest+=['--sd-card',str(alias/'.runtime/migrated/c-runtime/fixtures/card-r22-4096.raw')]
        if own.entry=='run_z62_paired_managed_console':
            rest+=['--scratch-root',str(alias/'.runtime/tmp')]
        with patch.object(virtual_sd,'Path',paths.WorkspacePath),patch.object(host_capture,'Path',paths.WorkspacePath), \
             patch.object(reference,'Path',paths.WorkspacePath), \
             patch.object(runpy,'run_path',execute),patch.object(sys,'argv',[str(ROOT/'tools'/(own.entry+'.py'))]+rest):
            if 'argv' in inspect.signature(module.main).parameters:
                module.main(rest)
            else:
                module.main()


if __name__=='__main__':
    main()
