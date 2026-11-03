"""Observe preparation and input readiness on a fresh VM without sending controls."""
import argparse
import importlib
import json
from pathlib import Path
import re
import select
import struct
import sys
import time
import urllib.parse
import urllib.request

from probe_z62_capture_submit import owner, profiles, stopped_snapshot, ScopedTracer, MASTER_SHA
from probe_z62_prepare_packet import clock
from record_z62_action_evidence import workspace, digest, require, bind
from z62_breakpoint_window import BreakpointWindow

CALLS = {0x103225C4: 'prepare-frame', 0x10238804: 'input-ready-wait'}
POINTS = {0x10315624: 'packet-entry', 0x10315626: 'packet-return'}
POINTS.update({pc: name+'-call' for pc, name in CALLS.items()})
POINTS.update({pc+4: name+'-return' for pc, name in CALLS.items()})
PLAN = {'entry': 0x10315624, 'return_pc': 0x10315626, 'register': 'r1', 'equals': 0x10322449,
        'points': [p for pc in CALLS for p in (pc, pc+4)], 'gate_return': True}
STATE_WORDS = (0xC188808C, 0xC269FA04, 0xC269FA08, 0xC269FA0C, 0xC269FA10, 0xC1888084,
    0x20068008, 0x2006800C, 0x20068200, 0x20068210, 0x20068260, 0x20068270,
    0x20068280, 0x20068290, 0x20069F00, 0x2006A514, 0x2006A518, 0x2006A540,
    0x2006A548, 0x2006A550, 0x2006A560, 0x2006A580)


class ControlTracer(ScopedTracer):
    def __init__(self, remote):
        self.remote = remote; self.active = set()
        self.window = BreakpointWindow(PLAN, POINTS)

    def initialize(self):
        self.arm(PLAN['entry'])


def words(remote, addresses):
    result = {}
    for address in addresses:
        data = remote.read(address, 4)
        require(len(data) == 4, 'Incomplete observed word')
        result[hex(address)] = hex(struct.unpack('<I', data)[0])
    return result


def run(url, session, output, *, packets=3, wall_limit=180):
    session, output = map(workspace, (session, output))
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port and
            parsed.path in ('','/') and not parsed.query and not parsed.fragment, 'Local console required')
    output.mkdir(parents=True, exist_ok=False)
    record = {'schema': 1, 'version': '2026.11.03-prepare-control-r79', 'scope': 'fresh-vm-no-controls',
        'completed_observation': False, 'camera_accessed': False, 'controls_sent': [], 'http_requests': [],
        'guest_memory_written': False, 'guest_registers_written': False, 'breakpoint_timing_perturbed': True,
        'functional_acceptance_eligible': False, 'hits': [], 'window_events': [], 'initial_samples': [],
        'target_packets': packets}
    remote = tracer = None; running = False
    journal = (output/'observations.jsonl').open('x', encoding='utf-8')
    def emit(kind, value):
        journal.write(json.dumps({'kind': kind, 'value': value}, ensure_ascii=False)+'\n'); journal.flush()
    def request(endpoint):
        require(endpoint in ('/status','/software/status','/paired/diagnostics'), 'Read-only endpoint required')
        record['http_requests'].append({'method': 'GET', 'endpoint': endpoint})
        with urllib.request.urlopen(url.rstrip('/')+endpoint, timeout=40) as response:
            return json.load(response)
    try:
        bind(session, output, output/'source-binding.json')
        profile = profiles(session); record['profile'] = profile
        binary = workspace(profile['diagnostic_profile']['runtime_binary'])
        require(digest(binary) == profile['diagnostic_profile']['binary_sha256'] ==
                '37603d1f8c55f819c0e1d3808e670d2de562b954152f2d8b847d1068359296f9', 'Frozen r69 required')
        master = (session/'inputs/master.bin').read_bytes()
        require(digest(session/'inputs/master.bin') == MASTER_SHA, 'Original master required')
        record['master_sha256'] = MASTER_SHA
        deadline = time.monotonic()+900; next_report = 0
        while time.monotonic() < deadline:
            row = request('/paired/diagnostics'); record['initial_samples'].append(row); emit('initial', row)
            if time.monotonic() >= next_report:
                print('INITIAL', row['virtual_time_ns'], row['pipeline_mode']['phase'],
                      row['selector']['original_observed_gate'], flush=True); next_report = time.monotonic()+20
            if row['pipeline_mode']['ready'] and row['pipeline_mode']['confirmed_mode'] == 'photo' and \
                    row['selector']['original_observed_gate']:
                record['initial_gate'] = row; break
            time.sleep(2)
        else:
            raise TimeoutError('Initial original observation gate limit')
        status = request('/status')
        require(Path(status['package_root']).samefile(session) and status['phase'] == 'running', 'Wrong console session')
        software = request('/software/status'); record['software_before'] = software
        require(not software['half_pressed'] and not software['full_pressed'] and
                software['card']['present'] and not software['card']['images'], 'Fresh released camera and empty card required')
        require(record['initial_gate']['capture_flow']['active_word'] == 0, 'Capture already active before control')
        commands = list((session/'runs').glob('*/command.json')); require(len(commands) == 1, 'Single-VM session required')
        command = json.loads(commands[0].read_text(encoding='utf-8'))
        require(Path(command[0]).samefile(binary), 'Command identity differs')
        endpoint = command[command.index('-gdb')+1]
        require(re.fullmatch(r'tcp:127\.0\.0\.1:[0-9]+', endpoint) is not None, 'Unexpected GDB endpoint')
        port = int(endpoint.rsplit(':', 1)[1]); record['owner'] = owner(port, binary)
        paths = [Path(__file__), Path(__file__).with_name('probe_z62_capture_submit.py'),
            Path(__file__).with_name('probe_z62_prepare_packet.py'),
            Path(__file__).with_name('z62_breakpoint_window.py'), session/'source/analyze/qemu_display.py', commands[0]]
        paths.extend((session/'source/tools').glob('*.py'))
        record['source_sha256'] = {str(p): digest(p) for p in paths}
        sys.path.insert(0, str(session/'source'))
        Remote = importlib.import_module('analyze.qemu_display').Remote
        remote = Remote(port); record['attachment_stop'] = remote.command('?')
        require(record['attachment_stop'].startswith(('T05','S05','T02','S02')), 'No stopped target')
        remote.select_thread(1); record['live_anchors'] = []
        for pc in POINTS:
            expected = master[pc-0x10020000:pc-0x10020000+4]
            require(remote.read(pc, 4) == expected, 'Original live instruction differs')
            record['live_anchors'].append({'pc': hex(pc), 'bytes': expected.hex()})
        record['initial'] = stopped_snapshot(remote); record['initial_ns'] = clock(remote)
        record['initial_words'] = words(remote, STATE_WORDS)
        require(record['initial']['capture']['active_word'] == 0, 'Unexpected capture input')
        tracer = ControlTracer(remote); tracer.initialize()
        def resume():
            nonlocal running
            remote.sock.sendall(b'$c#63'); running = True
            require(remote.sock.recv(1) == b'+', 'Missing continue acknowledgement')
        resume(); deadline = time.monotonic()+wall_limit; completed = 0
        while time.monotonic() < deadline and len(record['hits']) < 60:
            if not select.select([remote.sock], [], [], .1)[0]:
                continue
            stop = remote.receive(); running = False
            require(stop.startswith('T05'), 'Unexpected RSP stop')
            match = re.search(r'thread:([0-9a-f]+)', stop); require(match is not None, 'Missing stopped CPU')
            thread = match.group(1); remote.select_thread(int(thread, 16)); raw = remote.regs()
            reg = {name: remote.get(raw, name) for name in ('pc','lr','sp','r0','r1','r2','r3','r4','r5','r6','r7')}
            pc = reg['pc']; require(pc in tracer.active, 'Unexpected breakpoint')
            change, included = tracer.transition(pc, reg, thread)
            if pc == PLAN['entry'] and change != 'open': included = False
            if pc == PLAN['return_pc'] and change != 'close': included = False
            if included:
                hit = {'sequence': len(record['hits'])+1, 'packet_index': completed, 'label': POINTS[pc],
                    'thread': thread, 'virtual_time_ns': clock(remote),
                    'registers': {k: hex(v) for k, v in reg.items()}, 'state': stopped_snapshot(remote)}
                if pc in (0x10238804, 0x10238808):
                    hit['input_words'] = words(remote, STATE_WORDS)
                    hit['output_at_sp'] = words(remote, (reg['sp'],))[hex(reg['sp'])]
                record['hits'].append(hit); emit('hit', hit)
                print('HIT', completed, hit['label'], hit['virtual_time_ns'], hex(reg['r0']), flush=True)
            if change:
                record['window_events'].append({'kind': change, 'pc': hex(pc), 'thread': thread,
                                                'sp': hex(reg['sp']), 'after_hit': len(record['hits'])})
            if change == 'close':
                completed += 1
                if completed >= packets: break
            tracer.step(pc, thread); resume()
        record['completed_packets'] = completed; record['window_active'] = tracer.window.active
        record['final'] = stopped_snapshot(remote); record['final_ns'] = clock(remote)
        record['final_words'] = words(remote, STATE_WORDS)
        record['completed_observation'] = completed == packets and not tracer.window.active
    except Exception as exc:
        record['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        if remote is not None:
            try:
                if running: record['final_interrupt'] = remote.interrupt()
                if tracer is not None: tracer.cleanup()
                record['detach'] = remote.command('D')
            except Exception as exc:
                record['cleanup_error'] = str(exc)
            finally:
                remote.sock.close()
        try:
            record['after_detach'] = request('/paired/diagnostics')
            record['software_after'] = request('/software/status')
        except Exception as exc:
            record['after_detach_error'] = {'type': type(exc).__name__, 'message': str(exc)}
        if 'source_sha256' in record:
            record['sources_unchanged'] = all(digest(Path(p)) == sha for p, sha in record['source_sha256'].items())
        journal.close()
        with (output/'result.json').open('x', encoding='utf-8') as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
    print(json.dumps({k: record.get(k) for k in ('completed_observation','completed_packets','failure',
                    'detach','cleanup_error','sources_unchanged')}, ensure_ascii=False), flush=True)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8688')
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = run(args.url, args.session, args.output)
    raise SystemExit(0 if result['completed_observation'] and result.get('detach') == 'OK' and
                     result.get('sources_unchanged') and not result.get('cleanup_error') else 1)
