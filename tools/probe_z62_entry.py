"""Exercise the actual Windows CMD entry and its local HTTP status/stop paths."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]


def run(output,expected_version='2026.10.29-r8',diagnostic_key='finite_stats_status',firmware=None,python_entry=None,exercise_half_press=False,require_monitor_transport=False,
        expected_hardware_version=None, exercise_capture_input=False, *, before_stop=None, entry_args=()):
    output.mkdir(parents=True,exist_ok=False)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    url=f'http://127.0.0.1:{port}'
    def request(path,post=False,payload=None):
        req=Request(url+path,data=json.dumps(payload or {}).encode() if post else None,
                    headers={'Content-Type':'application/json'} if post else {})
        with urlopen(req,timeout=10) as response:
            body = response.read()
        if path == '/status':
            record['last_state'] = json.loads(body)
        return body
    record={'completed':False,'camera_accessed':False,'url':url,'entry':'start-z6ii-qemu.cmd',
            'expected_version':expected_version,'diagnostic_key':diagnostic_key,'candidate':firmware is not None}
    process=None
    with (output/'host.log').open('xb') as log:
        try:
            command=['cmd.exe','/c',str(ROOT/'start-z6ii-qemu.cmd'),'--port',str(port)]
            if python_entry is not None:
                python_entry=python_entry.resolve()
                if not python_entry.is_file() or not python_entry.is_relative_to(ROOT/'tools'):
                    raise ValueError('Python research entry must be a tool in this workspace')
                command=[sys.executable,'-X','utf8','-B',str(python_entry),
                         '--experimental-parameters','--capcom-sync','--functional-raw',
                         '--raw-completion','--capture-preset','init-mode','--no-auto-menu','--port',str(port)]
                record['entry']=str(python_entry.relative_to(ROOT))
            if firmware is not None: command+=['--firmware',str(firmware.resolve())]
            if not isinstance(entry_args, (list, tuple)) or any(not isinstance(value, str) for value in entry_args):
                raise ValueError('Entry arguments must be a sequence of strings')
            command += list(entry_args)
            process=subprocess.Popen(command,
                                     cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            record['pid']=process.pid
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                if process.poll() is not None: raise RuntimeError('Entry exited before HTTP readiness')
                try:
                    state=json.loads(request('/status'))
                    if state.get('phase')=='running' and (state.get('virtual_seconds') or 0)>=1.5:
                        record['status']=state
                        break
                except (URLError,TimeoutError):
                    pass
                time.sleep(1)
            else: raise TimeoutError('Entry readiness timeout')
            html=request('/').decode('utf-8')
            if (firmware is None and expected_version not in html) or state.get('hardware_version')!=(expected_hardware_version or expected_version):
                raise ValueError('Wrong entry version')
            if not state.get(diagnostic_key,{}).get('known'):
                raise ValueError('Requested device status adapter unavailable')
            if firmware is not None and state.get('firmware_health_known') is not False:
                raise ValueError('Candidate health must remain explicitly unknown')
            if require_monitor_transport:
                from z62_qmp_transport import VERSION as MONITOR_VERSION
                diagnostics=state.get('monitor_transport',{})
                if diagnostics.get('version')!=MONITOR_VERSION or diagnostics.get('replayed_commands')!=0:
                    raise ValueError('Required monitor transport unavailable')
                record['monitor_transport_verified']=True
            if exercise_half_press:
                from z62_shutter_input_v2 import identity
                if state.get('input_adapter') != identity() or 'data-pin="24"' not in html:
                    raise ValueError('Half-press input adapter unavailable')
                record['half_press_responses'] = [
                    request('/key', True, {'pin': 24, 'level': level}).decode('utf-8')
                    for level in (0, 1)]
                record['release_response'] = request('/release', True).decode('utf-8')
                released = json.loads(request('/status'))
                if released.get('held') or released.get('queued'):
                    raise ValueError('Input remained held after explicit release')
                record['half_press_http_verified'] = True
            if exercise_capture_input:
                from z62_capture_input import identity
                if (state.get('input_adapter') != identity() or 'data-pin="25"' not in html or
                        not state.get('capture_input', {}).get('known')):
                    raise ValueError('Two-stage capture input unavailable')
                before_edges = state['capture_input']['capture-contact-edges']
                record['full_press_responses'] = [request('/key', True, {'pin': 25, 'level': v}).decode('utf-8')
                                                   for v in (0, 1)]
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    released = json.loads(request('/status'))
                    physical = released.get('capture_input', {})
                    if (physical.get('known') and physical.get('capture-contact-edges', 0) >= before_edges + 4
                            and physical.get('capture-contact-levels') == 0 and
                            physical.get('body_input_levels') == [1, 1] and
                            not released.get('held') and not released.get('queued')):
                        break
                    time.sleep(.2)
                else:
                    raise TimeoutError('Coupled full press/release did not complete')
                record['capture_input_after'] = physical
                record['release_response'] = request('/release', True).decode('utf-8')
                record['capture_input_http_verified'] = True
            if before_stop is not None:
                before_stop(request)
            record['stop_response']=request('/stop',True).decode('utf-8')
            process.wait(timeout=30)
            record['exit_code']=process.returncode
            record['completed']=process.returncode==0
        except Exception as exc:
            record['failure']={'type':type(exc).__name__,'message':str(exc),
                               'traceback':traceback.format_exc()}
            raise
        finally:
            if process is not None and process.poll() is None:
                try:
                    request('/stop',True); process.wait(timeout=30)
                except Exception:
                    # Only this test's owned CMD process and descendants.
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                    process.wait(timeout=15)
                    record['forced_cleanup']=True
            record['process_closed']=process is None or process.poll() is not None
            (output/'report.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expected-version',default='2026.10.29-r8')
    p.add_argument('--diagnostic-key',default='finite_stats_status')
    p.add_argument('--firmware',type=Path)
    p.add_argument('--python-entry',type=Path)
    p.add_argument('--exercise-half-press',action='store_true')
    p.add_argument('--require-monitor-transport',action='store_true')
    p.add_argument('--expected-hardware-version')
    p.add_argument('--exercise-capture-input',action='store_true')
    args=p.parse_args()
    result=run(args.output,args.expected_version,args.diagnostic_key,args.firmware,args.python_entry,args.exercise_half_press,args.require_monitor_transport,
               args.expected_hardware_version,args.exercise_capture_input)
    print({k:result.get(k) for k in ('completed','process_closed','exit_code','failure')})
    raise SystemExit(0 if result['completed'] else 1)
