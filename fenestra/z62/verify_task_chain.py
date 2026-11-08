"""Strict r17 stream replay, including actual shared BX/first instruction; no guest access."""
import argparse
import json
import math
from pathlib import Path
import re
import observe_task_chain as o
import task_chain_contract as t
from startup_contract import ROOT,BASE,PROFILES,require,sha,read_inputs
from observe_startup import stopped_thread
from verify_boot_wait import EXPERIMENTAL,DEFAULT_COMPLETIONS,flags
from verify_task_context import check_regs,check_system,check_final_cpus
from verify_task_create import allowed_command,require_independent
from verify_task_entry import check_first_step
from verify_task_joint import mutations as joint_mutations


def check_run(r):
    require(r['schema']==1 and r['tool']==t.TOOL and r['completed'] is True and
            not any(n in r for n in ('failure','quit_failure','forced_host_cleanup')),'Incomplete chain observation')
    require(r['exit_code']==0 and r['owned_process_closed'] is True and r['close_notes']==[] and
            r['mapping_removed'] is True and r['quit_receipt']=={'acknowledged':True},'Owned cleanup differs')
    require(all(r.get(n) is False for n in o.FALSE_FIELDS) and r['default_completion_logic_disabled'] is False and
            r['controller_link_enabled'] is False and r['firmware_inputs']==PROFILES,'Scope differs')
    require(all(r[n] is True for n in ('firmware_loaded','reset_pc_initialized_by_qemu_loader','breakpoint_timing_perturbed')) and
            r['owned_shutdown']=='QMP quit; NOT camera normal shutdown','Reset/shutdown scope differs')
    identity=o.model_identity();require({n:r[n] for n in identity}==identity,'New model identity differs')
    require(r['sources']=={n:sha((ROOT/n).read_bytes()) for n in o.SOURCES},'Source identity differs')
    c,images=t.collect(),read_inputs();require(r['contract']==c,'Original chain static contract differs')
    cmd=r['command'];require(len(cmd)==28,'Command length differs')
    g=re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+)',cmd[15]);q=re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+),server=on,wait=off',cmd[19])
    require(g is not None and q is not None and 1024<=int(g[1])<=65535 and 1024<=int(q[1])<=65535 and
            g[1]!=q[1] and cmd==o.command((int(g[1]),int(q[1]))),'Exact loopback command differs')
    for n in EXPERIMENTAL:require(flags(r['model_tree'],n)==['false','false'],'Experimental property differs')
    for n in DEFAULT_COMPLETIONS:require(flags(r['model_tree'],n)==['true','true'],'Default completion differs')
    minimum=r['minimum_joint_chains']
    require(type(r['owned_pid']) is int and r['owned_pid']>0 and type(minimum) is int and 8<=minimum<=32 and
            1<=r['guest_target_seconds']<=6 and 30<=r['wall_limit_seconds']<=300 and math.isfinite(r['wall_seconds']) and
            0<r['wall_seconds']<=r['wall_limit_seconds']+30,'Bounds differ')
    require(r['trace_stop_reason']=='sample-bound-drained' and r['pending']==[] and r['pending_creations']==[] and
            0<len(r['events'])<=t.EVENT_CAP,'Incomplete bounded chain sample')
    pairs=[];creations=[];permanent=o.permanent_points(c);active=set(permanent)
    controls=[f'Z1,{a:x},2' for a in sorted(active)];reads=[];clock=-1;callbacks=0
    for index,e in enumerate(r['events']):
        require(e['sequence']==index,'Missing/reordered chain event')
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
        phase,pi=t.classify(creations,pairs,e,p);require((phase,pi)==(e['phase'],e['pair_index']),'Derived chain phase differs')
        controls.append('c');reads += [f'm{BASE:x},6c',f'm{pc-16:x},20','m4266008,8',f'm{p["context"]["current"]:x},8']
        if phase.startswith('create_') or phase in ('unmatched-construct','unmatched-initialized','word08_store','unmatched-update'):
            plan=t.create_plan(creations,e,p)
            require(set(e['memory'])=={label for label,_,_ in plan},'Creation memory labels differ')
            for label,address,size in plan:
                require(t.bounded_read(p,address,size) and len(bytes.fromhex(e['memory'][label]))==size,'Unbounded/wrong-sized creation read')
                if BASE<=address<BASE+len(image):require(e['memory'][label]==image[address-BASE:address-BASE+size].hex(),'Original name template differs')
                reads.append(f'm{address:x},{size:x}')
            if phase=='create_input':
                require(t.launch.bounded_stack(p,regs['sp']-104,104),'Unbounded original wrapper stack')
                reads.append(f'm{e["after_registers"]["sp"]:x},30')
            if phase in ('word08_store','unmatched-update'):reads.append(f'm{regs["r5"]:x},20')
        elif phase=='input':
            reads += [f'm{p["table_global"]:x},8',f'm{e["tcb_address"]:x},d8']
            ci=t.creation_for_input(creations,e);require(e['creation_index']==ci,'Derived creation association differs')
            if ci is not None:reads.append(f'm{creations[ci]["analysis"]["object_address"]:x},20')
            else:require('launch_object' not in e,'Unexpected unassociated object read')
            reads.append(f'm{e["after_registers"]["sp"]:x},28')
        elif phase=='prepared':
            entry=t.launch.check_prepared(e,p)['entry_pc'];require(entry not in permanent,'Permanent/entry conflict')
            reads += [f'm{e["tcb_address"]:x},d8',f'm{e["frame_address"]:x},4c',f'm{regs["sp"]:x},28']
            if entry not in active:controls.append(f'Z1,{entry:x},2');active.add(entry)
        elif phase=='returned':
            target=e['after_registers']['pc'];require(BASE+16<=target<BASE+len(image)-18 and e['return_rom']==
                dict(address=target-16,bytes=image[target-BASE-16:target-BASE+16].hex()),'Actual return target ROM differs')
            reads += [f'm{regs["sp"]:x},28',f'm{target-16:x},20']
        elif phase=='entered':
            reads.append(f'm{e["tcb_address"]:x},d8');check_first_step(e)
            ci=pairs[pi]['input'].get('creation_index')
            if ci is not None:reads.append(f'm{creations[ci]["analysis"]["object_address"]:x},20')
            else:require('launch_object' not in e,'Unexpected unassociated entry read')
            if regs['cpsr']&32:reads.append(f'm{regs["r1"]:x},8')
        else:require(phase=='unmatched-entry' and pc not in permanent and pi is None,'Invalid unmatched stop')
        controls += [f'z1,{pc:x},2','vCont;s:'+tid,f'Z1,{pc:x},2']
        if 'callback' in e:
            require(phase=='entered' and regs['cpsr']&32,'Unexpected callback phase')
            cb=e['callback'];callbacks+=1
            for name in ('after_bx','after_target'):check_regs(cb[name])
            for name in ('target_system','after_system'):check_system(cb[name],role)
            for name in ('bx_reply','target_step_reply'):
                require(cb[name].startswith('T05') and stopped_thread(cb[name],'QC'+tid)==tid,'Callback step CPU differs')
            target=cb['after_bx']['pc'];require(BASE+16<=target and target+16<=BASE+len(image)-2 and cb['target_rom']==
                dict(address=target,bytes=image[target-BASE:target-BASE+16].hex()),'Original callback target ROM differs')
            reads += [f'm{target:x},10',f'm{p["context"]["current"]:x},8']
            stack=cb['stack_write']
            if stack:reads.append(f'm{stack["address"]:x},{len(bytes.fromhex(stack["bytes"])):x}')
            controls += ['vCont;s:'+tid]*2
        t.ingest(creations,pairs,e,p)
        if phase=='entered' and pc not in o.old.entry_points(pairs,c):controls.append(f'z1,{pc:x},2');active.remove(pc)
        require(index==len(r['events'])-1 or not t.ready(creations,pairs,minimum),'Observer continued beyond drained sample')
    require(t.ready(creations,pairs,minimum) and len(pairs)<=t.CAP and len(creations)<=t.CAP and
            r['pairs']==pairs and r['creations']==creations and r['summary']==t.summarize(creations,pairs),'Rebuilt chains/summary differ')
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
    require(commands.count('g')==2*len(r['events'])+2*callbacks+4 and commands.count('qC')==2*len(r['events'])+2*callbacks and
            r['rsp_controls']==['interrupt']*len(r['pauses']),'Register/interrupt coverage differs')
    require(r['qmp_commands']==[dict(command='qmp_capabilities',arguments={}),
        dict(command='human-monitor-command',arguments={'command-line':'info qtree'}),dict(command='query-status',arguments={}),
        dict(command='quit',arguments={})],'QMP command plan differs')
    return dict(pid=r['owned_pid'],events=len(r['events']),summary=r['summary'],callback_samples=callbacks,
        unmatched_construct_stops=sum(e['phase']=='unmatched-construct' for e in r['events']),
        unmatched_entry_stops=sum(e['phase']=='unmatched-entry' for e in r['events']),
        trace_model_seconds=r['trace_end_ticks']/48000000,final_model_seconds=r['final_ticks']/48000000,
        final_idle_engine_cpus=idle,local_same_process_creation_launch_bx_first_verified=True,**{n:False for n in o.FALSE_FIELDS})


def mutations(record):
    out=joint_mutations(record)
    event=next(e for e in record['events'] if 'callback' in e)
    for name,change in [
        ('descriptor',lambda e:e['callback'].__setitem__('descriptor','00'*8)),
        ('bx-pc',lambda e:e['callback']['after_bx'].__setitem__('pc',e['callback']['after_bx']['pc']+2)),
        ('bx-isa',lambda e:e['callback']['after_bx'].__setitem__('cpsr',e['callback']['after_bx']['cpsr']^32)),
        ('bx-cpu',lambda e:e['callback'].__setitem__('bx_reply','T05thread:05;')),
        ('target-cpu',lambda e:e['callback'].__setitem__('target_step_reply','T05thread:05;')),
        ('target-rom',lambda e:e['callback']['target_rom'].__setitem__('bytes','00'*16)),
        ('target-effect',lambda e:e['callback']['after_target'].__setitem__('r0',e['callback']['after_target']['r0']^1)),
        ('target-current',lambda e:e['callback'].__setitem__('target_current',[0,0])),
        ('target-system',lambda e:e['callback']['target_system'].__setitem__('DFSR_S',1)),
        ('target-after-system',lambda e:e['callback']['after_system'].__setitem__('IFSR_S',1)),
        ('callback-analysis',lambda e:e['callback_analysis'].__setitem__('field_target',0)),
        ('missing-callback',lambda e:e.pop('callback'))]:
        import copy
        r=copy.deepcopy(record);change(r['events'][event['sequence']]);out[name]=r
    return out


def verify(paths,output):
    require(output.resolve().is_relative_to(o.OUTPUT) and not output.exists(),'Use new r17 replay output')
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
    result=dict(schema=1,tool='fenestra-z62-task-chain-verifier/0.1.0',runs=runs,
        verifier_sha256=sha(Path(__file__).read_bytes()),record_mutations_rejected=rejected,
        local_same_process_creation_launch_bx_first_verified=True,**{n:False for n in o.FALSE_FIELDS})
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',type=Path,action='append',required=True)
    ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    print(json.dumps(verify([p.resolve() for p in a.run],a.output.resolve()),indent=2))
