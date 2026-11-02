"""Verify read-timeout recovery against the frozen real QEMU, without firmware."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time
from probe_reference_devices import free_port
from run_z62_preview import DEFAULT_QEMU, verify_build
from z62_qmp_transport import QmpClient, identity


def run(output):
    build=verify_build(DEFAULT_QEMU.resolve())
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as result_file:
        record={'completed':False,'firmware_loaded':False,'camera_accessed':False,
                'qemu_sha256':build['binary_sha256'],'transport':identity()}
        port=free_port()
        command=[str(DEFAULT_QEMU.resolve()),'-M','none','-nodefaults','-display','none','-S',
                 '-qmp',f'tcp:127.0.0.1:{port},server=on,wait=off']
        process=client=None
        with tempfile.TemporaryFile() as log:
            try:
                process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=log)
                record['pid']=process.pid
                deadline=time.monotonic()+20
                while True:
                    try:
                        client=QmpClient(port)
                        break
                    except ConnectionRefusedError:
                        if process.poll() is not None or time.monotonic()>=deadline:
                            raise
                        time.sleep(.05)
                # Deterministic host read failure; the real QEMU still receives
                # exactly one request and leaves its reply on the same TCP link.
                # A nanosecond deadline is not deterministic on coarse clocks.
                original_socket=client.sock
                class OneReadTimeout:
                    def __getattr__(self,name): return getattr(original_socket,name)
                    def recv(self,size): raise TimeoutError('injected host read timeout')
                client.sock=OneReadTimeout()
                try:
                    try:
                        client.command('query-status')
                        raise RuntimeError('Host timeout control was not exercised')
                    except TimeoutError:
                        record['read_timeout_observed']=True
                        record['timeout_control']='one host recv failure; actual QEMU reply retained in TCP'
                finally:
                    client.sock=original_socket
                version=client.command('query-version')
                status=client.command('query-status')
                if version['qemu']['major']!=10 or status['running'] is not False:
                    raise ValueError('Late reply was misattributed')
                record.update(version=version,status=status,diagnostics=client.diagnostics())
                if client.late_replies!=1 or client.timed_out_requests!=1 or client.closed:
                    raise ValueError('Unexpected recovery counters or closed connection')
                client.command('quit')
                process.wait(timeout=10)
                record['exit_code']=process.returncode
                record['completed']=process.returncode==0
            except Exception as exc:
                record['failure']={'type':type(exc).__name__,'message':str(exc)}
            finally:
                if client is not None and process is not None and process.poll() is None:
                    try:
                        client.command('quit')
                        process.wait(timeout=10)
                    except (OSError,RuntimeError,ValueError,subprocess.TimeoutExpired):
                        pass
                if client is not None: client.close()
                if process is not None and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
                    record['forced_cleanup']=True
                    record['completed']=False
                record['process_closed']=process is None or process.poll() is not None
                log.seek(0)
                record['stderr']=log.read().decode(errors='replace')[-2000:]
                json.dump(record,result_file,indent=2)
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=run(args.output)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['completed'] else 1)
