"""Explicit transport-deadline fault on an owned firmware-free QEMU instance."""
import hashlib
import json
import os
from pathlib import Path as NativePath
import shutil
import socket
import subprocess
import tempfile
import time
from unittest.mock import patch

import run_z62_output_lineage as hardware
import z62_host_timeout_capture as host_capture
import z62_persistent_diagnostic_console as persistent
from z62_paired_diagnostic_console import ObservedQmp
from z62_workspace_paths import WorkspacePath,ROOT


def require(value,message):
    if not value:
        raise ValueError(message)


def check(output,binary):
    require(NativePath(tempfile.gettempdir()).resolve().is_relative_to(ROOT),
            'Use the workspace launcher before creating diagnostic temporary files')
    build=hardware.verify_build(binary)
    output=WorkspacePath(output).absolute(); output.mkdir(parents=True,exist_ok=False)
    work=output/'vm-scratch'; work.mkdir()
    result={'schema':1,'completed':False,'guest_firmware_executed':False,'camera_accessed':False,
        'scope':'deliberately shortened host QMP receive deadline; not a spontaneous runtime timeout',
        'injected_receive_deadline_seconds':0.000001,'functional_acceptance_eligible':False,
        'test_only_receive_delay_seconds':0.1,
        'production_monitor_timeout_changed':False,
        'qemu_sha256':build['binary_sha256']}
    process=client=None
    try:
        with host_capture.ascii_runtime(binary,build['binary_sha256']) as staged:
            with socket.socket() as reserve:
                reserve.bind(('127.0.0.1',0)); port=reserve.getsockname()[1]
            command=[str(staged['binary']),'-M','nikon-z62-dual-lab','-smp','4,maxcpus=5',
                '-display','none','-serial','none','-monitor','none','-nic','none','-S',
                '-qmp',f'tcp:127.0.0.1:{port},server=on,wait=off']
            with (work/'console.txt').open('xb') as console:
                process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=console)
            owner=object.__new__(persistent.PersistentDiagnosticMixin)
            owner.work=work; owner.process=process
            owner._diagnostic_timeout_events=[]; owner._diagnostic_capture_attempted=False
            owner._diagnostic_capture=None
            owner.diagnostic_profile={'runtime_binary':str(staged['binary']),
                'binary_sha256':build['binary_sha256'],'gdb':str(host_capture.DEFAULT_GDB)}
            owner.persistent_diagnostic_profile={'output_root':str(output/'permanent'),'workspace':str(ROOT)}
            deadline=time.monotonic()+20
            while client is None:
                require(process.poll() is None,'Owned native QEMU exited before monitor connection')
                try:
                    client=ObservedQmp(owner,port)
                except ConnectionRefusedError:
                    require(time.monotonic()<deadline,'Native monitor did not become ready'); time.sleep(.05)
            original_receive=client._receive
            delayed=False
            def receive_after_test_delay(deadline):
                nonlocal delayed
                if not delayed:
                    delayed=True
                    time.sleep(.1)
                return original_receive(deadline)
            with patch.object(client,'_receive',receive_after_test_delay):
                try:
                    client.command('query-status',timeout=0.000001)
                except TimeoutError:
                    result['injected_timeout_observed']=True
                else:
                    raise ValueError('The explicit test receive delay did not trigger a timeout')
            require(owner._diagnostic_capture and owner._diagnostic_capture['completed_capture'],
                    'The actual owned-process GDB capture failed')
            result['capture']=owner._diagnostic_capture
            reply=client.command('query-status')
            require(isinstance(reply,dict) and 'status' in reply,'QMP did not recover after actual GDB detach')
            require(client.diagnostics()['replayed_commands']==0,'A monitor control was replayed')
            result['monitor_after_detach']=client.diagnostics()
            client.command('quit'); process.wait(timeout=10); client.close()
            result['process_closed']=process.poll() is not None
            require(process.returncode==0,'Owned native QEMU did not close normally')
            require(NativePath(str(work)).resolve().is_relative_to(ROOT),'Cleanup escaped workspace')
            shutil.rmtree(work)
            log=output/'permanent/vm-scratch/first-timeout/host-gdb.txt'
            require(log.is_file() and hashlib.sha256(log.read_bytes()).hexdigest()==result['capture']['log_sha256'],
                    'The real stack did not survive VM cleanup')
            result.update(completed=True,vm_scratch_removed=not work.exists(),
                raw_stack_survives_cleanup=True,raw_stack=str(log),
                persisted_capture_file=(log.parent/'capture.json').is_file())
    except Exception as exc:
        result['failure']={'type':type(exc).__name__,'message':str(exc)}
    finally:
        if process is not None and process.poll() is None:
            try:
                if client is not None:
                    client.command('quit')
                process.wait(timeout=10)
            except Exception:
                host_capture.guard_owner(process,process.pid,process.args[0],build['binary_sha256'])
                process.kill(); process.wait(timeout=5)
        with (output/'result.json').open('x',encoding='utf-8') as handle:
            json.dump(result,handle,indent=2)
    print(json.dumps({k:result.get(k) for k in ('completed','injected_timeout_observed',
        'raw_stack_survives_cleanup','process_closed','failure')}),flush=True)
    require(result['completed'],'Persistent native fault test failed: '+str(result.get('failure')))
    return result
