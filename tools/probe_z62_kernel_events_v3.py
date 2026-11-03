"""r85: also observe the actual notification publication during an AND wait.

No inferior calls, guest writes, injected IRQs or controls. ARM breakpoints use
four-byte sizes; outer Thumb points use two. Exact event CB identity is checked.
"""
import argparse
import importlib
import json
from pathlib import Path
import re
import select
import sys
import traceback
import time
import urllib.parse
import urllib.request

from probe_z62_capture_submit import owner, profiles
from probe_z62_prepare_packet import clock
from trace_z62_upper_waits import validate_single_step_reply
from record_z62_action_evidence import workspace, digest, require, bind
from z62_kernel_event_layout import contract, resolve, OBJECT

THUMB = {0x102392FC: 'notification-call', 0x10239300: 'notification-return',
         0x10238804: 'wait-call', 0x10238808: 'wait-return',
         0x1035D450: 'kernel-wait-result'}
ARM = {0x101110EC: 'kernel-set-entry', 0x101111C4: 'kernel-pattern-store',
       0x10111318: 'kernel-set-return', 0x10111410: 'kernel-wait-entry',
       0x10111628: 'kernel-and-test'}


def signed(value):
    return value-(1 << 32) if value & (1 << 31) else value


def task_frame(sp, stored, delta=0):
    return stored is not None and sp == stored['sp']+delta


def run(url, session, output):
    session, output = map(workspace, (session, output))
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port and
            parsed.path in ('','/') and not parsed.query and not parsed.fragment, 'Local console required')
    output.mkdir(parents=True, exist_ok=False)
    record = {'schema': 1, 'version': '2026.11.03-kernel-events-r85', 'scope': 'no-controls-real-kernel-events',
        'completed_observation': False, 'controls_sent': [], 'camera_accessed': False,
        'guest_memory_written': False, 'guest_registers_written': False, 'inferior_functions_called': False,
        'breakpoint_timing_perturbed': True, 'functional_acceptance_eligible': False,
        'hits': [], 'initial_samples': [], 'outside_stops': [], 'http_requests': []}
    remote = None; active = set(); running = False; phase = 'notification'
    outer_set = kernel_set = outer_wait = kernel_wait = None
    journal = (output/'observations.jsonl').open('x', encoding='utf-8')
    def emit(kind, value):
        journal.write(json.dumps({'kind': kind, 'value': value}, ensure_ascii=False)+'\n'); journal.flush()
    def request(endpoint):
        require(endpoint in ('/status','/software/status','/paired/diagnostics'), 'Read-only console endpoint required')
        record['http_requests'].append({'method': 'GET', 'endpoint': endpoint})
        with urllib.request.urlopen(url.rstrip('/')+endpoint, timeout=40) as response: return json.load(response)
    def arm(pc):
        if pc not in active:
            require(remote.command('Z1,%x,%d'%(pc, 4 if pc in ARM else 2)) == 'OK', 'Execution breakpoint rejected')
            active.add(pc)
    def disarm(pc):
        if pc in active:
            require(remote.command('z1,%x,%d'%(pc, 4 if pc in ARM else 2)) == 'OK', 'Cannot remove breakpoint')
            active.remove(pc)
    def registers():
        raw = remote.regs()
        return {name: remote.get(raw, name) for name in ('pc','lr','sp','r0','r1','r2','r3','r4','r5','r6','r7')}
    def step(pc, thread):
        disarm(pc)
        require(remote.command('Hc'+thread) == 'OK', 'Cannot select stopped CPU')
        validate_single_step_reply(remote.command('s'))
        require(remote.command('Hc-1') == 'OK', 'Cannot restore all-CPU continuation')
    def resume():
        nonlocal running
        remote.sock.sendall(b'$c#63'); running = True
        require(remote.sock.recv(1) == b'+', 'Missing continue acknowledgement')
    def hit(label, reg, thread):
        row = {'sequence': len(record['hits'])+1, 'label': label, 'phase': phase, 'thread': thread,
            'virtual_time_ns': clock(remote), 'registers': {k: hex(v) for k, v in reg.items()},
            'event': resolve(remote, layout)}
        record['hits'].append(row); emit('hit', row)
        print('HIT', label, hex(reg['r0']), row['event']['pattern'], flush=True)
        return row
    def frame(thread, sp, stored, delta=0):
        return stored is not None and thread == stored['thread'] and sp == stored['sp']+delta
    try:
        bind(session, output, output/'source-binding.json')
        image = (session/'inputs/master.bin').read_bytes(); layout = contract(image); record['layout'] = layout
        profile = profiles(session); record['profile'] = profile
        binary = workspace(profile['diagnostic_profile']['runtime_binary'])
        require(digest(binary) == profile['diagnostic_profile']['binary_sha256'] ==
                '37603d1f8c55f819c0e1d3808e670d2de562b954152f2d8b847d1068359296f9', 'Frozen r69 required')
        deadline = time.monotonic()+900; report_at = 0
        while time.monotonic() < deadline:
            row = request('/paired/diagnostics'); record['initial_samples'].append(row); emit('initial', row)
            if time.monotonic() >= report_at:
                print('INITIAL', row['virtual_time_ns'], row['pipeline_mode']['phase'], flush=True); report_at = time.monotonic()+20
            if row['pipeline_mode']['ready'] and row['pipeline_mode']['confirmed_mode'] == 'photo' and \
                    row['selector']['original_observed_gate']:
                record['initial_gate'] = row; break
            time.sleep(2)
        else: raise TimeoutError('Initial original gate observation limit')
        require(record['initial_gate']['capture_flow']['active_word'] == 0, 'Capture already active')
        status = request('/status'); require(Path(status['package_root']).samefile(session), 'Wrong console session')
        software = request('/software/status'); record['software_before'] = software
        require(not software['half_pressed'] and not software['full_pressed'] and not software['card']['images'],
                'Released keys and an empty test card required')
        commands = list((session/'runs').glob('*/command.json')); require(len(commands) == 1, 'Single VM required')
        command = json.loads(commands[0].read_text(encoding='utf-8'))
        require(Path(command[0]).samefile(binary), 'Command binary differs')
        endpoint = command[command.index('-gdb')+1]
        require(re.fullmatch(r'tcp:127\.0\.0\.1:[0-9]+', endpoint) is not None, 'Unexpected GDB endpoint')
        port = int(endpoint.rsplit(':',1)[1]); record['owner'] = owner(port, binary)
        paths = [Path(__file__), Path(__file__).with_name('z62_kernel_event_layout.py'),
            Path(__file__).with_name('probe_z62_capture_submit.py'), Path(__file__).with_name('probe_z62_prepare_packet.py'),
            Path(__file__).with_name('trace_z62_upper_waits.py'), session/'source/analyze/qemu_display.py', commands[0]]
        record['source_sha256'] = {str(p): digest(p) for p in paths}
        sys.path.insert(0, str(session/'source')); Remote = importlib.import_module('analyze.qemu_display').Remote
        remote = Remote(port); record['attachment_stop'] = remote.command('?')
        require(record['attachment_stop'].startswith(('T05','S05','T02','S02')), 'No stopped target')
        remote.select_thread(1); record['live_anchors'] = []
        for pc in {**THUMB, **ARM}:
            size = 4 if pc in ARM else 2; expected = image[pc-0x10020000:pc-0x10020000+size]
            require(remote.read(pc, size) == expected, 'Original kernel instruction differs')
            record['live_anchors'].append({'pc': hex(pc), 'bytes': expected.hex(), 'mode': 'ARM' if pc in ARM else 'Thumb'})
        record['initial_event'] = resolve(remote, layout)
        identifier = int(record['initial_event']['identifier'],16)
        control_block = int(record['initial_event']['control_block'],16)
        arm(0x102392FC); resume(); deadline = time.monotonic()+180; stops = 0
        while time.monotonic() < deadline and stops < 512:
            if not select.select([remote.sock], [], [], .1)[0]: continue
            stop = remote.receive(); running = False; stops += 1
            require(stop.startswith('T05'), 'Unexpected RSP stop')
            match = re.search(r'thread:([0-9a-f]+)', stop); require(match is not None, 'Missing stopped CPU')
            thread = match.group(1); remote.select_thread(int(thread,16)); reg = registers(); pc = reg['pc']
            require(pc in active, 'Unexpected breakpoint')
            accepted = False; rearm = True
            if pc == 0x102392FC and outer_set is None and reg['r0'] == OBJECT and reg['r1'] == 0x800000:
                outer_set = {'thread': thread, 'sp': reg['sp']}; hit(THUMB[pc], reg, thread); accepted=True; rearm=False
                arm(0x10239300); arm(0x101110EC)
            elif pc == 0x101110EC and outer_set and thread == outer_set['thread'] and reg['r0'] == identifier and reg['r1'] == 0x800000:
                kernel_set = {'thread': thread, 'sp': reg['sp']}; hit(ARM[pc], reg, thread); accepted=True; rearm=False
                arm(0x101111C4); arm(0x10111318)
            elif pc == 0x101111C4 and frame(thread,reg['sp'],kernel_set,-layout['setter_stack_bytes']) and reg['r4'] == control_block:
                row = hit(ARM[pc], reg, thread); accepted=True; rearm=False
                require(reg['r0'] == (int(row['event']['pattern'],16) | reg['r6']), 'Kernel OR result differs')
                step(pc, thread); row['after_original_store'] = resolve(remote, layout)
                require(int(row['after_original_store']['pattern'],16) == reg['r0'], 'Original pattern publication differs')
                emit('original-store-result', row); resume(); continue
            elif pc == 0x10111318 and frame(thread,reg['sp'],kernel_set,-layout['setter_stack_bytes']):
                row = hit(ARM[pc],reg,thread); row['kernel_result_signed'] = signed(reg['r0'])
                accepted=True; rearm=False; emit('kernel-result',row)
            elif pc == 0x10239300 and frame(thread,reg['sp'],outer_set):
                hit(THUMB[pc],reg,thread); accepted=True; rearm=False
                require(kernel_set is not None, 'No matching kernel setter')
                phase='wait'; arm(0x10238804)
            elif pc == 0x10238804 and outer_wait is None and reg['r0'] == OBJECT and reg['r1'] == 0x5B00000:
                outer_wait={'thread':thread,'sp':reg['sp']}; hit(THUMB[pc],reg,thread); accepted=True; rearm=False
                arm(0x10238808); arm(0x10111410)
            elif pc == 0x10111410 and outer_wait and thread == outer_wait['thread'] and reg['r0'] == identifier and reg['r1'] == 0x5B00000:
                kernel_wait={'thread':thread,'sp':reg['sp']}; row=hit(ARM[pc],reg,thread)
                row['timeout_argument'] = int.from_bytes(remote.read(reg['sp'],4),'little')
                require(reg['r2'] == 0, 'Original wait is not this AND-mode contract')
                accepted=True; rearm=False; arm(0x10111628); arm(0x1035D450)
            elif pc == 0x10111628 and frame(thread,reg['sp'],kernel_wait,-48) and reg['r4'] == control_block:
                row=hit(ARM[pc],reg,thread); accepted=True; rearm=False
                require(reg['r6'] == 0 and reg['r3'] == int(row['event']['pattern'],16), 'Kernel wait pattern differs')
                step(pc,thread); after=registers(); row['missing_mask_after_original_bics'] = hex(after['r2'])
                require(after['r2'] == reg['r7'] & ~reg['r3'], 'Original AND condition differs')
                emit('original-and-result',row)
                outer_set=None; kernel_set=None
                arm(0x102392FC)
                record['notification_during_wait_armed']=True
                resume(); continue
            elif pc == 0x1035D450 and task_frame(reg['sp'],outer_wait,-16):
                row=hit(THUMB[pc],reg,thread); row['kernel_result_signed']=signed(reg['r0'])
                row['before_boolean_conversion']=True
                emit('kernel-result',row); accepted=True; rearm=False
            elif pc == 0x10238808 and task_frame(reg['sp'],outer_wait):
                row=hit(THUMB[pc],reg,thread)
                row['output_at_sp']=hex(int.from_bytes(remote.read(reg['sp'],4),'little'))
                record['completed_observation'] = all(any(h['label']==label for h in record['hits']) for label in
                    ('kernel-set-entry','kernel-pattern-store','kernel-set-return','notification-return',
                     'kernel-wait-entry','kernel-and-test','kernel-wait-result','wait-return'))
                break
            if not accepted: record['outside_stops'].append({'pc':hex(pc),'thread':thread,'sp':hex(reg['sp']),'r0':hex(reg['r0'])})
            step(pc,thread)
            if rearm: arm(pc)
            resume()
        record['stops']=stops
        if running:
            record['final_interrupt_before_snapshot']=remote.interrupt(); running=False
        record['final_event']=resolve(remote,layout)
        record['stop_reason']='complete-set-and-wait' if record['completed_observation'] else 'observation-limit'
    except Exception as exc:
        record['failure']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        emit('failure',record['failure'])
    finally:
        if remote is not None:
            try:
                if running: record['final_interrupt']=remote.interrupt()
                for pc in tuple(active): disarm(pc)
                record['detach']=remote.command('D')
            except Exception as exc: record['cleanup_error']=str(exc)
            remote.sock.close()
        try:
            record['after_detach']=request('/paired/diagnostics'); record['software_after']=request('/software/status')
        except Exception as exc: record['after_detach_error']={'type':type(exc).__name__,'message':str(exc)}
        if 'source_sha256' in record:
            record['sources_unchanged']=all(digest(Path(p))==sha for p,sha in record['source_sha256'].items())
        journal.close()
        with (output/'result.json').open('x',encoding='utf-8') as handle: json.dump(record,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:record.get(k) for k in ('completed_observation','failure','detach','cleanup_error','sources_unchanged')},ensure_ascii=False),flush=True)
    return record


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8688')
    parser.add_argument('--session',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); result=run(args.url,args.session,args.output)
    raise SystemExit(0 if result['completed_observation'] and result.get('detach')=='OK' and not result.get('cleanup_error') else 1)




