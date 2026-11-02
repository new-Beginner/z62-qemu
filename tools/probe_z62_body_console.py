"""Validate actual r19 CMD/HTTP controls against QEMU expander readback.

This checks delivery and release, not the firmware's photographic response.
Only the process started by this probe may be stopped by its cleanup.
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

import z62_body_controls as body
from run_z62_capture_contacts import DEFAULT_QEMU, verify_build

ROOT = Path(__file__).resolve().parents[1]


def run(output, firmware=None):
    build = verify_build(DEFAULT_QEMU)
    output.mkdir(parents=True, exist_ok=False)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'

    def request(path, payload=None):
        req = Request(url + path, data=None if payload is None else json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=15) as response:
            return response.read()

    def state():
        return json.loads(request('/status'))

    def wait_level(pin, level):
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            current = state()
            actual = current.get('body_controls', {}).get('electrical_input', {})
            if (actual.get('known') is True and (actual['levels'] >> pin) & 1 == level
                    and ((pin in current.get('held', [])) == (level == 0))):
                return current
            request('/heartbeat', {})
            time.sleep(.1)
        raise TimeoutError(f'Physical input {pin} did not reach {level}')

    record = {'schema': 1, 'completed': False, 'camera_accessed': False,
              'candidate': firmware is not None, 'body_controls': body.identity(),
              'qemu_sha256': build['binary_sha256'], 'controls': [],
              'firmware_functional_acceptance': False, 'url': url}
    process = None
    try:
        command = ['cmd.exe', '/c', str(ROOT / 'start-z6ii-body-controls.cmd'), '--port', str(port)]
        if firmware is not None:
            command += ['--firmware', str(firmware.resolve())]
        record['command'] = command
        with (output / 'host.log').open('xb') as log:
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        record['pid'] = process.pid
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Owned console exited before readiness')
            try:
                initial = state()
                if initial.get('phase') == 'running' and (initial.get('virtual_seconds') or 0) >= 1.5:
                    break
            except (URLError, TimeoutError):
                pass
            time.sleep(.5)
        else:
            raise TimeoutError('Body console readiness timeout')
        reported = dict(initial.get('body_controls', {}))
        reported.pop('electrical_input', None)
        if reported != body.identity() or initial.get('hardware_version') != '2026.10.29-r13':
            raise ValueError('Wrong staged body controls or hardware identity')
        if firmware is not None and initial.get('firmware_health_known') is not False:
            raise ValueError('Candidate health must stay unknown')
        record['initial_status'] = initial
        html = request('/')
        script = request('/console.js')
        (output / 'index.html').write_bytes(html)
        (output / 'console.js').write_bytes(script)
        record['assets_sha256'] = {'html': hashlib.sha256(html).hexdigest(),
                                   'javascript': hashlib.sha256(script).hexdigest()}
        for name, label, pin, code, shortcut, group in body.CONTROLS:
            if f'data-body-control="{name}"'.encode() not in html:
                raise ValueError('Visible body control is missing: ' + name)
            request('/key', {'pin': pin, 'level': 0})
            pressed = wait_level(pin, 0)
            request('/key', {'pin': pin, 'level': 1})
            released = wait_level(pin, 1)
            record['controls'].append({'id': name, 'pin': pin,
                'pressed_levels': pressed['body_controls']['electrical_input']['levels'],
                'released_levels': released['body_controls']['electrical_input']['levels'],
                'press_virtual_seconds': pressed.get('virtual_seconds'),
                'release_virtual_seconds': released.get('virtual_seconds')})
            print('BODY_HTTP', name, 'physical press/release passed', flush=True)
        # Explicit release must clear all expander inputs and pending queues.
        request('/key', {'pin': 19, 'level': 0})
        wait_level(19, 0)
        request('/release', {})
        final = state()
        if (final['body_controls']['electrical_input'] != {'known': True, 'levels': 0xffffff}
                or final.get('held') or final.get('queued')):
            raise ValueError('Release-all left physical or queued inputs')
        record['release_all_verified'] = True
        record['final_status'] = final
        request('/stop', {})
        process.wait(timeout=30)
        record['exit_code'] = process.returncode
        record['completed'] = process.returncode == 0
    except Exception as exc:
        record['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        if process is not None and process.poll() is None:
            try:
                request('/stop', {})
                process.wait(timeout=30)
            except Exception as exc:
                record['cleanup_error'] = str(exc)
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                process.wait(timeout=15)
                record['forced_cleanup'] = True
        record['process_closed'] = process is None or process.poll() is not None
        (output / 'report.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--firmware', type=Path)
    args = parser.parse_args()
    result = run(args.output, args.firmware)
    print({key: result.get(key) for key in ('completed', 'process_closed', 'failure')})
    raise SystemExit(0 if result['completed'] else 1)
