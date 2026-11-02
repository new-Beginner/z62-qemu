# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded read-only RSP trace of Z62 capture stop waits; NO physical USB.
Uses hardware execution breakpoints only; no memory/register patching.
Run separately from untraced menu timing experiments.
"""
import argparse
import importlib
import json
from pathlib import Path
import re
import select
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

from run_reference_console import ROOT, stage, install_native_process_adapter

POINTS = {
    0x106217B8: 'pending-menu-store',
    0x102DBB9C: 'capture-stop-entry',
    0x102DBBAC: 'wait-800-call',
    0x102DD9FC: 'wait-20-call',
    0x1026DB8E: 'capture-stop-result',
    0x1026D4BA: 'notification',
    0x103970D4: 'status-append',
}
WAIT_RETURN = 0x1035D450


def signed32(value):
    return value - (1 << 32) if value & 0x80000000 else value


def trace_complete(record):
    callers = {h.get('caller_lr') for h in record.get('hits', [])
               if h.get('label') == 'kernel-wait-return'}
    return (callers.issuperset({'0x102dbbb1', '0x102dda01'})
            and any(h.get('label') == 'capture-stop-result' for h in record.get('hits', []))
            and record.get('first_0x3f_append_captured') is True
            and record.get('process_closed') is True and record.get('detach') == 'OK'
            and not record.get('failure') and not record.get('cleanup_error'))


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    work, identity = stage('z62', args.qemu, experimental_parameters=True, updates=True)
    identity['laboratory_mode_completion'] = args.mode_completion
    (args.output / 'session.json').write_text(json.dumps(identity, indent=2), encoding='utf-8')
    sys.path.insert(0, str(work / 'source'))
    z = importlib.import_module('tools.z62_console')
    Remote = importlib.import_module('analyze.qemu_display').Remote
    original = install_native_process_adapter(work)
    if args.mode_completion:
        native_popen = subprocess.Popen
        class CompletionPopen(native_popen):
            def __init__(self, command, *a, **kw):
                if isinstance(command, (list, tuple)) and 'qemu-system-arm' in str(command[0]):
                    command = list(command) + ['-global', 'nikon-z62-sensor-config.laboratory-mode-completion=on']
                super().__init__(command, *a, **kw)
        subprocess.Popen = CompletionPopen
    config = SimpleNamespace(qemu=args.qemu.resolve(), master=work/'inputs/master.bin',
        slave=work/'inputs/slave.bin', controller=work/'inputs/controller.bin',
        parameters=work/'parameters', runs=work/'runs', auto_menu=False,
        main_screen_experiment=False, sd_card=None, wsl=False, sampling_source=False,
        input_trace=True, update_store=work/'update-store')
    machine = z.Z62Machine(config)
    record = {'camera_accessed': False, 'guest_state_patched': False,
              'breakpoint_timing_perturbed': True, 'menu_at': args.menu_at,
              'hits': [], 'observations': [], 'removed_breakpoints': [], 'version':'0.1.0'}
    remote = None
    active = set()
    running = False
    start = time.monotonic()

    def save():
        (args.output/'trace.json').write_text(json.dumps(record, indent=2), encoding='utf-8')

    def arm(address):
        if address not in active:
            remote.breakpoint(address)
            active.add(address)

    def disarm(address):
        if address in active:
            remote.breakpoint(address, False)
            active.remove(address)

    def resume():
        nonlocal running
        payload = b'c'
        remote.sock.sendall(b'$'+payload+b'#63')
        running = True
        if remote.sock.recv(1) != b'+':
            raise RuntimeError('missing RSP continue acknowledgement')

    def state():
        s = machine.status()
        with machine.io:
            words = machine._words(0xC253E0C0, 70)
            count = words[68]
            s = {k:s.get(k) for k in ('index','virtual_seconds','display_enabled','menu_pending','queued','execution')}
            s['status_codes'] = words[:count] if count<=68 else None
            s['pending'] = hex(machine._words(0xC181DAE8,1)[0])
            s['mmio'] = {hex(a):hex(machine._words(a,1)[0]) for a in
                        (0x20065508,0x2006550C,0x20065504,0x20065400,0x20060044,0x20060040)}
        return s

    def record_hit(stop):
        match = re.search(r'thread:([0-9a-f]+)', stop)
        if match:
            remote.select_thread(int(match[1],16))
        regs = remote.regs()
        reg = {n:remote.get(regs,n) for n in ('pc','lr','sp','r0','r1','r2','r3','r4','r5','r6','r7')}
        pc = reg['pc']
        h = {'label':POINTS.get(pc,'kernel-wait-return' if pc==WAIT_RETURN else 'unexpected'),
             'stop':stop,'wall_seconds':round(time.monotonic()-start,3),
             'registers':{k:hex(v) for k,v in reg.items()},'state':state()}
        if pc == WAIT_RETURN:
            h['kernel_r0_signed'] = signed32(reg['r0'])
            h['caller_lr'] = hex(int.from_bytes(remote.read(reg['sp']+12,4),'little'))
        if pc in (0x1026D4BA,0x103970D4):
            h['stack_32'] = remote.read(reg['sp'],32).hex()
        record['hits'].append(h)
        print('HIT',h['label'],hex(pc),h.get('kernel_r0_signed'),h['state']['virtual_seconds'],flush=True)
        save()
        return pc, reg, h

    try:
        machine.restart()
        while machine.phase not in ('running','failed'):
            if time.monotonic()-start>60:
                raise TimeoutError('start timeout')
            time.sleep(.1)
        if machine.phase != 'running':
            raise RuntimeError(machine.error)
        with machine.io:
            machine.qmp.command('stop')
        command = json.loads((machine.work/'command.json').read_text())
        port = int(command[command.index('-gdb')+1].rsplit(':',1)[1])
        remote = Remote(port)
        remote.select_thread(1)
        for p in POINTS:
            arm(p)
        resume()
        sent = False
        deadline = time.monotonic()+args.wall_limit
        next_observe = 0
        while time.monotonic()<deadline and len(record['hits'])<100:
            if select.select([remote.sock],[],[],.2)[0]:
                # RSP acknowledgements can precede the actual stop packet.
                remote.sock.settimeout(20)
                stop = remote.receive()
                running = False
                if not stop.startswith('T05'):
                    record['unexpected_stop'] = stop
                    break
                pc, reg, hit = record_hit(stop)
                if pc not in active:
                    record['unexpected_pc'] = hex(pc)
                    break
                disarm(pc)
                if pc in (0x102DBBAC,0x102DD9FC):
                    arm(WAIT_RETURN)
                elif pc == WAIT_RETURN:
                    if hit['caller_lr'] not in ('0x102dbbb1','0x102dda01'):
                        # Preserve explicit evidence of unrelated waits; don't infer target result.
                        record.setdefault('unrelated_waits',[]).append(hit['caller_lr'])
                        # Step only the stopped CPU past this shared return site,
                        # then restore all-CPU continuation and rearm the observer.
                        tid = re.search(r'thread:([0-9a-f]+)', stop).group(1)
                        if remote.command('Hc' + tid) != 'OK':
                            raise RuntimeError('cannot select step CPU')
                        stepped = remote.command('s')
                        if not stepped.startswith('T05'):
                            raise RuntimeError('unexpected single-step stop')
                        if remote.command('Hc-1') != 'OK':
                            raise RuntimeError('cannot restore all CPU continue')
                        arm(WAIT_RETURN)
                if pc==0x103970D4 and reg['r0']==0x3F:
                    record['first_0x3f_append_captured'] = True
                    break
                resume()
            if running and time.monotonic()>=next_observe:
                s=state();record['observations'].append(s);save()
                print('STATE',s['virtual_seconds'],s['index'],s['status_codes'],flush=True)
                if not sent and s['virtual_seconds']>=args.menu_at and s['index']==3:
                    record['menu_request']=s
                    machine.set_key(9,0);machine.set_key(9,1)
                    sent=True;save()
                next_observe=time.monotonic()+2
        else:
            record['trace_limit_reached']=True
    except Exception as exc:
        record['failure']={'type':type(exc).__name__,'message':str(exc)}
        raise
    finally:
        if remote is not None:
            try:
                if running:
                    remote.sock.settimeout(20)
                    record['final_interrupt']=remote.interrupt()
                    running=False
                for p in list(active):
                    disarm(p);record['removed_breakpoints'].append(hex(p))
                record['detach']=remote.command('D')
            except Exception as exc:
                record['cleanup_error']=str(exc)
            finally:
                remote.sock.close()
        try:
            if machine.work:
                for name in ('console.txt','command.json'):
                    p=machine.work/name
                    if p.exists():shutil.copyfile(p,args.output/name)
        finally:
            machine.close();subprocess.Popen=original
            record['process_closed']=machine.process is None or machine.process.poll() is not None
            for p in work.glob('effective-command-*.json'):
                shutil.copyfile(p, args.output / p.name)
            record['trace_complete'] = trace_complete(record)
            save()
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--qemu',type=Path,default=ROOT/'.build/z62-reference-2026.10.27-r1/runtime/qemu-system-arm.exe')
    p.add_argument('--menu-at',type=float,default=3)
    p.add_argument('--mode-completion', action='store_true', help='Single-variable existing lab mode-completion source; not a fix')
    p.add_argument('--wall-limit',type=float,default=600)
    a=p.parse_args()
    if a.menu_at<3 or a.wall_limit<=0:p.error('invalid limit')
    result = run(a)
    if not trace_complete(result):
        raise SystemExit(1)
