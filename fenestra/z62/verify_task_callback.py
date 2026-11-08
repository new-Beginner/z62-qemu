"""Replay bounded original field/BX/first-op evidence; not full port or flash acceptance."""
import argparse
import copy
import json
import math
from pathlib import Path
import re
import observe_task_callback as observer
from startup_contract import ROOT, BASE, require, sha, read_inputs
from observe_startup import stopped_thread
from observe_boot_wait import FALSE_FIELDS, build_command
from verify_task_create import allowed_command, require_independent
from verify_boot_wait import flags, EXPERIMENTAL, DEFAULT_COMPLETIONS
from verify_task_context import check_regs, check_system, check_final_cpus
from verify_task_entry import check_first_step
from task_callback_contract import TOOL, LIMITATIONS, collect, check_prepared, check_pair, check_shared, summarize


def check_run(r):
    require(r['schema']==1 and r['tool']==TOOL and r['completed'] is True,'Incomplete callback trace')
    require(r['exit_code']==0 and r['owned_process_closed'] is True and 'failure' not in r and 'quit_failure' not in r and
            r['close_notes']==[] and r['quit_receipt']=={'acknowledged':True},'Trace/close failed')
    require(all(r.get(n) is False for n in FALSE_FIELDS+LIMITATIONS),'Scope changed')
    require(all(r[n] is True for n in ('firmware_loaded','reset_pc_initialized_by_qemu_loader','breakpoint_timing_perturbed')) and
            r['controller_loaded'] is False and r['controller_link_enabled'] is False,'Original minimal scope changed')
    require(r['owned_shutdown']=='QMP quit; NOT camera normal shutdown','Shutdown claim differs')
    require(r['sources']=={n:sha((ROOT/n).read_bytes()) for n in observer.SOURCES},'Source identity changed')
    require(r['qemu_sha256']==observer.QEMU_SHA and sha((ROOT/observer.QEMU_REL).read_bytes())==observer.QEMU_SHA,'Model changed')
    c,images=collect(),read_inputs();require(r['contract']==c,'Original static contract changed')
    cmd=r['command'];require(len(cmd)==28,'Command length changed')
    g=re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+)',cmd[15]);q=re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+),server=on,wait=off',cmd[19])
    require(g is not None and q is not None and 1024<=int(g[1])<=65535 and 1024<=int(q[1])<=65535 and g[1]!=q[1] and
            cmd==build_command(Path('Q:/'),'minimal',int(g[1]),int(q[1])),'Minimal command/endpoints changed')
    for n in EXPERIMENTAL:require(flags(r['model_tree'],n)==['false','false'],'Model experimental flag: '+n)
    for n in DEFAULT_COMPLETIONS:require(flags(r['model_tree'],n)==['true','true'],'Default completion flag: '+n)
    require(type(r['owned_pid']) is int and r['owned_pid']>0 and type(r['max_entries']) is int and 8<=r['max_entries']<=256 and
            1<=r['guest_target_seconds']<=6 and 30<=r['wall_limit_seconds']<=300 and math.isfinite(r['wall_seconds']) and
            0<r['wall_seconds']<=r['wall_limit_seconds']+30,'Observation bounds changed')
    pairs,events=r['pairs'],r['events'];require(r['trace_stop_reason']=='sample-bound-drained' and r['pending']==[] and
            r['max_entries']<=len(pairs)<r['max_entries']+64 and len(events)<=4*(r['max_entries']+64),'Not complete bounded trace')
    permanent={p['checkpoint'] for p in c['roles'].values()};active=set(permanent);pending={};seen=set();previous=-1;callbacks=0
    controls=[f'Z1,{pc:x},2' for pc in sorted(active)];reads=[]
    for index,e in enumerate(events):
        require(e['sequence']==index,'Event omitted/reordered');role=e['role'];p=c['roles'][role];reg=e['registers'];pc=reg['pc'];tid=e['thread']
        check_regs(reg);check_regs(e['after_registers']);check_system(e['system'],role)
        require(tid in {'master':('01','02'),'slave':('03','04')}[role] and e['local_cpu']==(int(tid,16)-1)%2 and len(e['current'])==2,
                'Current CPU/engine changed')
        require(e['stop'].startswith('T05') and stopped_thread(e['stop'],e['previous_selected_thread'])==tid and
                e['step_reply'].startswith('T05') and stopped_thread(e['step_reply'],'QC'+tid)==tid,'Stop/step CPU differs')
        require(e['image_head']==images[role][:0x6C].hex() and
                e['rom_window']==dict(address=pc-16,bytes=images[role][pc-BASE-16:pc-BASE+16].hex()),'Original ROM changed')
        require(type(e['model_ticks']) is int and e['model_ticks']>=previous,'Clock regressed');previous=e['model_ticks']
        controls.append('c');reads += [f'm{BASE:x},6c',f'm{pc-16:x},20','m4266008,8',f'm{p["context"]["current"]:x},8']
        pi=e['pair_index'];shared=e['phase']=='entered' and bool(reg['cpsr']&32)
        require(('callback' in e)==shared and ('callback_analysis' in e)==shared,'Missing/extra callback phase')
        if e['phase']=='prepared':
            require(type(pi) is int and pi==len(seen) and pi not in seen and pi<len(pairs),'Prepared order changed')
            pair=pairs[pi];require(pair['prepared']==e and pair['role']==role and pair['sequence']==pi and pc==p['checkpoint'],'Prepared identity changed')
            a=check_prepared(e,p);require(e['prepared_analysis']==a,'Prepared analysis changed');pending[pi]=pair;seen.add(pi)
            entry=a['entry_pc'];require(entry not in permanent,'Entry/breakpoint conflict')
            if entry not in active:controls.append(f'Z1,{entry:x},2');active.add(entry)
            reads += [f'm{e["tcb_address"]:x},d8',f'm{e["frame_address"]:x},4c']
            require(e['after_registers']==dict(reg,pc=pc+4,r0=reg['r4']),'Original MOV publish effects changed')
        else:
            matches=[i for i,s in pending.items() if s['role']==role and s['prepared']['tcb_address']==e['current'][e['local_cpu']] and
                     s['prepared']['prepared_analysis']['entry_pc']==pc]
            if e['phase']=='entered':
                require(matches==[pi] and pairs[pi]['entered']==e,'First-entry identity changed');pair=pending.pop(pi)
                require(pair['analysis']==check_pair(pair,p),'Actual entry analysis changed');reads += [f'm{e["tcb_address"]:x},d8']
                check_first_step(e)
            else:require(e['phase']=='unmatched-entry' and pi is None and matches==[] and pc in active,'Invalid unmatched entry')
        if shared:reads.append(f'm{e["callback"]["descriptor_address"]:x},8')
        controls += [f'z1,{pc:x},2','vCont;s:'+tid,f'Z1,{pc:x},2']
        if shared:
            cb=e['callback'];callbacks+=1;check_regs(cb['after_bx']);check_regs(cb['after_target'])
            require(e['callback_analysis']==check_shared(e,p),'Callback analysis changed')
            target=cb['target_rom']['address']
            require(cb['target_rom']['bytes']==images[role][target-BASE:target-BASE+16].hex(),'Original target code changed')
            for name in ('bx_reply','target_step_reply'):
                require(cb[name].startswith('T05') and stopped_thread(cb[name],'QC'+tid)==tid,'Callback step CPU changed')
            check_system(cb['target_system'],role);check_system(cb['after_system'],role)
            require(cb['target_system']==e['system'] and cb['after_system']==e['system'],'Callback system registers changed')
            controls += ['vCont;s:'+tid]*2
            reads += [f'm{target:x},10',f'm{p["context"]["current"]:x},8']
            if cb['stack_write'] is not None:
                sw=cb['stack_write'];reads.append(f'm{sw["address"]:x},{len(bytes.fromhex(sw["bytes"])):x}')
        if e['phase']=='entered' and not any(s['prepared']['prepared_analysis']['entry_pc']==pc for s in pending.values()):
            controls.append(f'z1,{pc:x},2');active.remove(pc)
    require(not pending and len(seen)==len(pairs),'Missing actual task entry')
    for s in pairs:
        require([e['phase'] for e in events if e['pair_index']==s['sequence']]==['prepared','entered'],'Duplicate/missing launch phase')
        check_pair(s,c['roles'][s['role']])
    require(r['summary']==summarize(pairs,c) and all(r['summary'][role]['callback_samples']>0 for role in c['roles']),'Summary/engine coverage changed')
    require(type(r['trace_end_ticks']) is int and r['trace_end_ticks']>=previous,'Trace clock changed');previous=r['trace_end_ticks']
    for pause in r['pauses']:
        require(pause['phase']=='untraced' and pause['stop'].startswith('T02') and pause['ticks']>previous,'Pause/deadline differs');previous=pause['ticks']
    require(type(r['final_ticks']) is int and r['final_ticks']>=previous and r['guest_target_reached'] is True and
            r['final_ticks']>=r['guest_target_seconds']*48000000 and r['final_status']=={'status':'paused','running':False},'Final window/status differs')
    idle=check_final_cpus(r['final_cpus'],images,c,r['final_ticks'])
    controls += [f'z1,{pc:x},2' for pc in sorted(active)]+['c']*len(r['pauses']);commands=r['rsp_commands']
    for cmd in commands:allowed_command(cmd)
    require([cmd for cmd in commands if cmd=='c' or cmd.startswith(('Z','z','vCont;'))]==controls,'Breakpoint/step lifecycle changed')
    tail=[]
    for e in r['final_cpus']:
        p=c['roles'][e['role']]['context'];reg=e['registers']
        tail += [f'm{BASE:x},6c',f'm{p["current"]:x},8',f'm{p["ready"]:x},8','m4266008,8',f'm{reg["pc"]-16:x},40',f'm{reg["sp"]:x},80']
    actual=[cmd for cmd in commands if cmd.startswith('m')]
    require(actual[:len(reads)]==reads and actual[-len(tail):]==tail and actual[len(reads):-len(tail)] and
            all(cmd=='m4266008,8' for cmd in actual[len(reads):-len(tail)]),'Bounded read windows changed')
    require(commands.count('g')==2*len(events)+2*callbacks+4 and commands.count('qC')==2*len(events)+2*callbacks and
            r['rsp_controls']==['interrupt']*len(r['pauses']),'Register/interrupt coverage changed')
    require(r['qmp_commands']==[dict(command='qmp_capabilities',arguments={}),dict(command='human-monitor-command',arguments={'command-line':'info qtree'}),
            dict(command='query-status',arguments={}),dict(command='quit',arguments={})],'QMP changed')
    return dict(pid=r['owned_pid'],entries=len(pairs),callback_samples=callbacks,events=len(events),
        unmatched_entry_stops=sum(e['phase']=='unmatched-entry' for e in events),summary=r['summary'],
        trace_model_seconds=r['trace_end_ticks']/48000000,final_model_seconds=r['final_ticks']/48000000,
        final_idle_engine_cpus=idle,**{n:False for n in LIMITATIONS+FALSE_FIELDS})


def mutations(record):
    out={}
    def edit(n):out[n]=copy.deepcopy(record);return out[n]
    ci=next(i for i,e in enumerate(record['events']) if 'callback' in e)
    def cb(n):return edit(n)['events'][ci]['callback']
    edit('omitted')['events'].pop();edit('pair')['pairs'][0]['prepared']['frame']='00'*76
    edit('arg')['pairs'][0]['entered']['registers']['r0']^=1;edit('slot')['events'][0]['current']=[]
    edit('cpu')['events'][0]['thread']='05';edit('step')['events'][0]['step_reply']='T05thread:05;'
    edit('rom')['events'][0]['rom_window']['bytes']='00'*32;edit('fault')['events'][0]['system']['DFSR_S']=1
    edit('scope')['firmware_integrated']=True;edit('clock')['final_ticks']=0;edit('pending')['pending']=[0]
    edit('guest')['guest_target_reached']=False;edit('source')['sources']['fenestra/z62/task_callback_contract.py']='0'*64
    edit('command')['command'].append('-nographic');edit('rsp-write')['rsp_commands'].append('M10020000,1:00')
    edit('traditional-step')['rsp_commands'].append('s');edit('qmp')['qmp_commands'].append(dict(command='system_reset',arguments={}))
    edit('model')['model_tree']=record['model_tree'].replace('frame-sync = false','frame-sync = true')
    edit('summary')['summary']['master']['callback_samples']+=1;edit('final-cpu')['final_cpus'][0]['registers']['pc']+=4
    cb('field')['descriptor']='00'*8;cb('bx-pc')['after_bx']['pc']+=2;cb('bx-isa')['after_bx']['cpsr']^=32
    cb('bx-cpu')['bx_reply']='T05thread:05;';cb('target-cpu')['target_step_reply']='T05thread:05;'
    cb('target-rom')['target_rom']['bytes']='00'*16;cb('target-effect')['after_target']['r0']^=1
    cb('target-current')['target_current']=[0,0];cb('target-system')['after_system']['IFSR_S']=1
    cb('stack-write')['stack_write']=None
    return out


def verify(paths,output):
    require(not output.exists() and output.resolve().is_relative_to(ROOT/'analysis'),'Use new analysis output');records=[];runs=[]
    for path in paths:
        record=json.loads(path.read_text(encoding='utf-8'));row=check_run(record)
        require(sha(path.with_suffix('.qemu.log').read_bytes())==record['log_sha256'],'Log identity changed')
        row.update(path=path.relative_to(ROOT).as_posix(),sha256=sha(path.read_bytes()));records.append(record);runs.append(row)
    require_independent(records);rejected=[]
    for name,bad in mutations(records[0]).items():
        try:check_run(bad)
        except (ValueError,KeyError,TypeError,IndexError):rejected.append(name)
        else:raise ValueError('Mutation accepted: '+name)
    result=dict(schema=1,tool='fenestra-z62-task-callback-verifier/0.1.0',runs=runs,record_mutations_rejected=rejected,
        verifier_sha256=sha(Path(__file__).read_bytes()),inherited_verifiers={n:sha((ROOT/'fenestra/z62'/n).read_bytes()) for n in
            ('verify_task_entry.py','verify_task_create.py','verify_task_context.py','verify_boot_wait.py')},
        bounded_natural_field_bx_first_instruction_samples_replayed=True,**{n:False for n in LIMITATIONS+FALSE_FIELDS})
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,action='append',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();verify([s.resolve() for s in a.run],a.output.resolve())
