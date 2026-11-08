"""r18 exact read-only record replay; no QEMU or physical access."""
import argparse
import copy
import json
import math
from pathlib import Path
import re
import observe_business as o
import business_contract as t
from startup_contract import ROOT,BASE,PROFILES,require,sha,read_inputs
from observe_startup import stopped_thread
from verify_boot_wait import EXPERIMENTAL,DEFAULT_COMPLETIONS,flags
from verify_task_context import check_regs,check_system,check_final_cpus
from verify_task_create import allowed_command,require_independent


def check_run(r):
    require(r['schema']==1 and r['tool']==t.TOOL and r['completed'] is True and
        not any(n in r for n in ('failure','quit_failure','forced_host_cleanup')),'Incomplete business observation')
    require(r['exit_code']==0 and r['owned_process_closed'] is True and r['close_notes']==[] and
        r['mapping_removed'] is True and r['quit_receipt']=={'acknowledged':True},'Owned cleanup differs')
    require(all(r.get(n) is False for n in o.FALSE_FIELDS) and r['default_completion_logic_disabled'] is False and
        r['controller_link_enabled'] is False and r['firmware_inputs']==PROFILES,'Scope differs')
    require(all(r[n] is True for n in ('firmware_loaded','reset_pc_initialized_by_qemu_loader','breakpoint_timing_perturbed')) and
        r['owned_shutdown']=='QMP quit; NOT camera normal shutdown','Reset/shutdown scope differs')
    identity=o.model_identity();require({n:r[n] for n in identity}==identity,'New model identity differs')
    require(r['sources']=={n:sha((ROOT/n).read_bytes()) for n in o.SOURCES},'Source identity differs')
    c,images=t.collect(),read_inputs();require(r['contract']==c,'Original business static contract differs')
    cmd=r['command'];require(len(cmd)==28,'Command length differs')
    g=re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+)',cmd[15]);q=re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+),server=on,wait=off',cmd[19])
    require(g is not None and q is not None and 1024<=int(g[1])<=65535 and 1024<=int(q[1])<=65535 and
        g[1]!=q[1] and cmd==o.command((int(g[1]),int(q[1]))),'Exact loopback command differs')
    for n in EXPERIMENTAL:require(flags(r['model_tree'],n)==['false','false'],'Experimental property differs')
    for n in DEFAULT_COMPLETIONS:require(flags(r['model_tree'],n)==['true','true'],'Default completion differs')
    minimum=r['minimum_returned_calls']
    require(type(r['owned_pid']) is int and r['owned_pid']>0 and type(minimum) is int and 8<=minimum<=32 and
        1<=r['guest_target_seconds']<=6 and 30<=r['wall_limit_seconds']<=300 and math.isfinite(r['wall_seconds']) and
        0<r['wall_seconds']<=r['wall_limit_seconds']+30,'Bounds differ')
    require(r['trace_stop_reason']=='sample-bound-drained' and r['pending_registrations']==[] and r['pending_calls']==[] and
        0<len(r['events'])<=t.EVENT_CAP,'Incomplete bounded business sample')
    rows=[];calls=[];active=t.points(c);controls=[f'Z1,{a:x},2' for a in sorted(active)];reads=[];clock=-1
    for index,e in enumerate(r['events']):
        require(e['sequence']==index,'Missing/reordered business event')
        role=e['role'];p=c['roles'][role];image=images[role];regs=e['registers'];pc=regs['pc'];tid=e['thread']
        check_regs(regs);check_regs(e['after_registers']);check_system(e['system'],role);check_system(e['after_system'],role)
        require(e['after_system']==e['system'],'Original single instruction changed fault/system state')
        require(tid in {'master':('01','02'),'slave':('03','04')}[role] and e['local_cpu']==(int(tid,16)-1)%2 and
            len(e['current'])==2 and all(type(x) is int and 0<=x<2**32 for x in e['current']),'Role/current CPU differs')
        require(pc in active and e['stop'].startswith('T05') and stopped_thread(e['stop'],e['previous_selected_thread'])==tid and
            e['step_reply'].startswith('T05') and stopped_thread(e['step_reply'],'QC'+tid)==tid,'Stop/isolated-step CPU differs')
        require(e['image_head']==image[:0x6C].hex() and e['rom_window']==
            dict(address=pc-16,bytes=image[pc-BASE-16:pc-BASE+16].hex()),'Original ROM differs')
        require(type(e['model_ticks']) is int and e['model_ticks']>=clock,'Model clock regressed');clock=e['model_ticks']
        d,phase,pi=t.classify(rows,calls,e,p)
        require((phase,d['kind'],pi)==(e['phase'],e['kind'],e['pair_index']),'Derived business phase differs')
        controls.append('c');reads += [f'm{BASE:x},6c',f'm{pc-16:x},20','m4266008,8',f'm{p["context"]["current"]:x},8']
        plan=t.read_plan(rows,calls,e,p)
        require(set(e['memory'])=={label for label,_,_ in plan},'Business memory labels differ')
        for label,address,size in plan:
            require(t.bounded_read(p,address,size) and len(bytes.fromhex(e['memory'][label]))==size,'Unbounded/wrong-sized read')
            reads.append(f'm{address:x},{size:x}')
        controls += [f'z1,{pc:x},2','vCont;s:'+tid,f'Z1,{pc:x},2']
        if phase=='register':
            address=e['after_registers']['sp'];require(t.bounded_stack(p,address,24),'Unbounded actual setter PUSH')
            reads.append(f'm{address:x},18')
        elif phase=='store':reads.append(f'm{regs["r4"]:x},30')
        elif phase=='call':
            target=e['after_registers']['pc'];require(BASE+16<=target and target+16<=BASE+len(image)-2 and e['target_rom']==
                dict(address=target,bytes=image[target-BASE:target-BASE+16].hex()),'Original business target ROM differs')
            check_system(e['target_system'],role)
            reads += [f'm{target:x},10',f'm{p["context"]["current"]:x},8']
        t.ingest(rows,calls,e,p)
        require(index==len(r['events'])-1 or not t.ready(rows,calls,minimum),'Observer continued beyond drained sample')
    require(t.ready(rows,calls,minimum) and len(rows)<=t.CAP and len(calls)<=t.CAP and
        r['registrations']==rows and r['calls']==calls and r['summary']==t.summarize(rows,calls),'Rebuilt business chains/summary differ')
    require(type(r['trace_end_ticks']) is int and r['trace_end_ticks']>=clock,'Trace end clock differs');clock=r['trace_end_ticks']
    for pause in r['pauses']:
        require(pause['phase']=='untraced' and pause['stop'].startswith('T02') and pause['ticks']>clock,'Pause/deadline differs');clock=pause['ticks']
    require(r['guest_target_reached'] is True and type(r['final_ticks']) is int and r['final_ticks']>=clock and
        r['final_ticks']>=r['guest_target_seconds']*48000000 and r['final_status']=={'status':'paused','running':False},'Final window/status differs')
    idle=check_final_cpus(r['final_cpus'],images,c,r['final_ticks'])
    controls += [f'z1,{a:x},2' for a in sorted(active)]+['c']*len(r['pauses']);commands=r['rsp_commands']
    for item in commands:allowed_command(item)
    require([n for n in commands if n=='c' or n.startswith(('Z','z','vCont;'))]==controls,'Breakpoint/step lifecycle differs')
    tail=[]
    for e in r['final_cpus']:
        p=c['roles'][e['role']]['context'];regs=e['registers']
        tail += [f'm{BASE:x},6c',f'm{p["current"]:x},8',f'm{p["ready"]:x},8','m4266008,8',f'm{regs["pc"]-16:x},40',f'm{regs["sp"]:x},80']
    actual=[n for n in commands if n.startswith('m')]
    require(actual[:len(reads)]==reads and actual[-len(tail):]==tail and actual[len(reads):-len(tail)] and
        all(n=='m4266008,8' for n in actual[len(reads):-len(tail)]),'Exact bounded memory read plan differs')
    require(commands.count('g')==2*len(r['events'])+4 and commands.count('qC')==2*len(r['events']) and
        r['rsp_controls']==['interrupt']*len(r['pauses']),'Register/interrupt coverage differs')
    require(r['qmp_commands']==[dict(command='qmp_capabilities',arguments={}),
        dict(command='human-monitor-command',arguments={'command-line':'info qtree'}),dict(command='query-status',arguments={}),
        dict(command='quit',arguments={})],'QMP command plan differs')
    return dict(pid=r['owned_pid'],events=len(r['events']),summary=r['summary'],
        trace_model_seconds=r['trace_end_ticks']/48000000,final_model_seconds=r['final_ticks']/48000000,
        final_idle_engine_cpus=idle,bounded_registered_business_return_verified=True,**{n:False for n in o.FALSE_FIELDS})


def mutations(record):
    out={}
    def add(name,change):
        r=copy.deepcopy(record);change(r);out[name]=r
    def event(name,phase,change):
        i=next(e['sequence'] for e in record['events'] if e['phase']==phase)
        add(name,lambda r:change(r['events'][i]))
    add('omitted',lambda r:r['events'].pop())
    add('source',lambda r:r['sources'].__setitem__('fenestra/z62/business_contract.py','0'*64))
    add('scope',lambda r:r.__setitem__('message_semantics_verified',True))
    add('model',lambda r:r.__setitem__('qemu_sha256','0'*64))
    add('command',lambda r:r['command'].__setitem__(15,'tcp:0.0.0.0:1234'))
    add('pending',lambda r:r['pending_calls'].append(0))
    add('summary',lambda r:r['summary']['master'].__setitem__('calls',999))
    add('rsp-write',lambda r:r['rsp_commands'].append('M10020000,4:00000000'))
    add('traditional-step',lambda r:r['rsp_commands'].append('s'))
    add('qmp',lambda r:r['qmp_commands'].append(dict(command='cont',arguments={})))
    add('quit',lambda r:r.__setitem__('quit_receipt',{'acknowledged':False}))
    add('model-tree',lambda r:r.__setitem__('model_tree',r['model_tree'].replace('gate-completion = true','gate-completion = false')))
    event('sequence','register',lambda e:e.__setitem__('sequence',999))
    event('cpu','register',lambda e:e.__setitem__('thread','05'))
    event('step-cpu','store',lambda e:e.__setitem__('step_reply','T05thread:05;'))
    event('rom','call',lambda e:e['rom_window'].__setitem__('bytes','00'*32))
    event('clock','store',lambda e:e.__setitem__('model_ticks',-1))
    event('system','call',lambda e:e['system'].__setitem__('DFSR_S',1))
    event('after-system','store',lambda e:e['after_system'].__setitem__('IFSR_S',1))
    event('setter-push','register',lambda e:e.__setitem__('after_stack','00'*24))
    event('setter-source','store',lambda e:e['registers'].__setitem__('r6',e['registers']['r6']^1))
    event('strd-memory','store',lambda e:e.__setitem__('after_object','00'*48))
    event('saved-stack','store',lambda e:e['memory'].__setitem__('saved_stack','00'*24))
    event('field','call',lambda e:e['memory'].__setitem__('object','00'*48))
    event('message','call',lambda e:e['memory'].__setitem__('message_slot','ffffffff'))
    event('tcb','call',lambda e:e['memory'].__setitem__('tcb','00'*32))
    event('blx-lr','call',lambda e:e['after_registers'].__setitem__('lr',0))
    event('blx-isa','call',lambda e:e['after_registers'].__setitem__('cpsr',e['after_registers']['cpsr']^32))
    event('blx-parameter','call',lambda e:e['after_registers'].__setitem__('r0',e['after_registers']['r0']^1))
    event('target-rom','call',lambda e:e['target_rom'].__setitem__('bytes','00'*16))
    event('target-current','call',lambda e:e.__setitem__('target_current',[0,0]))
    event('target-system','call',lambda e:e['target_system'].__setitem__('DFSR_S',1))
    event('return-register','returned',lambda e:e['registers'].__setitem__('r8',e['registers']['r8']^1))
    event('return-tcb','returned',lambda e:e.__setitem__('current',[0,0]))
    event('return-branch','returned',lambda e:e['after_registers'].__setitem__('pc',e['after_registers']['pc']+2))
    return out


def verify(paths,output):
    require(output.resolve().is_relative_to(o.OUTPUT) and not output.exists(),'Use new r18 replay output')
    records=[];runs=[]
    for path in paths:
        r=json.loads(path.read_text(encoding='utf-8'));result=check_run(r)
        require(sha(path.with_suffix('.qemu.log').read_bytes())==r['log_sha256'],'Runtime log differs')
        result.update(path=path.relative_to(ROOT).as_posix(),sha256=sha(path.read_bytes()));runs.append(result);records.append(r)
    require_independent(records);rejected=[]
    for name,bad in mutations(records[0]).items():
        try:check_run(bad)
        except (ValueError,KeyError,TypeError,IndexError):rejected.append(name)
        else:raise ValueError('Mutation accepted: '+name)
    result=dict(schema=1,tool='fenestra-z62-business-verifier/0.1.0',runs=runs,
        verifier_sha256=sha(Path(__file__).read_bytes()),record_mutations_rejected=rejected,
        bounded_registered_business_return_verified=True,**{n:False for n in o.FALSE_FIELDS})
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',type=Path,action='append',required=True)
    ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    print(json.dumps(verify([p.resolve() for p in a.run],a.output.resolve()),indent=2))
