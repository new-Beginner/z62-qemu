"""Read actual original enqueue returns in one r69/r76 interactive capture call.

Guest breakpoints perturb timing. This probe never qualifies camera functionality,
replays an HTTP control, writes guest RAM/registers, or closes somebody else's VM.
"""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import importlib
import json
from pathlib import Path
import re
import select
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

from record_z62_action_evidence import workspace, digest, require, bind
from z62_action_queue_console import QUEUE, CAPTURE, queue_layout, decode_queue, decode_capture
from z62_breakpoint_window import BreakpointWindow
from trace_z62_upper_waits import validate_single_step_reply

VERSION = '2026.11.03-capture-submit-r77'
MASTER_SHA = 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4'
POINTS = {0x10325186: 'capture-submit-entry', 0x1031627E: 'capture-enqueue-return',
          0x103EC564: 'capture-submit-return', 0x10320018: 'capture-worker-entry'}
PLAN = {'entry': 0x10325186, 'return_pc': 0x103EC564, 'register': 'r1',
        'equals': 0x103EAE81, 'points': [0x1031627E], 'gate_return': True}


def profiles(session):
    tree = ast.parse((session/'source/tools/z62_console.py').read_text(encoding='utf-8'))
    return {target.id: ast.literal_eval(node.value) for top in tree.body
            if isinstance(top, ast.ClassDef) and top.name == 'Z62Machine'
            for node in top.body if isinstance(node, ast.Assign)
            for target in node.targets if isinstance(target, ast.Name) and
            target.id in ('diagnostic_profile', 'paired_profile')}


def owner(port, binary):
    require(type(port) is int and 1 <= port <= 65535, 'Invalid local GDB port')
    code = ('[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); '
            f'$ids=@(Get-NetTCPConnection -LocalPort {port} -ErrorAction Stop | '
            'Where-Object {$_.LocalAddress -eq "127.0.0.1" -and $_.RemotePort -eq 0 -and $_.OwningProcess -gt 0} | '
            'Select-Object -ExpandProperty OwningProcess -Unique); '
            'if($ids.Count -ne 1){throw "Ambiguous GDB owner"}; '
            'Get-CimInstance Win32_Process -Filter ("ProcessId="+$ids[0]) | '
            'Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress')
    process = subprocess.run(['powershell.exe', '-NoProfile', '-Command', code],
                             capture_output=True, text=True, encoding='utf-8', timeout=20)
    require(process.returncode == 0, 'Cannot identify this session GDB listener: '+process.stderr)
    row = json.loads(process.stdout)
    require(row['ProcessId'] > 0 and Path(row['ExecutablePath']).samefile(binary),
            'GDB listener does not belong to the verified session binary')
    require(re.search(r'(?:^|\s)-gdb\s+tcp:127\.0\.0\.1:'+str(port)+r'(?:\s|$)',
                      row['CommandLine']) is not None, 'Process command does not expose this GDB endpoint')
    return row


def stopped_snapshot(remote):
    def words(address, count):
        data = remote.read(address, count*4)
        require(len(data) == count*4, 'Incomplete stopped memory read')
        return list(struct.unpack('<'+'I'*count, data))
    header = words(QUEUE, 6); layout = queue_layout(header)
    queue = decode_queue(header, words(layout['base'], layout['capacity']*23))
    return {'queue': queue, 'capture': decode_capture(words(CAPTURE, 40)),
            'applv_action_word': words(0xC181D388, 1)[0],
            'input_inhibit': words(0xC1821EB8, 1)[0], 'ready_join': words(0xC1868AE8, 1)[0]}


class ScopedTracer:
    """Reuse the established call frame and step/rearm rules on this RSP client."""
    def __init__(self, remote):
        self.remote = remote
        self.window = BreakpointWindow(PLAN, POINTS)
        self.active = set()

    def arm(self, pc):
        self.remote.breakpoint(pc)
        self.active.add(pc)

    def disarm(self, pc):
        self.remote.breakpoint(pc, False)
        self.active.remove(pc)

    def initialize(self):
        for pc in POINTS:
            if self.window.should_arm(pc):
                self.arm(pc)

    def transition(self, pc, registers, thread):
        change = self.window.transition(pc, registers, thread)
        included = self.window.includes(pc, registers, thread)
        if change:
            for address in sorted(self.window.scoped_points):
                if change == 'open' and address not in self.active:
                    self.arm(address)
                elif change == 'close' and address in self.active:
                    self.disarm(address)
        return change, included

    def step(self, pc, thread):
        if pc in self.active:
            self.disarm(pc)
        require(self.remote.command('Hc'+thread) == 'OK', 'Cannot select stopped CPU')
        validate_single_step_reply(self.remote.command('s'))
        require(self.remote.command('Hc-1') == 'OK', 'Cannot restore all-CPU continuation')
        if self.window.should_arm(pc):
            self.arm(pc)

    def cleanup(self):
        for pc in tuple(self.active):
            self.disarm(pc)


def run(url, session, output, *, wall_limit=240):
    session, output = map(workspace, (session, output))
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port and
            parsed.path in ('', '/') and not parsed.query and not parsed.fragment, 'Local console required')
    output.mkdir(parents=True, exist_ok=False)
    record = {'schema': 1, 'version': VERSION, 'completed_observation': False,
              'camera_accessed': False, 'guest_memory_written': False, 'guest_registers_written': False,
              'guest_breakpoints_used': False, 'breakpoint_timing_perturbed': True,
              'functional_acceptance_eligible': False, 'factory_capture_verified': False,
              'events': [], 'initial_samples': [], 'hits': [], 'window_events': []}
    remote = tracer = None
    running = False
    pool = ThreadPoolExecutor(max_workers=1)
    futures = []
    journal = (output/'observations.jsonl').open('x', encoding='utf-8')
    journal_lock = threading.Lock()
    def emit(kind, value):
        with journal_lock:
            journal.write(json.dumps({'kind': kind, 'value': value}, ensure_ascii=False)+'\n'); journal.flush()
    def request(endpoint, payload=None):
        req = urllib.request.Request(url.rstrip('/')+endpoint,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=40) as response:
            return json.load(response)
    def controls():
        for pressed in (True, False):
            item = {'type': 'shutter', 'payload': {'stage': 'full', 'pressed': pressed}, 'outcome': 'unknown'}
            record['events'].append(item); emit('send', item)
            try:
                reply = request('/camera/event', {'type': item['type'], 'payload': item['payload']})
            except Exception as exc:
                item['error'] = {'type': type(exc).__name__, 'message': str(exc)}
                emit('reply', item)
                raise
            item.update(outcome='accepted', reply=reply); emit('reply', item)
        return True
    try:
        bind(session, output, output/'source-binding.json')
        profile = profiles(session)
        binary = workspace(profile['diagnostic_profile']['runtime_binary'])
        require(digest(binary) == profile['diagnostic_profile']['binary_sha256'] ==
                '37603d1f8c55f819c0e1d3808e670d2de562b954152f2d8b847d1068359296f9', 'Not frozen r69')
        master = (session/'inputs/master.bin').read_bytes()
        require(digest(session/'inputs/master.bin') == MASTER_SHA, 'Original master identity differs')
        record['master_sha256'] = MASTER_SHA
        record['profile'] = profile
        deadline = time.monotonic()+900; report_at = 0
        while time.monotonic() < deadline:
            row = request('/paired/diagnostics'); record['initial_samples'].append(row); emit('initial', row)
            if time.monotonic() >= report_at:
                print('INITIAL', row['virtual_time_ns'], row['selector']['original_observed_gate'],
                      row['pipeline_mode']['phase'], flush=True); report_at = time.monotonic()+20
            if row['pipeline_mode']['ready'] and row['pipeline_mode']['confirmed_mode'] == 'photo' and \
                    row['selector']['original_observed_gate']:
                record['initial_gate'] = row
                break
            time.sleep(2)
        else:
            raise TimeoutError('Original initial gate observation limit')
        status = request('/status')
        require(Path(status['package_root']).samefile(session) and status['phase'] == 'running',
                'HTTP listener belongs to another session')
        card = request('/software/status')
        require(card['card']['present'] and not card['card']['images'] and
                not card['half_pressed'] and not card['full_pressed'], 'Fresh card and released inputs required')
        commands = list((session/'runs').glob('*/command.json'))
        require(len(commands) == 1, 'Require a fresh single-VM session')
        command = json.loads(commands[0].read_text(encoding='utf-8'))
        require(Path(command[0]).samefile(binary), 'Session command binary differs')
        endpoint = command[command.index('-gdb')+1]
        require(re.fullmatch(r'tcp:127\.0\.0\.1:[0-9]+', endpoint) is not None, 'Unexpected GDB address')
        port = int(endpoint.rsplit(':', 1)[1]); record['owner'] = owner(port, binary)
        record['source_sha256'] = {str(p): digest(p) for p in (Path(__file__), commands[0],
            session/'source/analyze/qemu_display.py', Path(__file__).with_name('z62_breakpoint_window.py'))}
        sys.path.insert(0, str(session/'source'))
        Remote = importlib.import_module('analyze.qemu_display').Remote
        record['guest_breakpoints_used'] = True
        remote = Remote(port)
        # QEMU's new GDB connection enters all-stop; '?' retrieves that stop.
        record['attachment_stop'] = remote.command('?')
        require(record['attachment_stop'].startswith(('T05', 'S05', 'T02', 'S02')), 'No stopped target at attachment')
        remote.select_thread(1)
        record['live_anchors'] = []
        for pc in POINTS:
            expected = master[pc-0x10020000:pc-0x10020000+4]
            require(remote.read(pc, 4) == expected, 'Original live instruction differs at '+hex(pc))
            record['live_anchors'].append({'pc': hex(pc), 'bytes': expected.hex()})
        record['stopped_before_input'] = stopped_snapshot(remote)
        tracer = ScopedTracer(remote); tracer.initialize()
        def resume():
            nonlocal running
            remote.sock.sendall(b'$c#63'); running = True
            require(remote.sock.recv(1) == b'+', 'Missing continue acknowledgement')
        resume()
        futures.append(pool.submit(controls))
        deadline = time.monotonic()+wall_limit
        while time.monotonic() < deadline and len(record['hits']) < 16:
            if select.select([remote.sock], [], [], .1)[0]:
                stop = remote.receive(); running = False
                require(stop.startswith('T05'), 'Unexpected RSP stop: '+stop)
                match = re.search(r'thread:([0-9a-f]+)', stop)
                require(match is not None, 'Missing stopped CPU'); thread = match.group(1)
                remote.select_thread(int(thread, 16)); raw = remote.regs()
                reg = {name: remote.get(raw, name) for name in ('pc','lr','sp','r0','r1','r2','r3','r4','r5','r6','r7')}
                pc = reg['pc']; require(pc in tracer.active, 'Unexpected execution breakpoint')
                change, included = tracer.transition(pc, reg, thread)
                if included:
                    hit = {'sequence': len(record['hits'])+1, 'label': POINTS[pc], 'thread': thread,
                           'registers': {k: hex(v) for k, v in reg.items()},
                           'state': stopped_snapshot(remote), 'stack_32': remote.read(reg['sp'], 32).hex()}
                    record['hits'].append(hit); emit('hit', hit)
                    print('HIT', hit['label'], hex(reg['r0']), hit['state']['queue']['count'], flush=True)
                if change:
                    row = {'kind': change, 'thread': thread, 'pc': hex(pc), 'sp': hex(reg['sp'])}
                    record['window_events'].append(row); emit('window', row)
                if change == 'close':
                    break
                tracer.step(pc, thread); resume()
            if futures[0].done():
                futures[0].result()
        record['window_active'] = tracer.window.active
        record['completed_observation'] = (not tracer.window.active and
            [h['label'] for h in record['hits'] if h['label'] != 'capture-worker-entry'] ==
            ['capture-submit-entry', 'capture-enqueue-return', 'capture-submit-return'])
        record['stop_reason'] = 'capture-submit-return' if record['completed_observation'] else 'observation limit'
    except Exception as exc:
        record['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        if remote is not None:
            try:
                if running:
                    record['final_interrupt'] = remote.interrupt(); running = False
                if tracer is not None:
                    tracer.cleanup()
                record['detach'] = remote.command('D')
            except Exception as exc:
                record['cleanup_error'] = str(exc)
            finally:
                remote.sock.close()
        for future in futures:
            try:
                future.result(timeout=45)
            except Exception as exc:
                record.setdefault('control_errors', []).append({'type': type(exc).__name__, 'message': str(exc)})
        pool.shutdown(wait=True)
        try:
            record['after_detach'] = request('/paired/diagnostics')
        except Exception as exc:
            record['after_detach_error'] = {'type': type(exc).__name__, 'message': str(exc)}
        if 'source_sha256' in record:
            record['sources_unchanged'] = all(digest(Path(p)) == sha for p, sha in record['source_sha256'].items())
        binding = output/'source-binding.json'
        if binding.is_file():
            bound = json.loads(binding.read_text(encoding='utf-8'))
            record['bound_before_shutter_send'] = bound['bound_before_shutter_send']
            record['reader_sources_unchanged'] = all(digest(Path(p)) == sha for p, sha in bound['source_sha256'].items())
            record['source_binding_sha256'] = digest(binding)
        journal.close()
        with (output/'result.json').open('x', encoding='utf-8') as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
    print(json.dumps({k: record.get(k) for k in ('completed_observation','failure','detach','cleanup_error',
                                                'sources_unchanged','control_errors')}, ensure_ascii=False), flush=True)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8688')
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.url, args.session, args.output)
    raise SystemExit(0 if result['completed_observation'] and result.get('detach') == 'OK' and
                     result.get('sources_unchanged') and not result.get('control_errors') else 1)
