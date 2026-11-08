"""Observe stock EG startup on pinned Z62 QEMU; never writes guest registers/memory.

Only model boot-image loading and reset PC setup precede original EG execution.
No controller, calibration parameters, card, plugin or earlier camera loader.
"""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

from startup_contract import ROOT, BASE, PROFILES, collect, read_inputs, sha, require

sys.path.insert(0, str(ROOT/'tools'))
from probe_reference_devices import free_port, connect
from probe_z62_functional_raw import Session
sys.path.insert(0, str(ROOT/'third_party/z62-qemu'))
from analyze.qemu_display import Remote

QEMU_REL = '.build/z62-output-lineage-2026.11.03-r69/runtime/qemu-system-arm.exe'
QEMU_SHA = '37603d1f8c55f819c0e1d3808e670d2de562b954152f2d8b847d1068359296f9'

def stopped_thread(reply, current):
    """Hg selection can make qC stale after another CPU traps."""
    match = re.search(r'(?:^|;)thread:([0-9a-f]+);', reply[3:])
    if match is not None:
        return match.group(1)
    require(reply.startswith('S05') and current.startswith('QC'), 'Missing stopped CPU identity')
    thread = current[2:]
    require(re.fullmatch('[0-9a-f]+',thread) is not None, 'Unexpected thread encoding')
    return thread


def advance_breakpoint(remote, address, thread, keep):
    """Step the original instruction only when the shared breakpoint is kept."""
    remote.breakpoint(address, False)
    if not keep:
        return None
    require(remote.command('Hc'+thread) == 'OK', 'Cannot select step thread')
    reply = remote.command('s')
    require(reply.startswith('T05') or reply.startswith('S05'), 'Unexpected single-step stop: '+reply)
    require(remote.command('Hc-1') == 'OK', 'Cannot restore all-thread continuation')
    remote.breakpoint(address)
    return reply



def run(output):
    output = output.resolve()
    require(output.is_relative_to(ROOT/'analysis') and not output.exists(), 'Use new analysis output')
    root = Path('Q:/')
    require(root.is_dir() and root.samefile(ROOT), 'Verified ASCII Q: workspace alias required')
    binary = root/QEMU_REL
    require(sha(binary.read_bytes()) == QEMU_SHA, 'Pinned QEMU changed')
    images, contract = read_inputs(), collect()
    qmp_port, gdb_port = free_port(), free_port()
    require(qmp_port != gdb_port, 'Port collision; rerun with new output')
    machine = ('nikon-z62-dual-lab,'
               f'master-boot-image={root}/artifacts/z62-reference-1.70/master.bin,'
               f'slave-boot-image={root}/artifacts/z62-reference-1.70/slave.bin')
    command = [str(binary), '-M', machine, '-smp', '4,maxcpus=5', '-S',
               '-display','none','-serial','none','-monitor','none','-nic','none',
               '-gdb',f'tcp:127.0.0.1:{gdb_port}', '-icount','shift=0,sleep=off',
               '-qmp',f'tcp:127.0.0.1:{qmp_port},server=on,wait=off']
    for cpu in range(4):
        command += ['-device',f'loader,addr={BASE:#x},cpu-num={cpu}']
    record = dict(schema=1, completed=False, scope='original EG early startup only', command=command,
                  qemu_sha256=QEMU_SHA, contract=contract,
                  sources={name:sha((ROOT/name).read_bytes()) for name in (
                      Path(__file__).relative_to(ROOT).as_posix(),
                      'third_party/z62-qemu/analyze/qemu_display.py',
                      'tools/probe_reference_devices.py','tools/probe_z62_functional_raw.py')},
                  firmware_loaded=True, firmware_integrated=False, flash_safety_verified=False,
                  camera_accessed=False, debugger_guest_registers_written=False, debugger_guest_memory_written=False,
                  reset_pc_initialized_by_qemu_loader=True,
                  original_firmware_patched=False, breakpoints='RSP Z1 execution breakpoints; timing perturbed',
                  earlier_camera_loader_executed=False, parameters_loaded=False, card_attached=False,
                  controller_loaded=False, hits=[])
    output.parent.mkdir(parents=True, exist_ok=True)
    log_path = output.with_suffix('.qemu.log')
    require(not log_path.exists(), 'Log exists')
    process = remote = session = qmp_sock = qmp_stream = None
    active = {BASE+0xBE74, BASE+0xBF88, BASE+0xAC, BASE+0x38,
              *(p['runtime']+8 for p in PROFILES.values())}
    seen = {role:set() for role in PROFILES}
    initial_third = {}
    error = None
    with output.open('x', encoding='utf-8') as evidence:
        try:
            env = dict(os.environ, TEMP=os.environ['PI_SCRATCH_DIR'], TMP=os.environ['PI_SCRATCH_DIR'],
                       TMPDIR=os.environ['PI_SCRATCH_DIR'], PYTHONDONTWRITEBYTECODE='1')
            with log_path.open('xb') as log:
                process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log, env=env)
            record['owned_pid'] = process.pid
            qmp_sock = connect(qmp_port, process); qmp_sock.settimeout(5)
            qmp_stream = qmp_sock.makefile('rwb')
            session = Session(); session.qmp = qmp_stream
            json.loads(qmp_stream.readline()); session.query('qmp_capabilities')
            start = time.monotonic()
            for _ in range(100):
                require(process.poll() is None, 'Owned QEMU exited during connection')
                try:
                    remote = Remote(gdb_port); break
                except (ConnectionRefusedError, socket.timeout):
                    time.sleep(.05)
            require(remote is not None, 'GDB connection timeout')
            remote.sock.settimeout(40)
            record['gdb_threads'] = remote.command('qfThreadInfo')
            record['system_register_names'] = [n for n in remote.register_numbers if
                any(k in n.upper() for k in ('SCTLR','TTBR','TTBCR','DACR','VBAR','MPIDR','DFSR','IFSR'))]
            for address in sorted(active):
                remote.breakpoint(address)
            while time.monotonic()-start < 150 and len(record['hits']) < 40:
                reply = remote.command('c')
                require(reply.startswith('T05') or reply.startswith('S05'), 'Unexpected guest stop: '+reply)
                # Select the CPU in the stop packet, not the last Hg-selected CPU.
                current = remote.command('qC')
                record['last_stop_context'] = dict(stop=reply,current=current)
                tid = stopped_thread(reply,current)
                remote.select_thread(int(tid,16))
                regs = remote.regs()
                pc = remote.get(regs,'pc')
                head = remote.read(BASE,0x6C)
                roles = [r for r,d in images.items() if head == d[:0x6C]]
                require(len(roles)==1, 'Stopped CPU address space does not match stock EG')
                role = roles[0]
                r = contract['roles'][role]
                names = {BASE+0xBE74:'before-inline', BASE+0xBF88:'after-inline',
                         r['startup']['runtime_thumb']:'runtime-thumb', BASE+0xAC:'kernel-entry',
                         BASE+0x38:'scatter-dispatch'}
                require(pc in names, f'Unexpected breakpoint {role} {pc:#x}')
                kind = names[pc]
                row = dict(role=role, kind=kind, thread=tid, stop_reply=reply, wall_seconds=round(time.monotonic()-start,3),
                           registers={n:remote.get(regs,n) for n in ('r0','r1','r2','r3','r4','sp','lr','pc','cpsr')})
                record['hits'].append(row)
                row['system_registers'] = {n:remote.read_register(n) for n in record['system_register_names']}
                require(bool(row['registers']['cpsr'] & 32) == (kind in ('runtime-thumb','scatter-dispatch')), 'Instruction state mismatch')
                # Independently confirm the stock TTBR contents as seen by this CPU.
                if kind == 'before-inline':
                    table = remote.read(BASE+0x10000,0x4000)
                    row['page_table_sha256'] = sha(table)
                    require(table == images[role][0x10000:0x14000], 'Original page table changed')
                    initial_third[role] = remote.read(r['startup']['early_copies'][2]['destination'],64)
                    row['third_destination_head_sha256'] = sha(initial_third[role])
                if kind == 'after-inline':
                    require('before-inline' in seen[role], 'Missing before-inline observation')
                    checks = []
                    for c in r['startup']['early_copies'][:2]:
                        actual = remote.read(c['destination'],c['size'])
                        expected = images[role][c['source']-BASE:c['source']-BASE+c['size']]
                        checks.append(dict(destination=c['destination'], size=c['size'], expected_sha256=sha(expected),
                                           actual_sha256=sha(actual), equal=actual==expected))
                        require(actual == expected, 'Original early copy mismatch')
                    row['copy_checks'] = checks
                    third = remote.read(r['startup']['early_copies'][2]['destination'],64)
                    row['third_destination_head_unchanged'] = third == initial_third[role]
                    require(third == initial_third[role], 'Zero-length inline destination sample changed')
                seen[role].add(kind)
                print(role,kind,hex(pc),flush=True)
                # Keep a shared-address breakpoint until both roles were observed.
                peers = [rr for rr in PROFILES if (pc in (BASE+0xBE74,BASE+0xBF88,BASE+0xAC,BASE+0x38) or rr==role)]
                keep = not all(kind in seen[rr] for rr in peers)
                row['step_reply'] = advance_breakpoint(remote,pc,tid,keep)
                if not keep:
                    active.remove(pc)
                if all({'before-inline','after-inline','runtime-thumb','kernel-entry'} <= s for s in seen.values()):
                    break
            record['seen'] = {r:sorted(s) for r,s in seen.items()}
            require(all({'before-inline','after-inline','runtime-thumb','kernel-entry'} <= s for s in seen.values()), 'Early startup observation incomplete')
            record['observed_copy_bytes'] = sum(c['size'] for r in contract['roles'].values() for c in r['startup']['early_copies'][:2])
            record['full_scatter_dispatch_execution_verified'] = False
            record['startup_complete_hook_verified'] = False
            record['owned_shutdown'] = 'QMP quit at early breakpoint; NOT camera normal shutdown'
            session.query('quit'); process.wait(timeout=15)
            require(process.returncode==0, 'Owned QEMU did not exit cleanly')
            record['completed'] = True
        except Exception as exc:
            error = exc
            record['failure'] = dict(type=type(exc).__name__, message=str(exc))
            if session is not None and process is not None and process.poll() is None:
                try:
                    session.query('quit'); process.wait(timeout=10)
                except Exception as cleanup:
                    record['quit_failure'] = str(cleanup)
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=10)
            record['owned_process_closed'] = process is not None and process.poll() is not None
            record['exit_code'] = None if process is None else process.returncode
            for handle in (getattr(remote,'sock',None),qmp_stream,qmp_sock):
                if handle is not None:
                    handle.close()
            if log_path.exists():
                record['log_sha256'] = sha(log_path.read_bytes())
            json.dump(record,evidence,indent=2);evidence.write('\n')
    if error is not None:
        raise error
    print(json.dumps({k:record[k] for k in ('completed','seen','observed_copy_bytes','owned_process_closed','firmware_integrated','flash_safety_verified')},indent=2))
    return record


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
