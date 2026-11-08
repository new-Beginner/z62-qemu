"""Independent replay of r8 original wait STR, not wait completion/flash certification."""
import argparse
import copy
import json
import math
from pathlib import Path
import re

import observe_wait_store as observer
from observe_boot_wait import FALSE_FIELDS, build_command
from verify_boot_wait import flags, EXPERIMENTAL, DEFAULT_COMPLETIONS
from verify_task_context import check_regs, check_system, check_final_cpus
from observe_startup import stopped_thread
from startup_contract import ROOT, BASE, read_inputs, require, sha
from wait_store_contract import TOOL, collect, check_event, summarize

FALSE = FALSE_FIELDS + ('wait_registration_completed','task_identity_verified','hardware_root_cause_identified')


def require_independent(records):
    require(len(records) >= 2 and len({r['owned_pid'] for r in records}) == len(records),
            'Two independent original processes required')


def check_run(r):
    require(r['schema'] == 1 and r['tool'] == TOOL and r['completed'] is True,'Incomplete current trace')
    require(r['exit_code'] == 0 and r['owned_process_closed'] is True and 'failure' not in r and
            'quit_failure' not in r and r['close_notes'] == [],'Process/trace/close failed')
    require(r['quit_receipt'] == {'acknowledged':True},'Actual QMP quit receipt required')
    require(all(r.get(k) is False for k in FALSE),'Scope changed')
    require(r['firmware_loaded'] is True and r['reset_pc_initialized_by_qemu_loader'] is True and
            r['breakpoint_timing_perturbed'] is True and r['controller_loaded'] is False and
            r['controller_link_enabled'] is False,'Original minimal boot scope changed')
    require(r['owned_shutdown'] == 'QMP quit; NOT camera normal shutdown','Shutdown claim changed')
    require(r['sources'] == {n:sha((ROOT/n).read_bytes()) for n in observer.SOURCES},'Source identity changed')
    require(r['qemu_sha256'] == observer.QEMU_SHA and
            sha((ROOT/observer.QEMU_REL).read_bytes()) == observer.QEMU_SHA,'Pinned model changed')
    contract, images = collect(), read_inputs()
    require(r['contract'] == contract,'Original static contract changed')
    require(type(r['owned_pid']) is int and r['owned_pid'] > 0,'Missing process identity')
    cmd = r['command']; require(len(cmd) == 28,'Command length changed')
    g = re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+)',cmd[15])
    q = re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+),server=on,wait=off',cmd[19])
    require(g is not None and q is not None and 1024 <= int(g[1]) <= 65535 and
            1024 <= int(q[1]) <= 65535,'Loopback ports required')
    require(cmd == build_command(Path('Q:/'),'minimal',int(g[1]),int(q[1])),'Minimal command changed')
    for n in EXPERIMENTAL: require(flags(r['model_tree'],n) == ['false','false'],'Model experimental flag: '+n)
    for n in DEFAULT_COMPLETIONS: require(flags(r['model_tree'],n) == ['true','true'],'Default completion scope: '+n)
    events = r['events']
    require(type(r['max_stops']) is int and 32 <= r['max_stops'] <= 512 and
            r['trace_stop_reason'] == 'sample-bound' and len(events) == r['max_stops'],
            'This replay requires complete bounded sample trace')
    require(math.isfinite(r['guest_target_seconds']) and 1 <= r['guest_target_seconds'] <= 6 and
            30 <= r['wall_limit_seconds'] <= 180 and math.isfinite(r['wall_seconds']) and
            0 < r['wall_seconds'] <= r['wall_limit_seconds'] + 30,'Observation limits differ')
    previous = -1
    points = sorted(p['checkpoint'] for p in contract['roles'].values())
    expected_control = [f'Z1,{pc:x},2' for pc in points]
    expected_reads = []
    for index,e in enumerate(events):
        require(e['sequence'] == index,'Omitted/reordered STR event')
        regs = e['registers']; p = contract['roles'][e['role']]; pc = regs['pc']
        check_regs(regs);check_regs(e['after_registers']);check_system(e['system'],e['role'])
        require(e['stop'].startswith('T05') and
                stopped_thread(e['stop'],e['previous_selected_thread']) == e['thread'],'Stopping CPU changed')
        require(e['step_reply'].startswith('T05') and
                stopped_thread(e['step_reply'],'QC'+e['thread']) == e['thread'],'Isolated step CPU changed')
        require(e['image_head'] == images[e['role']][:0x6C].hex(),'Original engine identity changed')
        require(e['rom_window'] == dict(address=pc-16,bytes=images[e['role']][pc-BASE-16:pc-BASE+16].hex()),
                'Original STR runtime ROM changed')
        require(e['analysis'] == check_event(e,p),'Original STR/object analysis changed')
        require(type(e['model_ticks']) is int and e['model_ticks'] >= previous,'Model clock regressed')
        previous = e['model_ticks']
        expected_control += ['c',f'z1,{pc:x},2','vCont;s:'+e['thread'],f'Z1,{pc:x},2']
        expected_reads += [f'm{BASE:x},6c',f'm{p["context"]["current"]:x},8',f'm{regs["r4"]:x},18',
            f'm{regs["r1"]:x},100',f'm{regs["sp"]+16:x},40',f'm{pc-16:x},20','m4266008,8',
            f'm{regs["r4"]:x},18',f'm{regs["r1"]:x},100']
    require(r['summary'] == summarize(events,contract),'STR summary changed')
    require(all(any(e['role'] == role for e in events) for role in ('master','slave')),'Missing engine role')
    require(type(r['trace_end_ticks']) is int and r['trace_end_ticks'] >= previous,'Trace clock changed')
    previous = r['trace_end_ticks']
    for pause in r['pauses']:
        require(pause['phase'] == 'untraced' and pause['stop'].startswith('T02') and
                type(pause['ticks']) is int and pause['ticks'] > previous,'Guest deadline pause differs')
        previous = pause['ticks']
    require(type(r['final_ticks']) is int and r['final_ticks'] >= previous and
            r['guest_target_reached'] is True and r['final_ticks'] >= r['guest_target_seconds'] * 48000000,
            'Guest model window not reached')
    require(r['final_status'] == {'status':'paused','running':False},'Final CPUs not paused')
    idle = check_final_cpus(r['final_cpus'],images,contract,r['final_ticks'])
    commands = r['rsp_commands']
    for c in commands:
        ok = (c in ('c','g','qC','qfThreadInfo') or c.startswith(('qSupported:','qXfer:features:read:')) or
              re.fullmatch(r'Hg[0-4]|p[0-9a-f]+|m[0-9a-f]+,[0-9a-f]+|[Zz]1,[0-9a-f]+,2|vCont;s:0[1-4]',c))
        require(bool(ok),'Forbidden RSP: '+c)
    expected_control += [f'z1,{pc:x},2' for pc in points]+['c']*len(r['pauses'])
    require([c for c in commands if c == 'c' or c.startswith(('Z','z','vCont;'))] == expected_control,
            'Breakpoint/isolated step lifecycle changed')
    reads = [c for c in commands if c.startswith('m')]
    require(reads[:len(expected_reads)] == expected_reads,'Original event read windows/order changed')
    tail = []
    for c in r['final_cpus']:
        p = contract['roles'][c['role']]['context']; regs = c['registers']
        tail += [f'm{BASE:x},6c',f'm{p["current"]:x},8',f'm{p["ready"]:x},8','m4266008,8',
                 f'm{regs["pc"]-16:x},40',f'm{regs["sp"]:x},80']
    require(reads[-len(tail):] == tail and reads[len(expected_reads):-len(tail)] and
            all(c == 'm4266008,8' for c in reads[len(expected_reads):-len(tail)]),'Final read windows differ')
    require(commands.count('g') == 2*len(events)+4 and commands.count('qC') == 2*len(events),
            'Register/stop CPU coverage differs')
    require(r['rsp_controls'] == ['interrupt']*len(r['pauses']),'Interrupt count changed')
    require(r['qmp_commands'] == [dict(command='qmp_capabilities',arguments={}),
        dict(command='human-monitor-command',arguments={'command-line':'info qtree'}),
        dict(command='query-status',arguments={}),dict(command='quit',arguments={})],'QMP commands changed')
    return dict(pid=r['owned_pid'],events=len(events),summary=r['summary'],final_idle_engine_cpus=idle,
        trace_model_seconds=r['trace_end_ticks']/48000000,final_model_seconds=r['final_ticks']/48000000,
        complete_task_abi_verified=False,**{n:False for n in FALSE})


def mutations(record):
    out = {}
    def changed(name):
        out[name] = copy.deepcopy(record);return out[name]
    changed('omitted')['events'].pop()
    changed('role')['events'][0]['role'] = 'master' if record['events'][0]['role'] == 'slave' else 'slave'
    changed('cpu')['events'][0]['thread'] = '05'
    changed('slot')['events'][0]['current'] = [0,0]
    changed('object-before')['events'][0]['object_before'] = '00'*24
    changed('object-after')['events'][0]['object_after'] = '00'*24
    changed('tcb-after')['events'][0]['tcb_after'] = '00'*256
    changed('caller-stack')['events'][0]['call_stack_address'] += 4
    changed('register')['events'][0]['after_registers']['r2'] ^= 1
    changed('step-cpu')['events'][0]['step_reply'] = 'T05thread:05;'
    changed('rom')['events'][0]['rom_window']['bytes'] = '00'*32
    changed('system')['events'][0]['system']['DFSR_S'] = 1
    changed('clock')['final_ticks'] = 0
    changed('guest')['guest_target_reached'] = False
    changed('scope')['firmware_integrated'] = True
    changed('source')['sources']['fenestra/z62/wait_store_contract.py'] = '0'*64
    changed('command')['command'].append('-nographic')
    changed('rsp-write')['rsp_commands'].append('M10020000,1:00')
    bad=changed('breakpoint');bad['rsp_commands'].remove(next(c for c in bad['rsp_commands'] if c.startswith('z1,')))
    changed('qmp')['qmp_commands'].append(dict(command='system_reset',arguments={}))
    changed('model')['model_tree'] = record['model_tree'].replace('frame-sync = false','frame-sync = true')
    changed('summary')['summary']['master']['events'] += 1
    changed('final-cpu')['final_cpus'][0]['registers']['pc'] += 4
    return out


def verify(paths,output):
    require(not output.exists() and output.resolve().is_relative_to(ROOT/'analysis'),'Use new analysis output')
    records=[];runs=[]
    for path in paths:
        record=json.loads(path.read_text(encoding='utf-8')); row=check_run(record)
        require(sha(path.with_suffix('.qemu.log').read_bytes()) == record['log_sha256'],'QEMU log identity changed')
        row.update(path=path.relative_to(ROOT).as_posix(),sha256=sha(path.read_bytes()))
        records.append(record);runs.append(row)
    require_independent(records)
    rejected=[]
    for name,bad in mutations(records[0]).items():
        try:check_run(bad)
        except (ValueError,KeyError,TypeError,IndexError):rejected.append(name)
        else:raise ValueError('Mutation accepted: '+name)
    result=dict(schema=1,tool='fenestra-z62-wait-store-verifier/0.1.0',
        verifier_sha256=sha(Path(__file__).read_bytes()),runs=runs,record_mutations_rejected=rejected,
        bounded_original_str_samples_replayed=True,complete_task_abi_verified=False,**{n:False for n in FALSE})
    with output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();verify([p.resolve() for p in args.run],args.output.resolve())
