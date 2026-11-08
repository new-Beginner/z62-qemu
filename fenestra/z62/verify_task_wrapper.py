"""Replay natural wrapper initialization samples; not complete Fenestra acceptance."""
import argparse
import copy
import json
import math
from pathlib import Path
import re
import observe_task_wrapper as observer
from startup_contract import ROOT,BASE,require,sha,read_inputs
from observe_startup import stopped_thread
from observe_boot_wait import FALSE_FIELDS,build_command
from verify_task_create import allowed_command,require_independent
from verify_boot_wait import flags,EXPERIMENTAL,DEFAULT_COMPLETIONS
from verify_task_context import check_regs,check_system,check_final_cpus
from task_wrapper_contract import TOOL,LIMITATIONS,PHASES,collect,read_plan,matching,check_pair,summarize,step_effect,bounded_read


def check_run(r):
    require(r['schema']==1 and r['tool']==TOOL and r['completed'] is True,'Incomplete wrapper trace')
    require(r['exit_code']==0 and r['owned_process_closed'] is True and 'failure' not in r and 'quit_failure' not in r and
            r['close_notes']==[] and r['quit_receipt']=={'acknowledged':True},'Trace/close failed')
    require(all(r.get(n) is False for n in FALSE_FIELDS+LIMITATIONS),'Scope changed')
    require(all(r[n] is True for n in ('firmware_loaded','reset_pc_initialized_by_qemu_loader','breakpoint_timing_perturbed')) and
            r['controller_loaded'] is False and r['controller_link_enabled'] is False and
            r['owned_shutdown']=='QMP quit; NOT camera normal shutdown','Original minimal scope changed')
    require(r['sources']=={n:sha((ROOT/n).read_bytes()) for n in observer.SOURCES},'Source identity changed')
    require(r['qemu_sha256']==observer.QEMU_SHA and sha((ROOT/observer.QEMU_REL).read_bytes())==observer.QEMU_SHA,'Model changed')
    c,images=collect(),read_inputs();require(r['contract']==c,'Static contract changed')
    cmd=r['command'];require(len(cmd)==28,'Command length changed')
    g=re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+)',cmd[15]);q=re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+),server=on,wait=off',cmd[19])
    require(g is not None and q is not None and 1024<=int(g[1])<=65535 and 1024<=int(q[1])<=65535 and g[1]!=q[1] and
            cmd==build_command(Path('Q:/'),'minimal',int(g[1]),int(q[1])),'Command/endpoints changed')
    for n in EXPERIMENTAL:require(flags(r['model_tree'],n)==['false','false'],'Experimental flag: '+n)
    for n in DEFAULT_COMPLETIONS:require(flags(r['model_tree'],n)==['true','true'],'Default completion flag: '+n)
    require(type(r['owned_pid']) is int and r['owned_pid']>0 and type(r['max_calls']) is int and 8<=r['max_calls']<=128 and
            1<=r['guest_target_seconds']<=6 and 30<=r['wall_limit_seconds']<=300 and math.isfinite(r['wall_seconds']) and
            0<r['wall_seconds']<=r['wall_limit_seconds']+30,'Bounds changed')
    ev=r['events'];require(r['trace_stop_reason']=='sample-bound-drained' and r['pending']==[] and
        r['max_calls']<=len(r['pairs'])<r['max_calls']+32 and len(ev)<=32*(r['max_calls']+32),'Incomplete bounded trace')
    active=sorted({pc for p in c['roles'].values() for pc in p['points'].values()});controls=[f'Z1,{pc:x},2' for pc in active]
    pairs=[];reads=[];previous=-1
    for index,e in enumerate(ev):
        require(e['sequence']==index,'Event omitted/reordered');role=e['role'];p=c['roles'][role];r0=e['registers'];pc=r0['pc'];phase=e['phase'];tid=e['thread']
        check_regs(r0);check_regs(e['after_registers']);check_system(e['system'],role)
        require(tid in {'master':('01','02'),'slave':('03','04')}[role] and phase in PHASES and pc==p['points'][phase] and
                r0['cpsr']&0x3F==(0x13 if phase in ('native','constructed','native_start') else 0x33),'Original phase/engine/ISA differs')
        require(e['stop'].startswith('T05') and stopped_thread(e['stop'],e['previous_selected_thread'])==tid and
                e['step_reply'].startswith('T05') and stopped_thread(e['step_reply'],'QC'+tid)==tid,'Stop/step CPU differs')
        require(e['image_head']==images[role][:0x6C].hex() and e['rom_window']==dict(address=pc-16,bytes=images[role][pc-BASE-16:pc-BASE+16].hex()),'Original ROM differs')
        require(type(e['model_ticks']) is int and e['model_ticks']>=previous,'Clock regressed');previous=e['model_ticks']
        controls += ['c'];reads += [f'm{BASE:x},6c',f'm{pc-16:x},20','m4266008,8']
        if phase=='entry':
            require(len(pairs)<r['max_calls']+32,'Preparation overflow');s=dict(sequence=len(pairs),role=role,stages={});pairs.append(s)
        else:s=matching(pairs,ev,role,phase,r0)
        require(e['pair_index']==(None if s is None else s['sequence']),'Wrapper association changed')
        if s is None:require(phase in ('native','constructed','native_start'),'Unmatched wrapper-specific phase')
        plan=read_plan(p,phase,r0,s,ev);require(set(e['memory'])=={name for name,_,_ in plan},'Read payload labels changed')
        for name,address,size in plan:
            require(bounded_read(p,address,size) and len(bytes.fromhex(e['memory'][name]))==size,'Unbounded/truncated read')
            reads.append(f'm{address:x},{size:x}')
        if s is not None:s['stages'][phase]=index
        handle=int.from_bytes(bytes.fromhex(e['memory']['handle_word']),'little') if phase=='constructed' else None
        require(e['after_registers']==step_effect(r0,p,phase,handle),'Original single-step effects differ')
        controls += [f'z1,{pc:x},2','vCont;s:'+tid,f'Z1,{pc:x},2']
        require(('object_after' in e)==(s is not None and phase in ('created','field')),'Store read coverage changed')
        if 'object_after' in e:
            require(len(bytes.fromhex(e['object_after']))==32,'Truncated post-store object');reads.append(f'm{r0["r4"]:x},20')
        if s is not None and phase=='started':
            a={k:ev[i]['registers'] for k,i in s['stages'].items()};outer_sp=a['entry']['sp']-104
            require(a['native']['sp']==a['native_start']['sp']==outer_sp-36 and
                    a['native']['r4']==a['native_start']['r4']==outer_sp,'Nested original SVC call-frame differs')
            s['analysis']=check_pair(s,ev,p)
    require(pairs==r['pairs'] and all(list(s['stages'])==list(PHASES) for s in pairs),'Missing/reordered wrapper phases')
    require(r['summary']==summarize(pairs,ev,c) and all(r['summary'][role]['chains']>0 for role in c['roles']),'Summary/engine coverage differs')
    require(type(r['trace_end_ticks']) is int and r['trace_end_ticks']>=previous,'Trace clock differs');previous=r['trace_end_ticks']
    for pause in r['pauses']:
        require(pause['phase']=='untraced' and pause['stop'].startswith('T02') and pause['ticks']>previous,'Pause differs');previous=pause['ticks']
    require(type(r['final_ticks']) is int and r['final_ticks']>=previous and r['guest_target_reached'] is True and
            r['final_ticks']>=r['guest_target_seconds']*48000000 and r['final_status']=={'status':'paused','running':False},'Final window differs')
    idle=check_final_cpus(r['final_cpus'],images,c,r['final_ticks']);controls += [f'z1,{pc:x},2' for pc in active]+['c']*len(r['pauses'])
    commands=r['rsp_commands']
    for cmd in commands:allowed_command(cmd)
    require([cmd for cmd in commands if cmd=='c' or cmd.startswith(('Z','z','vCont;'))]==controls,'Breakpoint/step lifecycle changed')
    tail=[]
    for e in r['final_cpus']:
        p=c['roles'][e['role']]['context'];reg=e['registers'];tail += [f'm{BASE:x},6c',f'm{p["current"]:x},8',f'm{p["ready"]:x},8','m4266008,8',f'm{reg["pc"]-16:x},40',f'm{reg["sp"]:x},80']
    actual=[cmd for cmd in commands if cmd.startswith('m')]
    require(actual[:len(reads)]==reads and actual[-len(tail):]==tail and actual[len(reads):-len(tail)] and
            all(cmd=='m4266008,8' for cmd in actual[len(reads):-len(tail)]),'Bounded read windows changed')
    require(commands.count('g')==2*len(ev)+4 and commands.count('qC')==2*len(ev) and r['rsp_controls']==['interrupt']*len(r['pauses']),'Register/interrupt coverage changed')
    require(r['qmp_commands']==[dict(command='qmp_capabilities',arguments={}),dict(command='human-monitor-command',arguments={'command-line':'info qtree'}),
            dict(command='query-status',arguments={}),dict(command='quit',arguments={})],'QMP changed')
    return dict(pid=r['owned_pid'],chains=len(pairs),events=len(ev),unmatched_kernel_stops=sum(e['pair_index'] is None for e in ev),summary=r['summary'],
        trace_model_seconds=r['trace_end_ticks']/48000000,final_model_seconds=r['final_ticks']/48000000,final_idle_engine_cpus=idle,
        **{n:False for n in LIMITATIONS+FALSE_FIELDS})


def mutations(record):
    out={}
    def edit(name):out[name]=copy.deepcopy(record);return out[name]
    def event(name,phase):
        r=edit(name);return r['events'][r['pairs'][0]['stages'][phase]]
    edit('omitted')['events'].pop();edit('pair')['pairs'][0]['stages'].pop('field')
    event('config','call')['memory']['native_config']='00'*56;event('tcb','constructed')['memory']['tcb']='00'*216
    event('name','call')['memory']['name_template']='ff'*8;event('frame','constructed')['memory']['frame']='00'*76
    event('create-return','created')['registers']['r0']^=1;event('store-word','created')['object_after']='00'*32
    event('field-input','field')['registers']['r0']^=2;event('store-field','field')['object_after']='00'*32
    event('start-arg','native_start')['registers']['r1']=0;event('start-return','started')['registers']['r0']=1
    event('cfg-low16','started')['memory']['input_config']='00'*28;event('object-name','started')['memory']['object']='00'*32
    x=event('stack-word28','entry')['memory'];x['stack_word28']=(int.from_bytes(bytes.fromhex(x['stack_word28']),'little')^1).to_bytes(4,'little').hex()
    x=event('service-foreign-sp','native_start');x['registers']['sp']+=4;x['after_registers']['sp']+=4
    event('cpu','entry')['thread']='05';event('step-cpu','entry')['step_reply']='T05thread:05;'
    event('step','field')['after_registers']['r0']^=1;event('rom','entry')['rom_window']['bytes']='00'*32
    event('fault','entry')['system']['DFSR_S']=1;edit('scope')['firmware_integrated']=True
    edit('clock')['final_ticks']=0;edit('pending')['pending']=[0];edit('guest')['guest_target_reached']=False
    edit('source')['sources']['fenestra/z62/task_wrapper_contract.py']='0'*64;edit('command')['command'].append('-nographic')
    edit('rsp-write')['rsp_commands'].append('M10020000,1:00');edit('traditional-step')['rsp_commands'].append('s')
    edit('qmp')['qmp_commands'].append(dict(command='system_reset',arguments={}));edit('model')['model_tree']=record['model_tree'].replace('frame-sync = false','frame-sync = true')
    edit('summary')['summary']['master']['chains']+=1;edit('final-cpu')['final_cpus'][0]['registers']['pc']+=4
    return out


def verify(paths,output):
    require(not output.exists() and output.resolve().is_relative_to(ROOT/'analysis'),'Use new analysis output');records=[];runs=[]
    for path in paths:
        record=json.loads(path.read_text(encoding='utf-8'));row=check_run(record)
        require(sha(path.with_suffix('.qemu.log').read_bytes())==record['log_sha256'],'Log changed')
        row.update(path=path.relative_to(ROOT).as_posix(),sha256=sha(path.read_bytes()));records.append(record);runs.append(row)
    require_independent(records);rejected=[]
    for name,bad in mutations(records[0]).items():
        try:check_run(bad)
        except (ValueError,KeyError,TypeError,IndexError):rejected.append(name)
        else:raise ValueError('Mutation accepted: '+name)
    result=dict(schema=1,tool='fenestra-z62-task-wrapper-verifier/0.1.4',runs=runs,record_mutations_rejected=rejected,
        verifier_sha256=sha(Path(__file__).read_bytes()),inherited_verifiers={n:sha((ROOT/'fenestra/z62'/n).read_bytes()) for n in ('verify_task_create.py','verify_task_context.py','verify_boot_wait.py')},
        bounded_original_wrapper_initialization_samples_replayed=True,**{n:False for n in LIMITATIONS+FALSE_FIELDS})
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,action='append',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();verify([x.resolve() for x in a.run],a.output.resolve())
