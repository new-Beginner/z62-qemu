"""Time three original preparation packets after the r77 capture rejection.

No controls are sent. Source binding starts in this explicitly post-capture state;
guest breakpoints exclude this run from camera functional acceptance.
"""
import argparse
import importlib
import json
from pathlib import Path
import re
import select
import struct
import sys
import time

from probe_z62_capture_submit import owner, profiles, stopped_snapshot, ScopedTracer, MASTER_SHA
from record_z62_action_evidence import workspace, digest, require
from z62_breakpoint_window import BreakpointWindow

CALLS = {0x103225C4: 'prepare-frame', 0x102335E0: 'frame-event8', 0x1023382C: 'frame-event15'}
POINTS = {0x10315624: 'packet-entry', 0x10315626: 'packet-return'}
POINTS.update({pc: name+'-call' for pc, name in CALLS.items()})
POINTS.update({pc+4: name+'-return' for pc, name in CALLS.items()})
PLAN = {'entry': 0x10315624, 'return_pc': 0x10315626, 'register': 'r1', 'equals': 0x10322449,
        'points': [p for pc in CALLS for p in (pc, pc+4)], 'gate_return': True}


class PrepareTracer(ScopedTracer):
    def __init__(self, remote):
        self.remote = remote; self.active = set()
        self.window = BreakpointWindow(PLAN, POINTS)

    def initialize(self):
        self.arm(PLAN['entry'])


def clock(remote):
    data = remote.read(0x04266008, 12)
    require(len(data) == 12, 'Incomplete original input-clock read')
    low, high, frequency = struct.unpack('<3I', data)
    require(frequency > 0, 'Original input clock unavailable')
    return ((high << 32) | low)*1_000_000_000//frequency


def run(session, output, previous, *, wall_limit=180, packets=3):
    session, output, previous = map(workspace, (session, output, previous))
    prior = json.loads(previous.read_text(encoding='utf-8'))
    require(prior['completed_observation'] and prior['detach'] == 'OK' and prior['reader_sources_unchanged'],
            'Require the completed r77 capture-rejection trace')
    require(prior['profile'] == profiles(session), 'Do not change session between these observations')
    output.mkdir(parents=True, exist_ok=False)
    record = {'schema': 1, 'version': '2026.11.03-prepare-packet-r78', 'scope': 'post-r77-capture-rejection',
        'prior_trace_sha256': digest(previous), 'completed_observation': False, 'camera_accessed': False,
        'controls_sent': [], 'guest_memory_written': False, 'guest_registers_written': False,
        'breakpoint_timing_perturbed': True, 'functional_acceptance_eligible': False,
        'hits': [], 'window_events': [], 'target_packets': packets}
    remote = tracer = None; running = False
    journal = (output/'hits.jsonl').open('x', encoding='utf-8')
    try:
        command_paths = list((session/'runs').glob('*/command.json'))
        require(len(command_paths) == 1, 'Fresh single-VM session required')
        command = json.loads(command_paths[0].read_text(encoding='utf-8'))
        binary = Path(command[0]); expected = prior['profile']['diagnostic_profile']['binary_sha256']
        require(digest(binary) == expected, 'Runtime differs')
        master = (session/'inputs/master.bin').read_bytes()
        require(digest(session/'inputs/master.bin') == MASTER_SHA, 'Original master differs')
        port = int(command[command.index('-gdb')+1].rsplit(':', 1)[1])
        record['owner'] = owner(port, binary)
        require(record['owner']['ProcessId'] == prior['owner']['ProcessId'], 'VM changed after capture trace')
        paths = [Path(__file__), Path(__file__).with_name('probe_z62_capture_submit.py'),
                 Path(__file__).with_name('z62_breakpoint_window.py'), session/'source/analyze/qemu_display.py']
        paths.extend((session/'source/tools').glob('*.py'))
        record['source_sha256'] = {str(p): digest(p) for p in paths}
        sys.path.insert(0, str(session/'source'))
        Remote = importlib.import_module('analyze.qemu_display').Remote
        remote = Remote(port); record['attachment_stop'] = remote.command('?')
        require(record['attachment_stop'].startswith(('T05','S05','T02','S02')), 'No stopped target')
        remote.select_thread(1)
        record['live_anchors'] = []
        for pc in POINTS:
            expected = master[pc-0x10020000:pc-0x10020000+4]
            require(remote.read(pc, 4) == expected, 'Original instruction differs')
            record['live_anchors'].append({'pc': hex(pc), 'bytes': expected.hex()})
        record['initial'] = stopped_snapshot(remote); record['initial_ns'] = clock(remote)
        tracer = PrepareTracer(remote); tracer.initialize()
        def resume():
            nonlocal running
            remote.sock.sendall(b'$c#63'); running = True
            require(remote.sock.recv(1) == b'+', 'Missing continue acknowledgement')
        resume(); deadline = time.monotonic()+wall_limit; completed = 0
        while time.monotonic() < deadline and len(record['hits']) < 80:
            if not select.select([remote.sock], [], [], .1)[0]:
                continue
            stop = remote.receive(); running = False
            require(stop.startswith('T05'), 'Unexpected RSP stop')
            match = re.search(r'thread:([0-9a-f]+)', stop)
            require(match is not None, 'Missing stopped CPU'); thread = match.group(1)
            remote.select_thread(int(thread, 16)); raw = remote.regs()
            reg = {name: remote.get(raw, name) for name in ('pc','lr','sp','r0','r1','r2','r3','r4','r5','r6','r7')}
            pc = reg['pc']; require(pc in tracer.active, 'Unexpected breakpoint')
            change, included = tracer.transition(pc, reg, thread)
            if pc == PLAN['entry'] and change != 'open':
                included = False
            if pc == PLAN['return_pc'] and change != 'close':
                included = False
            if included:
                hit = {'sequence': len(record['hits'])+1, 'packet_index': completed,
                       'label': POINTS[pc], 'thread': thread, 'virtual_time_ns': clock(remote),
                       'registers': {k: hex(v) for k, v in reg.items()},
                       'queue_header': remote.read(0xC23D9F14, 24).hex(),
                       'operation_state_36': remote.read(0xC1868A70, 36).hex()}
                record['hits'].append(hit)
                journal.write(json.dumps(hit)+'\n'); journal.flush()
                print('HIT', hit['packet_index'], hit['label'], hit['virtual_time_ns'], hex(reg['r0']), flush=True)
            if change:
                record['window_events'].append({'kind': change, 'pc': hex(pc), 'thread': thread,
                                                'sp': hex(reg['sp']), 'after_hit': len(record['hits'])})
            if change == 'close':
                completed += 1
                if completed >= packets:
                    break
            tracer.step(pc, thread); resume()
        record['completed_packets'] = completed
        record['window_active'] = tracer.window.active
        record['completed_observation'] = completed == packets and not tracer.window.active
        record['final'] = stopped_snapshot(remote); record['final_ns'] = clock(remote)
    except Exception as exc:
        record['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        if remote is not None:
            try:
                if running:
                    record['final_interrupt'] = remote.interrupt()
                if tracer is not None:
                    tracer.cleanup()
                record['detach'] = remote.command('D')
            except Exception as exc:
                record['cleanup_error'] = str(exc)
            finally:
                remote.sock.close()
        if 'source_sha256' in record:
            record['sources_unchanged'] = all(digest(Path(p)) == sha for p, sha in record['source_sha256'].items())
        journal.close()
        with (output/'result.json').open('x', encoding='utf-8') as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
    print(json.dumps({k: record.get(k) for k in ('completed_observation','completed_packets',
                    'failure','detach','cleanup_error','sources_unchanged')}, ensure_ascii=False), flush=True)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--previous-trace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.session, args.output, args.previous_trace)
    raise SystemExit(0 if result['completed_observation'] and result.get('detach') == 'OK' and
                     result.get('sources_unchanged') and not result.get('cleanup_error') else 1)
