"""r19 exact local observation replay; pending calls never imply full acceptance."""
import argparse
import copy
import json
import math
from pathlib import Path
import re
import observe_queue as o
import queue_contract as t
from startup_contract import ROOT,BASE,PROFILES,require,sha,read_inputs
from observe_startup import stopped_thread
from verify_task_context import check_regs,check_system,check_final_cpus
from verify_task_create import allowed_command,require_independent
from verify_boot_wait import EXPERIMENTAL,DEFAULT_COMPLETIONS,flags


def check_run(r):
    require(r['schema']==1 and r['tool']==t.TOOL and r['completed'] is True and
        not any(n in r for n in ('failure','quit_failure','forced_host_cleanup')),'Incomplete r19 local observation')
    require(r['exit_code']==0 and r['owned_process_closed'] is True and r['mapping_removed'] is True and
        r['close_notes']==[] and r['quit_receipt']=={'acknowledged':True},'Owned queue cleanup differs')
    require(all(r.get(n) is False for n in o.FALSE_FIELDS) and r['default_completion_logic_disabled'] is False and
        r['controller_link_enabled'] is False and r['registration_observed'] is False and r['firmware_inputs']==PROFILES,'Queue scope differs')
    require(all(r[n] is True for n in ('firmware_loaded','reset_pc_initialized_by_qemu_loader','breakpoint_timing_perturbed')) and
        r['owned_shutdown']=='QMP quit; NOT camera normal shutdown','Reset/shutdown scope differs')
    identity=o.model_identity();require({n:r[n] for n in identity}==identity,'Queue model identity differs')
    require(r['sources']=={n:sha((ROOT/n).read_bytes()) for n in o.SOURCES},'Queue source identity differs')
    c,images=t.collect(),read_inputs();require(r['contract']==c,'Original queue static contract differs')
    cmd=r['command'];require(len(cmd)==28,'Queue command length differs')
    g=re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+)',cmd[15]);q=re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+),server=on,wait=off',cmd[19])
    require(g is not None and q is not None and 1024<=int(g[1])<=65535 and 1024<=int(q[1])<=65535 and
        g[1]!=q[1] and cmd==o.command((int(g[1]),int(q[1]))),'Exact queue loopback command differs')
    for n in EXPERIMENTAL:require(flags(r['model_tree'],n)==['false','false'],'Queue experimental property differs')
    for n in DEFAULT_COMPLETIONS:require(flags(r['model_tree'],n)==['true','true'],'Queue default completion differs')
    require(type(r['owned_pid']) is int and r['owned_pid']>0 and type(r['guest_target_seconds']) is int and
        r['guest_target_seconds'] in (2,3) and r['wall_limit_seconds']==240 and math.isfinite(r['wall_seconds']) and
        0<r['wall_seconds']<=270 and r['trace_stop_reason']=='model-horizon' and 0<len(r['events'])<t.EVENT_CAP,'Queue budget/horizon differs')
    calls=[];active=t.points(c);controls=[f'Z1,{a:x},2' for a in sorted(active)];reads=[];clock=-1;pauses=list(r['pauses'])
    require(pauses and [p['after_events'] for p in pauses]==sorted(p['after_events'] for p in pauses),'Queue pause order differs')
    def pause_before(index):
        nonlocal clock
        while pauses and pauses[0]['after_events']==index:
            p=pauses.pop(0)
            require(p['stop'].startswith('T02') and type(p['ticks']) is int and p['ticks']>clock,'Queue pause/clock differs')
            require(not pauses or p['ticks']<r['guest_target_seconds']*48000000,'Observer ignored model horizon')
            clock=p['ticks'];controls.append('c');reads.append('m4266008,8')
    for index,e in enumerate(r['events']):
        pause_before(index);require(e['sequence']==index,'Missing/reordered queue event')
        role=e['role'];p=c['roles'][role];image=images[role];regs=e['registers'];pc=regs['pc'];tid=e['thread']
        check_regs(regs);check_regs(e['after_registers']);check_system(e['system'],role);check_system(e['after_system'],role)
        require(e['after_system']==e['system'],'Queue instruction changed system/fault state')
        require(tid in {'master':('01','02'),'slave':('03','04')}[role] and e['local_cpu']==(int(tid,16)-1)%2 and
            len(e['current'])==2 and all(type(x) is int and 0<=x<2**32 for x in e['current']),'Queue role/current CPU differs')
        require(pc in active and e['stop'].startswith('T05') and stopped_thread(e['stop'],e['previous_selected_thread'])==tid and
            e['step_reply'].startswith('T05') and stopped_thread(e['step_reply'],'QC'+tid)==tid,'Queue stop/step CPU differs')
        require(e['image_head']==image[:0x6c].hex() and e['rom_window']==dict(address=pc-16,
            bytes=image[pc-BASE-16:pc-BASE+16].hex()),'Original queue ROM differs')
        require(type(e['model_ticks']) is int and e['model_ticks']>=clock,'Queue clock regressed');clock=e['model_ticks']
        phase,pi=t.classify(calls,e,p);require((phase,pi)==(e['phase'],e['pair_index']),'Derived queue phase differs')
        controls.append('c');reads += [f'm{BASE:x},6c',f'm{pc-16:x},20','m4266008,8',f'm{p["context"]["current"]:x},8']
        plan=t.read_plan(calls,e,p);require(set(e['memory'])=={label for label,_,_ in plan},'Queue read labels differ')
        reads += [f'm{address:x},{size:x}' for _,address,size in plan]
        controls += [f'z1,{pc:x},2','vCont;s:'+tid,f'Z1,{pc:x},2']
        if phase=='entry':reads.append(f'm{e["after_registers"]["sp"]:x},18')
        if phase=='store':reads.append(f'm{regs["r4"]:x},8')
        if phase in ('call','nested'):
            target=e['after_registers']['pc'];require(BASE+16<=target and target+16<=BASE+len(image)-2 and e['target_rom']==
                dict(address=target,bytes=image[target-BASE:target-BASE+16].hex()),'Original queue target ROM differs')
            check_system(e['target_system'],role);reads += [f'm{target:x},10',f'm{p["context"]["current"]:x},8']
        t.ingest(calls,e,p)
    pause_before(len(r['events']));require(not pauses and r['pauses'][-1]['ticks']>=r['guest_target_seconds']*48000000,'Queue horizon pause missing')
    require(r['calls']==calls and r['summary']==t.local_summary(calls),'Rebuilt queue calls/summary differ')
    require({s['role'] for s in calls}=={'master','slave'} and all(s['entered'] is not None and s['loads'] and s['stores'] and s['nested'] for s in calls),
        'Insufficient two-engine queue sample')
    require(r['guest_target_reached'] is True and type(r['final_ticks']) is int and r['final_ticks']>=clock and
        r['final_ticks']>=r['guest_target_seconds']*48000000 and r['final_status']=={'status':'paused','running':False},'Queue final window/status differs')
    idle=check_final_cpus(r['final_cpus'],images,c,r['final_ticks'])
    controls += [f'z1,{a:x},2' for a in sorted(active)];reads.append('m4266008,8')
    for e in r['final_cpus']:
        p=c['roles'][e['role']]['context'];regs=e['registers']
        reads += [f'm{BASE:x},6c',f'm{p["current"]:x},8',f'm{p["ready"]:x},8','m4266008,8',f'm{regs["pc"]-16:x},40',f'm{regs["sp"]:x},80']
    commands=r['rsp_commands']
    for n in commands:allowed_command(n)
    require([n for n in commands if n=='c' or n.startswith(('Z','z','vCont;'))]==controls and
        [n for n in commands if n.startswith('m')]==reads,'Exact queue read/step lifecycle differs')
    require(commands.count('g')==2*len(r['events'])+4 and commands.count('qC')==2*len(r['events']) and
        r['rsp_controls']==['interrupt']*len(r['pauses']),'Queue register/interrupt coverage differs')
    require(r['qmp_commands']==[dict(command='qmp_capabilities',arguments={}),
        dict(command='human-monitor-command',arguments={'command-line':'info qtree'}),dict(command='query-status',arguments={}),
        dict(command='quit',arguments={})],'Queue QMP plan differs')
    return dict(pid=r['owned_pid'],events=len(r['events']),summary=r['summary'],final_model_seconds=r['final_ticks']/48000000,
        final_idle_engine_cpus=idle,local_queue_window_replayed=True,full_port_passed=False,
        **{n:False for n in o.FALSE_FIELDS})


def mutations(record):
    out={}
    def add(name,change):
        r=copy.deepcopy(record);change(r);out[name]=r
    def event(name,phase,change):
        e=next((e for e in record['events'] if e['phase']==phase),None)
        if e is not None:add(name,lambda r:change(r['events'][e['sequence']]))
    add('omitted',lambda r:r['events'].pop())
    add('source',lambda r:r['sources'].__setitem__('fenestra/z62/queue_contract.py','0'*64))
    add('scope',lambda r:r.__setitem__('phase1_passed',True))
    add('model',lambda r:r.__setitem__('qemu_sha256','0'*64))
    add('command',lambda r:r['command'].__setitem__(15,'tcp:0.0.0.0:1234'))
    add('guest',lambda r:r.__setitem__('guest_target_reached',False))
    add('horizon',lambda r:r['pauses'][-1].__setitem__('ticks',0))
    add('quiet',lambda r:r['pauses'][-1].__setitem__('stop','T05thread:01;'))
    add('pending',lambda r:r['calls'].clear())
    add('summary',lambda r:r['summary'].__setitem__('outer_returned',99))
    add('rsp-write',lambda r:r['rsp_commands'].append('M0,4:00000000'))
    add('traditional-step',lambda r:r['rsp_commands'].append('s'))
    add('g-audit',lambda r:r['rsp_commands'].remove('g'))
    add('step-audit',lambda r:r['rsp_commands'].remove(next(x for x in r['rsp_commands'] if x.startswith('vCont;s:'))))
    add('read-audit',lambda r:r['rsp_commands'].remove(next(x for x in r['rsp_commands'] if x.startswith('m'))))
    add('qmp',lambda r:r['qmp_commands'].append({'command':'cont','arguments':{}}))
    add('quit',lambda r:r.__setitem__('quit_receipt',{'acknowledged':False}))
    add('final-cpu',lambda r:r['final_cpus'].pop())
    event('sequence','call',lambda e:e.__setitem__('sequence',9))
    event('cpu','call',lambda e:e.__setitem__('thread','04' if e['role']=='master' else '01'))
    event('step-cpu','call',lambda e:e.__setitem__('step_reply','T05thread:05;'))
    event('rom','call',lambda e:e['rom_window'].__setitem__('bytes','00'*32))
    event('clock','call',lambda e:e.__setitem__('model_ticks',-1))
    event('system','call',lambda e:e['system'].__setitem__('DFSR',1))
    event('after-system','load',lambda e:e['after_system'].__setitem__('DFSR',1))
    event('outer-argument','call',lambda e:e['registers'].__setitem__('r1',2))
    event('outer-field','call',lambda e:e['memory'].__setitem__('object','00'*48))
    event('push','entry',lambda e:e.__setitem__('after_stack','00'*24))
    event('load-word','load',lambda e:e['after_registers'].__setitem__('r0',191))
    event('indices','load',lambda e:e['memory'].__setitem__('indices','ff'*8))
    event('saved','store',lambda e:e['memory'].__setitem__('saved','00'*24))
    event('store-source','store',lambda e:e['registers'].__setitem__('r1',191))
    event('store-memory','store',lambda e:e.__setitem__('after_indices','00'*8))
    event('slot-argument','nested',lambda e:e['registers'].__setitem__('r1',0xc3000000))
    event('nested-field','nested',lambda e:e['memory'].__setitem__('field','00'*4))
    event('nested-lr','nested',lambda e:e['after_registers'].__setitem__('lr',0))
    event('nested-isa','nested',lambda e:e['after_registers'].__setitem__('cpsr',e['after_registers']['cpsr']^32))
    event('target-rom','nested',lambda e:e['target_rom'].__setitem__('bytes','00'*16))
    event('target-current','nested',lambda e:e.__setitem__('target_current',[0,0]))
    event('target-system','nested',lambda e:e['target_system'].__setitem__('DFSR',1))
    return out


def verify(paths,output):
    output=output.resolve();require(output.is_relative_to(o.OUTPUT) and not output.exists(),'Use new r19 verification output')
    records=[json.loads(p.read_text(encoding='utf-8')) for p in paths];require_independent(records)
    stats=[check_run(r) for r in records]
    for p,r in zip(paths,records):require(sha(p.with_suffix('.qemu.log').read_bytes())==r['log_sha256'],'Queue log differs')
    rejected=[]
    for name,bad in mutations(records[0]).items():
        try:check_run(bad)
        except (ValueError,KeyError,IndexError,TypeError):rejected.append(name)
        else:raise ValueError('Queue mutation accepted: '+name)
    result=dict(tool='fenestra-z62-queue-verifier/0.1.0',runs=stats,rejected_mutations=rejected,
        local_queue_window_replayed=True,full_port_passed=False,**{n:False for n in o.FALSE_FIELDS})
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2));return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',type=Path,action='append',required=True)
    ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();verify(a.run,a.output)
