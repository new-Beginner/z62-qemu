"""Observe original Z62 RTOS pool initialization; no injected calls or writes."""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import time

from memory_contract import collect
from startup_contract import ROOT, BASE, PROFILES, read_inputs, sha, require
from observe_startup import QEMU_REL,QEMU_SHA,Remote,Session,free_port,connect,stopped_thread,advance_breakpoint


def run(output):
    output=output.resolve()
    require(output.is_relative_to(ROOT/'analysis') and not output.exists(),'Use new analysis output')
    root=Path('Q:/');require(root.is_dir() and root.samefile(ROOT),'Verified Q: alias required')
    binary=root/QEMU_REL;require(sha(binary.read_bytes())==QEMU_SHA,'Pinned QEMU changed')
    contract,images=collect(),read_inputs()
    qmp_port,gdb_port=free_port(),free_port();require(qmp_port!=gdb_port,'Port collision')
    machine=('nikon-z62-dual-lab,'f'master-boot-image={root}/artifacts/z62-reference-1.70/master.bin,'
             f'slave-boot-image={root}/artifacts/z62-reference-1.70/slave.bin')
    command=[str(binary),'-M',machine,'-smp','4,maxcpus=5','-S','-display','none','-serial','none',
             '-monitor','none','-nic','none','-gdb',f'tcp:127.0.0.1:{gdb_port}',
             '-icount','shift=0,sleep=off','-qmp',f'tcp:127.0.0.1:{qmp_port},server=on,wait=off']
    for cpu in range(4):command+=['-device',f'loader,addr={BASE:#x},cpu-num={cpu}']
    record=dict(schema=1,completed=False,contract=contract,command=command,qemu_sha256=QEMU_SHA,
        sources={name:sha((ROOT/name).read_bytes()) for name in (
            Path(__file__).relative_to(ROOT).as_posix(),'fenestra/z62/observe_startup.py',
            'third_party/z62-qemu/analyze/qemu_display.py','tools/probe_reference_devices.py',
            'tools/probe_z62_functional_raw.py')},
        firmware_loaded=True,firmware_integrated=False,flash_safety_verified=False,camera_accessed=False,
        debugger_guest_registers_written=False,debugger_guest_memory_written=False,
        reset_pc_initialized_by_qemu_loader=True,injected_calls=False,parameters_loaded=False,
        card_attached=False,controller_loaded=False,earlier_camera_loader_executed=False,
        allocator_call_abi_verified=False,allocation_lifetime_verified=False,plugin_execution_in_heap_verified=False,
        breakpoint_timing_perturbed=True,hits=[],ignored_secondary=[])
    points={r:{v['pool_init']:'pool-before',v['pool_return']:'pool-after',
               v['heap_return']:'heap-after',v['services_return']:'services-after'} for r,v in contract['roles'].items()}
    active={p for rows in points.values() for p in rows}
    seen={r:[] for r in PROFILES};owner={};stacks={}
    output.parent.mkdir(parents=True,exist_ok=True);log_path=output.with_suffix('.qemu.log')
    require(not log_path.exists(),'Log already exists')
    process=remote=session=qmp_sock=qmp_stream=None;error=None
    with output.open('x',encoding='utf-8') as evidence:
        try:
            env=dict(os.environ,TEMP=os.environ['PI_SCRATCH_DIR'],TMP=os.environ['PI_SCRATCH_DIR'],TMPDIR=os.environ['PI_SCRATCH_DIR'])
            with log_path.open('xb') as log:process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=log,env=env)
            record['owned_pid']=process.pid
            qmp_sock=connect(qmp_port,process);qmp_sock.settimeout(5);qmp_stream=qmp_sock.makefile('rwb')
            session=Session();session.qmp=qmp_stream;json.loads(qmp_stream.readline());session.query('qmp_capabilities')
            remote=Remote(gdb_port);remote.sock.settimeout(45)
            for address in active:remote.breakpoint(address)
            start=time.monotonic()
            for _ in range(40):
                require(time.monotonic()-start<120,'Observation wall limit')
                stop=remote.command('c');require(stop.startswith('T05') or stop.startswith('S05'),'Unexpected stop '+stop)
                current=remote.command('qC');tid=stopped_thread(stop,current);remote.select_thread(int(tid,16))
                regs=remote.regs();registers={n:remote.get(regs,n) for n in ('r0','r1','r2','r3','sp','lr','pc','cpsr')}
                head=remote.read(BASE,0x6C);roles=[r for r,d in images.items() if head==d[:0x6C]]
                require(len(roles)==1,'Stopped CPU image is not original');role=roles[0];p=contract['roles'][role]
                pc=registers['pc'];require(pc in points[role],f'Unexpected {role} PC {pc:#x}')
                kind=points[role][pc]
                if kind=='services-after' and owner.get(role)!=tid:
                    record['ignored_secondary'].append(dict(role=role,thread=tid,stop=stop,pc=pc))
                    advance_breakpoint(remote,pc,tid,True);continue
                require(kind not in seen[role],'Duplicate primary checkpoint')
                row=dict(role=role,kind=kind,thread=tid,stop=stop,previous_selected_thread=current,
                         registers=registers,wall_seconds=round(time.monotonic()-start,3))
                record['hits'].append(row)
                require(registers['cpsr']&32==0,'Expected original ARM memory routines')
                if kind=='pool-before':
                    owner[role]=tid;stacks[role]=registers['sp']
                    row['pool_config_before']=list(struct.unpack('<4I',remote.read(p['pool_config'],16)))
                    g=p['geometry'];require(row['pool_config_before'][:2]==[g['start'],g['end']],'Original pool bounds mismatch')
                    require(registers['lr']==p['pool_return'],'Pool caller mismatch')
                    table=remote.read(p['copied_table'],0x4000);row['installed_table_sha256']=sha(table)
                    require(table==images[role][0x10000:0x14000],'Installed original table differs')
                else:
                    require(owner.get(role)==tid,'Wrong primary thread')
                    require(registers['r0']==0,'Original memory routine returned failure')
                    require(registers['sp']==stacks[role]+(8 if kind=='services-after' else 0),'Original stack not restored')
                names=('TTBR0_S','TTBCR_S','DACR_S','SCTLR_EL1_S','VBAR_EL1_S','DFSR_S','IFSR_S','DFSR','IFSR')
                row['system_registers']={n:remote.read_register(n) for n in names}
                system=row['system_registers']
                require(system['TTBR0_S']==p['copied_table'] and system['TTBCR_S']==0,'Original RAM table not active')
                require(system['SCTLR_EL1_S']&0x1005==0x1005,'MMU/cache disabled')
                require(all(system[n]==0 for n in ('DFSR_S','IFSR_S','DFSR','IFSR')),'Observed CPU fault state')
                if kind=='pool-after':
                    g=p['geometry'];count=g['count']
                    row['pool_state']=list(struct.unpack('<4I',remote.read(p['pool_state'],16)))
                    row['pool_config']=list(struct.unpack('<4I',remote.read(p['pool_config'],16)))
                    row['first_headers']=list(struct.unpack('<6I',remote.read(g['start'],24)))
                    row['tail_header']=list(struct.unpack('<2I',remote.read(g['start']+count*8,8)))
                    require(row['pool_state']==[count,count,g['start'],g['pool_end']],'Initial pool state mismatch')
                    require(row['pool_config'][0]==g['end'],'Pool initialization cursor mismatch')
                    require(row['first_headers']==[4,4,1,0,(count<<2)|1,0] and row['tail_header']==[(count<<2)|1,0],
                            'Pool header mismatch')
                if kind=='heap-after':
                    row['heap_control']=list(struct.unpack('<2I',remote.read(p['heap_control'],8)))
                    require(row['heap_control']==[0,0x800],'Initial heap control mismatch')
                    row['list_groups']=[]
                    for group in p['list_groups']:
                        b=group['base'];words=list(struct.unpack('<5I',remote.read(b+8,20)))
                        row['list_groups'].append(dict(**group,words=words))
                        require(words==[b+8,b+8,b+16,b+16,group['flags']],'Original empty list mismatch')
                seen[role].append(kind);print(role,kind,hex(pc),flush=True)
                advance_breakpoint(remote,pc,tid,False);active.remove(pc)
                if all(len(s)==4 for s in seen.values()):break
            require(all(s==['pool-before','pool-after','heap-after','services-after'] for s in seen.values()),'Memory window incomplete')
            record['seen']=seen;record['memory_initialization_verified']=True
            session.query('quit');process.wait(timeout=15);require(process.returncode==0,'QEMU did not exit normally')
            record['completed']=True
        except Exception as exc:
            error=exc;record['failure']=dict(type=type(exc).__name__,message=str(exc))
            if session is not None and process is not None and process.poll() is None:
                try:session.query('quit');process.wait(timeout=10)
                except Exception as cleanup:record['quit_failure']=str(cleanup)
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
            record['owned_process_closed']=process is not None and process.poll() is not None
            record['exit_code']=None if process is None else process.returncode
            for h in (getattr(remote,'sock',None),qmp_stream,qmp_sock):
                if h is not None:h.close()
            if log_path.exists():record['log_sha256']=sha(log_path.read_bytes())
            json.dump(record,evidence,indent=2);evidence.write('\n')
    if error is not None:raise error
    print(json.dumps({k:record[k] for k in ('completed','seen','memory_initialization_verified','owned_process_closed','firmware_integrated','flash_safety_verified')},indent=2))
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output)
