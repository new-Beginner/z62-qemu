"""Strict replay of r15 local native startup call chains; no live guest access."""
import argparse
import copy
import json
import math
from pathlib import Path
import re
import observe_task_launch as observer
from startup_contract import ROOT, BASE, PROFILES, require, sha, read_inputs
from observe_startup import stopped_thread
from verify_boot_wait import EXPERIMENTAL, DEFAULT_COMPLETIONS, flags
from verify_task_context import check_regs, check_system, check_final_cpus
from verify_task_create import allowed_command, require_independent
from verify_task_entry import check_first_step
from task_launch_contract import TOOL, collect, classify, ingest, complete, ready, summarize, check_prepared


def check_run(r):
    require(r['schema'] == 1 and r['tool'] == TOOL and r['completed'] is True and
            not any(n in r for n in ('failure','quit_failure','forced_host_cleanup')), 'Incomplete launch observation')
    require(r['exit_code'] == 0 and r['owned_process_closed'] is True and r['close_notes'] == [] and
            r['mapping_removed'] is True and r['quit_receipt'] == {'acknowledged':True}, 'Owned cleanup differs')
    require(all(r.get(n) is False for n in observer.FALSE_FIELDS) and r['default_completion_logic_disabled'] is False and
            r['controller_link_enabled'] is False and r['firmware_inputs'] == PROFILES, 'Scope differs')
    require(all(r[n] is True for n in ('firmware_loaded','reset_pc_initialized_by_qemu_loader','breakpoint_timing_perturbed')) and
            r['owned_shutdown'] == 'QMP quit; NOT camera normal shutdown', 'Reset/shutdown scope differs')
    require({n:r[n] for n in observer.model_identity()} == observer.model_identity(), 'New model identity differs')
    require(r['sources'] == {n:sha((ROOT/n).read_bytes()) for n in observer.SOURCES}, 'Source identity differs')
    c,images = collect(),read_inputs(); require(r['contract'] == c, 'Original static contract differs')
    cmd = r['command']; require(len(cmd) == 28, 'Command length differs')
    g = re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+)',cmd[15])
    q = re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+),server=on,wait=off',cmd[19])
    require(g is not None and q is not None and 1024 <= int(g[1]) <= 65535 and 1024 <= int(q[1]) <= 65535 and
            cmd == observer.command((int(g[1]),int(q[1]))), 'Exact loopback command differs')
    for n in EXPERIMENTAL: require(flags(r['model_tree'],n) == ['false','false'], 'Experimental property differs: '+n)
    for n in DEFAULT_COMPLETIONS: require(flags(r['model_tree'],n) == ['true','true'], 'Default completion differs: '+n)
    maximum = r['max_calls']
    require(type(r['owned_pid']) is int and r['owned_pid'] > 0 and type(maximum) is int and 8 <= maximum <= 128 and
            1 <= r['guest_target_seconds'] <= 6 and 30 <= r['wall_limit_seconds'] <= 300 and
            math.isfinite(r['wall_seconds']) and 0 < r['wall_seconds'] <= r['wall_limit_seconds']+30, 'Bounds differ')
    events = r['events']; require(len(events) <= 8*(maximum+64) and r['trace_stop_reason'] == 'sample-bound-drained' and
            r['pending'] == [], 'Incomplete bounded sample')
    pairs = []; permanent = observer.permanent_points(c); active = set(permanent)
    controls = [f'Z1,{a:x},2' for a in sorted(active)]; reads = []; clock = -1
    for index,e in enumerate(events):
        require(e['sequence'] == index, 'Missing/reordered event')
        role = e['role']; p = c['roles'][role]; regs = e['registers']; pc = regs['pc']; tid = e['thread']
        check_regs(regs); check_regs(e['after_registers']); check_system(e['system'],role); check_system(e['after_system'],role)
        require(e['after_system'] == e['system'], 'Original single instruction changed system/fault state')
        require(tid in {'master':('01','02'),'slave':('03','04')}[role] and
                e['local_cpu'] == (int(tid,16)-1)%2 and len(e['current']) == 2 and
                all(type(n) is int and 0 <= n < 2**32 for n in e['current']), 'Role/current CPU differs')
        require(pc in active and e['stop'].startswith('T05') and
                stopped_thread(e['stop'],e['previous_selected_thread']) == tid and
                e['step_reply'].startswith('T05') and stopped_thread(e['step_reply'],'QC'+tid) == tid,
                'Stop/isolated-step CPU differs')
        image = images[role]
        require(e['image_head'] == image[:0x6C].hex() and
                e['rom_window'] == dict(address=pc-16,bytes=image[pc-BASE-16:pc-BASE+16].hex()), 'Original ROM differs')
        require(type(e['model_ticks']) is int and e['model_ticks'] >= clock, 'Model clock regressed'); clock=e['model_ticks']
        phase,pi = classify(pairs,e,p)
        require((e['phase'],e['pair_index']) == (phase,pi), 'Derived phase differs')
        controls.append('c'); reads += [f'm{BASE:x},6c',f'm{pc-16:x},20','m4266008,8',f'm{p["context"]["current"]:x},8']
        if phase == 'input':
            require(len(pairs) < maximum+64, 'Prepared bound exceeded')
            reads += [f'm{p["table_global"]:x},8',f'm{e["tcb_address"]:x},d8',f'm{e["after_registers"]["sp"]:x},28']
        elif phase == 'prepared':
            entry = check_prepared(e,p)['entry_pc']; require(entry not in permanent, 'Permanent/entry conflict')
            reads += [f'm{e["tcb_address"]:x},d8',f'm{e["frame_address"]:x},4c',f'm{regs["sp"]:x},28']
            if entry not in active: controls.append(f'Z1,{entry:x},2'); active.add(entry)
        elif phase == 'returned':
            target = e['after_registers']['pc']
            require(BASE+16 <= target < BASE+len(image)-18 and e['return_rom'] ==
                    dict(address=target-16,bytes=image[target-BASE-16:target-BASE+16].hex()), 'Actual return target ROM differs')
            reads += [f'm{regs["sp"]:x},28',f'm{target-16:x},20']
        elif phase == 'entered':
            reads += [f'm{e["tcb_address"]:x},d8']; check_first_step(e)
        else: require(pc not in permanent and pi is None, 'Invalid unmatched first entry')
        ingest(pairs,e,p)
        controls += [f'z1,{pc:x},2','vCont;s:'+tid,f'Z1,{pc:x},2']
        if phase == 'entered' and pc not in observer.entry_points(pairs,c):
            controls.append(f'z1,{pc:x},2'); active.remove(pc)
        require(index == len(events)-1 or not ready(pairs,maximum), 'Observer continued beyond drained sample')
    require(ready(pairs,maximum) and len(pairs) < maximum+64 and pairs == r['pairs'] and
            r['summary'] == summarize(pairs), 'Rebuilt call chains/summary differ')
    for s in pairs:
        order = [e['phase'] for e in events if e['pair_index'] == s['sequence']]
        require(order in (['input','prepared','returned','entered'], ['input','prepared','entered','returned']),
                'Duplicate/omitted call phase')
    require(type(r['trace_end_ticks']) is int and r['trace_end_ticks'] >= clock, 'Trace end clock differs')
    clock = r['trace_end_ticks']
    for pause in r['pauses']:
        require(pause['phase'] == 'untraced' and pause['stop'].startswith('T02') and pause['ticks'] > clock,
                'Pause/deadline differs'); clock=pause['ticks']
    require(r['guest_target_reached'] is True and type(r['final_ticks']) is int and r['final_ticks'] >= clock and
            r['final_ticks'] >= r['guest_target_seconds']*48000000 and
            r['final_status'] == {'status':'paused','running':False}, 'Final window/status differs')
    idle = check_final_cpus(r['final_cpus'],images,c,r['final_ticks'])
    controls += [f'z1,{a:x},2' for a in sorted(active)]+['c']*len(r['pauses'])
    commands = r['rsp_commands']
    for item in commands: allowed_command(item)
    require([n for n in commands if n == 'c' or n.startswith(('Z','z','vCont;'))] == controls, 'Breakpoint lifecycle differs')
    tail = []
    for e in r['final_cpus']:
        p = c['roles'][e['role']]['context']; regs=e['registers']
        tail += [f'm{BASE:x},6c',f'm{p["current"]:x},8',f'm{p["ready"]:x},8','m4266008,8',
                 f'm{regs["pc"]-16:x},40',f'm{regs["sp"]:x},80']
    actual = [n for n in commands if n.startswith('m')]
    require(actual[:len(reads)] == reads and actual[-len(tail):] == tail and actual[len(reads):-len(tail)] and
            all(n == 'm4266008,8' for n in actual[len(reads):-len(tail)]), 'Exact bounded memory read plan differs')
    require(commands.count('g') == 2*len(events)+4 and commands.count('qC') == 2*len(events) and
            r['rsp_controls'] == ['interrupt']*len(r['pauses']), 'Register/interrupt coverage differs')
    require(r['qmp_commands'] == [dict(command='qmp_capabilities',arguments={}),
        dict(command='human-monitor-command',arguments={'command-line':'info qtree'}),
        dict(command='query-status',arguments={}),dict(command='quit',arguments={})], 'QMP command plan differs')
    return dict(pid=r['owned_pid'],calls=len(pairs),events=len(events),summary=r['summary'],
        unmatched_entry_stops=sum(e['phase'] == 'unmatched-entry' for e in events),
        trace_model_seconds=r['trace_end_ticks']/48000000, final_model_seconds=r['final_ticks']/48000000,
        final_idle_engine_cpus=idle, local_input_publish_pop_entry_samples_verified=True,
        **{n:False for n in observer.FALSE_FIELDS})


def mutations(record):
    out = {}
    def edit(name): out[name]=copy.deepcopy(record); return out[name]
    def event(name,phase,change):
        r=edit(name); e=next(e for e in r['events'] if e['phase']==phase); change(e)
        if e['pair_index'] is not None: r['pairs'][e['pair_index']][phase]=copy.deepcopy(e)
    edit('omitted')['events'].pop(); edit('pending')['pending']=[0]
    edit('scope')['firmware_integrated']=True; edit('qemu')['qemu_sha256']='0'*64
    edit('source')['sources'][observer.SOURCES[0]]='0'*64
    edit('command')['command'].append('-nographic'); edit('rsp-write')['rsp_commands'].append('M10020000,1:00')
    edit('traditional-step')['rsp_commands'].append('s')
    edit('qmp')['qmp_commands'].append(dict(command='system_reset',arguments={}))
    edit('model')['model_tree']=record['model_tree'].replace('gate-completion = true','gate-completion = false')
    edit('clock')['final_ticks']=0; edit('guest')['guest_target_reached']=False
    edit('summary')['summary']['master']['calls']+=1
    edit('final-cpu')['final_cpus'][0]['registers']['pc']+=4
    event('input-handle','input',lambda e:e['registers'].__setitem__('r0',0))
    event('input-arg-consistent','input',lambda e:e['registers'].__setitem__('r1',e['registers']['r1']^1))
    event('input-tcb','input',lambda e:e.__setitem__('tcb_address',e['tcb_address']+216))
    event('push-stack','input',lambda e:e.__setitem__('after_stack','00'*40))
    event('table-count','input',lambda e:e['table_words'].__setitem__(1,0))
    event('publish-frame','prepared',lambda e:e.__setitem__('frame','00'*76))
    event('publish-stack','prepared',lambda e:e.__setitem__('saved_stack','00'*40))
    event('return-value','returned',lambda e:e['registers'].__setitem__('r0',1))
    event('return-pop','returned',lambda e:e['after_registers'].__setitem__('sp',e['after_registers']['sp']+4))
    event('return-rom','returned',lambda e:e['return_rom'].__setitem__('bytes','00'*32))
    event('entered-arg','entered',lambda e:e['registers'].__setitem__('r0',e['registers']['r0']^1))
    event('entered-current','entered',lambda e:e['current'].__setitem__(e['local_cpu'],0))
    event('step-cpu','returned',lambda e:e.__setitem__('step_reply','T05thread:05;'))
    event('stop-cpu','input',lambda e:e.__setitem__('thread','05'))
    event('rom','input',lambda e:e['rom_window'].__setitem__('bytes','00'*32))
    event('fault','input',lambda e:e['after_system'].__setitem__('DFSR_S',1))
    edit('quit')['quit_receipt']['acknowledged']=False
    return out


def verify(paths,output):
    require(output.resolve().is_relative_to(observer.OUTPUT) and not output.exists(),'Use new r15 replay output')
    records=[]; runs=[]
    for path in paths:
        r=json.loads(path.read_text(encoding='utf-8')); result=check_run(r)
        require(sha(path.with_suffix('.qemu.log').read_bytes()) == r['log_sha256'],'Runtime log identity differs')
        result.update(path=path.relative_to(ROOT).as_posix(),sha256=sha(path.read_bytes())); records.append(r); runs.append(result)
    require_independent(records); rejected=[]
    for name,bad in mutations(records[0]).items():
        try: check_run(bad)
        except (ValueError,KeyError,TypeError,IndexError): rejected.append(name)
        else: raise ValueError('Mutation accepted: '+name)
    result=dict(schema=1,tool='fenestra-z62-task-launch-verifier/0.1.0',runs=runs,
        verifier_sha256=sha(Path(__file__).read_bytes()),record_mutations_rejected=rejected,
        local_input_publish_pop_entry_samples_verified=True,**{n:False for n in observer.FALSE_FIELDS})
    with output.open('x',encoding='utf-8') as f: json.dump(result,f,indent=2); f.write('\n')
    return result


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--run',type=Path,action='append',required=True)
    ap.add_argument('--output',type=Path,required=True); args=ap.parse_args()
    print(json.dumps(verify([p.resolve() for p in args.run],args.output.resolve()),indent=2))
