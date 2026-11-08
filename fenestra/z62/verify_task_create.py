"""Replay original constructor traces, never a complete port/flash certification."""
import argparse
import copy
import json
import math
from pathlib import Path
import re
import observe_task_create as observer
from startup_contract import ROOT, BASE, require, sha, read_inputs
from observe_startup import stopped_thread
from observe_boot_wait import FALSE_FIELDS, build_command
from verify_boot_wait import flags, EXPERIMENTAL, DEFAULT_COMPLETIONS
from verify_task_context import check_regs, check_system, check_final_cpus
from task_create_contract import TOOL, LIMITATIONS, collect, check_pair, summarize


def allowed_command(c):
    ok=(c in ('c','g','qC','qfThreadInfo') or c.startswith(('qSupported:','qXfer:features:read:')) or
        re.fullmatch(r'Hg[0-4]|p[0-9a-f]+|m[0-9a-f]+,[0-9a-f]+|[Zz]1,[0-9a-f]+,2|vCont;s:0[1-4]',c))
    require(bool(ok),'Forbidden RSP: '+c)


def require_independent(records):
    require(len(records)>=2 and len({r['owned_pid'] for r in records})==len(records),
            'Two independent original processes required')


def check_run(r):
    require(r['schema']==1 and r['tool']==TOOL and r['completed'] is True,'Incomplete original creation trace')
    require(r['exit_code']==0 and r['owned_process_closed'] is True and 'failure' not in r and
            'quit_failure' not in r and r['close_notes']==[] and r['quit_receipt']=={'acknowledged':True},
            'Trace/process/QMP close failed')
    require(all(r.get(n) is False for n in FALSE_FIELDS+LIMITATIONS),'Scope changed')
    require(all(r[n] is True for n in ('firmware_loaded','reset_pc_initialized_by_qemu_loader','breakpoint_timing_perturbed'))
            and r['controller_loaded'] is False and r['controller_link_enabled'] is False,'Minimal boot scope changed')
    require(r['owned_shutdown']=='QMP quit; NOT camera normal shutdown','Shutdown claim changed')
    require(r['sources']=={n:sha((ROOT/n).read_bytes()) for n in observer.SOURCES},'Source identity changed')
    require(r['qemu_sha256']==observer.QEMU_SHA and sha((ROOT/observer.QEMU_REL).read_bytes())==observer.QEMU_SHA,
            'Pinned model changed')
    contract,images=collect(),read_inputs();require(r['contract']==contract,'Static original contract changed')
    require(type(r['owned_pid']) is int and r['owned_pid']>0,'Missing process identity')
    cmd=r['command'];require(len(cmd)==28,'Command length changed')
    g=re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+)',cmd[15]);q=re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+),server=on,wait=off',cmd[19])
    require(g is not None and q is not None and 1024<=int(g[1])<=65535 and 1024<=int(q[1])<=65535,
            'Bounded loopback ports required')
    require(cmd==build_command(Path('Q:/'),'minimal',int(g[1]),int(q[1])),'Original minimal command changed')
    for n in EXPERIMENTAL:require(flags(r['model_tree'],n)==['false','false'],'Experimental flag: '+n)
    for n in DEFAULT_COMPLETIONS:require(flags(r['model_tree'],n)==['true','true'],'Default completion scope: '+n)
    require(type(r['max_calls']) is int and 8<=r['max_calls']<=512 and
            1<=r['guest_target_seconds']<=6 and 30<=r['wall_limit_seconds']<=300 and
            math.isfinite(r['wall_seconds']) and 0<r['wall_seconds']<=r['wall_limit_seconds']+30,'Limits changed')
    require(r['trace_stop_reason']=='sample-bound-drained' and r['pending']==[] and
            r['max_calls']<=len(r['pairs'])<=r['max_calls']+64,'Not a complete bounded/drained sample')
    pairs=r['pairs'];events=r['events'];require(len(events)<=6*(r['max_calls']+64),'Event bound changed')
    permanent={p[k] for p in contract['roles'].values() for k in ('entry','constructed')}
    active=set(permanent);pending={};seen=set();expected_control=[f'Z1,{pc:x},2' for pc in sorted(active)]
    reads=[];previous=-1
    for index,e in enumerate(events):
        require(e['sequence']==index,'Omitted/reordered event')
        regs=e['registers'];pc=regs['pc'];p=contract['roles'][e['role']]
        check_regs(regs);check_regs(e['after_registers']);check_system(e['system'],e['role'])
        require(e['thread'] in {'master':('01','02'),'slave':('03','04')}[e['role']],'Event CPU/role mismatch')
        require(e['stop'].startswith('T05') and stopped_thread(e['stop'],e['previous_selected_thread'])==e['thread'],
                'Wrong stopped CPU')
        require(e['step_reply'].startswith('T05') and stopped_thread(e['step_reply'],'QC'+e['thread'])==e['thread'],
                'Wrong isolated-step CPU')
        require(e['image_head']==images[e['role']][:0x6C].hex() and
                e['rom_window']==dict(address=pc-16,bytes=images[e['role']][pc-BASE-16:pc-BASE+16].hex()),'Original ROM changed')
        require(type(e['model_ticks']) is int and e['model_ticks']>=previous,'Model clock regressed');previous=e['model_ticks']
        pi=e['pair_index'];pair=None
        if e['phase']=='unmatched-return':
            require(pi is None and pc in active and pc not in permanent and
                any(s['entry']['registers']['lr']&~1==pc for s in pending.values()) and
                not any(s['role']==e['role'] and s['thread']==e['thread'] and
                    s['entry']['registers']['sp']==regs['sp'] and s['entry']['registers']['lr']&~1==pc
                    for s in pending.values()),'Unmatched stop actually matches/no live return trap')
        else:
            require(type(pi) is int and 0<=pi<len(pairs),'Invalid pair index');pair=pairs[pi]
            require(pair[e['phase']]==e and pair['role']==e['role'] and pair['thread']==e['thread'],'Pair/event identity differs')
        expected_control.append('c');reads += [f'm{BASE:x},6c',f'm{pc-16:x},20','m4266008,8']
        if e['phase']=='entry':
            require(pi==len(seen) and pi not in seen and pair['sequence']==pi and pc==p['entry'],'Entry order changed')
            seen.add(pi);pending[pi]=pair
            ret=regs['lr']&~1
            require(BASE+16<=ret<BASE+len(images[e['role']])-18 and ret not in permanent,'Return outside original ROM')
            if ret not in active:expected_control.append(f'Z1,{ret:x},2');active.add(ret)
            reads += [f'm{regs["r0"]:x},38']
            require(e['after_registers']==dict(regs,pc=pc+4,sp=regs['sp']-36),'Original PUSH register effects differ')
        elif e['phase']=='constructed':
            require(pi in pending and pc==p['constructed'],'Constructed without live entry')
            require(e['after_registers']==dict(regs,pc=pc+4,r4=int.from_bytes(bytes.fromhex(e['tcb'])[8:12],'little')),
                    'Original LDR handle effects differ')
            reads += [f'm{e["tcb_address"]:x},d8',f'm{e["frame_address"]:x},4c',
                      f'm{pair["entry"]["registers"]["r0"]:x},38']
        elif e['phase']!='unmatched-return':
            require(e['phase']=='returned' and pi in pending and pc==pair['entry']['registers']['lr']&~1,'Unpaired return')
            del pending[pi]
            if pair['constructed'] is not None:reads += [f'm{pair["constructed"]["tcb_address"]:x},d8']
            require(pair['analysis']==check_pair(pair,p),'Original pair analysis changed')
        expected_control += [f'z1,{pc:x},2','vCont;s:'+e['thread'],f'Z1,{pc:x},2']
        if e['phase']=='returned' and not any(s['entry']['registers']['lr']&~1==pc for s in pending.values()):
            expected_control.append(f'z1,{pc:x},2');active.remove(pc)
    require(not pending and len(seen)==len(pairs),'Missing call/return')
    for pair in pairs:
        phases=[e['phase'] for e in events if e['pair_index']==pair['sequence']]
        require(phases==(['entry','returned'] if pair['constructed'] is None else ['entry','constructed','returned']),
                'Missing/duplicate/reordered constructor phase')
        check_pair(pair,contract['roles'][pair['role']])
    require(r['summary']==summarize(pairs,contract) and all(r['summary'][role]['successful']>0 for role in contract['roles']),
            'Summary/missing engine changed')
    require(type(r['trace_end_ticks']) is int and r['trace_end_ticks']>=previous,'Trace clock changed')
    previous=r['trace_end_ticks']
    for pause in r['pauses']:
        require(pause['phase']=='untraced' and pause['stop'].startswith('T02') and
                type(pause['ticks']) is int and pause['ticks']>previous,'Guest pause differs');previous=pause['ticks']
    require(type(r['final_ticks']) is int and r['final_ticks']>=previous and r['guest_target_reached'] is True and
            r['final_ticks']>=r['guest_target_seconds']*48000000,'Guest deadline not reached')
    require(r['final_status']=={'status':'paused','running':False},'Final state not paused')
    idle=check_final_cpus(r['final_cpus'],images,contract,r['final_ticks'])
    expected_control += [f'z1,{pc:x},2' for pc in sorted(active)]+['c']*len(r['pauses'])
    commands=r['rsp_commands']
    for c in commands:allowed_command(c)
    require([c for c in commands if c=='c' or c.startswith(('Z','z','vCont;'))]==expected_control,'Breakpoint lifecycle changed')
    actual_reads=[c for c in commands if c.startswith('m')]
    tail=[]
    for c in r['final_cpus']:
        p=contract['roles'][c['role']]['context'];reg=c['registers']
        tail += [f'm{BASE:x},6c',f'm{p["current"]:x},8',f'm{p["ready"]:x},8','m4266008,8',
                 f'm{reg["pc"]-16:x},40',f'm{reg["sp"]:x},80']
    require(actual_reads[:len(reads)]==reads and actual_reads[-len(tail):]==tail and
            actual_reads[len(reads):-len(tail)] and all(c=='m4266008,8' for c in actual_reads[len(reads):-len(tail)]),
            'Bounded read windows/order changed')
    require(commands.count('g')==2*len(events)+4 and commands.count('qC')==2*len(events),'Register/CPU coverage differs')
    require(r['rsp_controls']==['interrupt']*len(r['pauses']),'Interrupt coverage changed')
    require(r['qmp_commands']==[dict(command='qmp_capabilities',arguments={}),
        dict(command='human-monitor-command',arguments={'command-line':'info qtree'}),
        dict(command='query-status',arguments={}),dict(command='quit',arguments={})],'QMP commands changed')
    return dict(pid=r['owned_pid'],events=len(events),calls=len(pairs),summary=r['summary'],
        trace_model_seconds=r['trace_end_ticks']/48000000,final_model_seconds=r['final_ticks']/48000000,
        final_idle_engine_cpus=idle,unmatched_return_stops=sum(e['phase']=='unmatched-return' for e in events),
        **{n:False for n in LIMITATIONS+FALSE_FIELDS})


def mutations(record):
    out={}
    def changed(n):out[n]=copy.deepcopy(record);return out[n]
    changed('omitted')['events'].pop()
    changed('sequence')['events'][0]['sequence']+=1
    changed('pair')['pairs'][0]['entry']['config']='00'*56
    changed('frame')['pairs'][0]['constructed']['frame']='00'*76
    changed('return')['pairs'][0]['returned']['registers']['r0']^=1
    changed('register')['events'][0]['after_registers']['sp']+=4
    changed('cpu')['events'][0]['thread']='05'
    changed('step-cpu')['events'][0]['step_reply']='T05thread:05;'
    changed('rom')['events'][0]['rom_window']['bytes']='00'*32
    changed('system')['events'][0]['system']['DFSR_S']=1
    changed('clock')['final_ticks']=0
    changed('guest')['guest_target_reached']=False
    changed('scope')['firmware_integrated']=True
    changed('source')['sources']['fenestra/z62/task_create_contract.py']='0'*64
    changed('command')['command'].append('-nographic')
    changed('rsp-write')['rsp_commands'].append('M10020000,1:00')
    changed('traditional-step')['rsp_commands'].append('s')
    changed('breakpoint')['rsp_commands'].remove(next(c for c in record['rsp_commands'] if c.startswith('z1,')))
    changed('qmp')['qmp_commands'].append(dict(command='system_reset',arguments={}))
    changed('model')['model_tree']=record['model_tree'].replace('frame-sync = false','frame-sync = true')
    changed('pending')['pending']=[0]
    changed('summary')['summary']['master']['successful']+=1
    changed('final-cpu')['final_cpus'][0]['registers']['pc']+=4
    return out


def verify(paths,output):
    require(not output.exists() and output.resolve().is_relative_to(ROOT/'analysis'),'Use new analysis output')
    records=[];runs=[]
    for path in paths:
        record=json.loads(path.read_text(encoding='utf-8'));row=check_run(record)
        require(sha(path.with_suffix('.qemu.log').read_bytes())==record['log_sha256'],'QEMU log changed')
        row.update(path=path.relative_to(ROOT).as_posix(),sha256=sha(path.read_bytes()));records.append(record);runs.append(row)
    require_independent(records);rejected=[]
    for n,bad in mutations(records[0]).items():
        try:check_run(bad)
        except (ValueError,KeyError,TypeError,IndexError):rejected.append(n)
        else:raise ValueError('Mutation accepted: '+n)
    result=dict(schema=1,tool='fenestra-z62-task-create-verifier/0.1.0',verifier_sha256=sha(Path(__file__).read_bytes()),
        runs=runs,record_mutations_rejected=rejected,bounded_natural_constructor_samples_replayed=True,
        **{n:False for n in LIMITATIONS+FALSE_FIELDS})
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    verify([p.resolve() for p in args.run],args.output.resolve())
