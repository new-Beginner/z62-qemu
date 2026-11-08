"""r16: same-process local creation/initialization/index3/first-entry relations."""
import struct
from startup_contract import require, read_inputs, instructions
import task_launch_contract as launch
from task_wrapper_contract import collect as wrapper_contract, native_config, step_effect
from task_create_contract import bounded_read, copied_name
from task_context import words, bounded_ram

TOOL='fenestra-z62-task-joint/0.1.1'
LIMITATIONS=launch.LIMITATIONS+('complete_descriptor_layout_verified','wrapper_caller_return_verified',
    'service0a_to_index3_direct_call_verified','all_created_tasks_launched','deletion_reuse_verified')
CAP=128
EVENT_CAP=2048
CREATE_PHASES=('create_input','create_built','create_initialized')


def collect():
    c=launch.collect(); w=wrapper_contract()
    for role,p in c['roles'].items():
        p['wrapper']=w['roles'][role]; q=p['wrapper']['points']
        p['joint_points']=dict(create_input=q['entry'],create_built=q['constructed'],create_initialized=q['started'])
        p['joint_points']['word08_store']=q['entry']+0xCA
        image=read_inputs()[role]
        require(image[q['entry']+0xCA-launch.BASE:q['entry']+0xCC-launch.BASE]==bytes.fromhex('ac60'),'Original word08 STR differs')
        p['word08_writer_instructions']=instructions(image,q['entry']+0xA4,0x2A,True)
        p['service0a_instructions']=instructions(read_inputs()[role],q['native_start'],0x11C,False)
        require(p['service_table_words'][10]==q['native_start']!=p['start'],'Distinct services differ')
    c.update(tool=TOOL,**{n:False for n in LIMITATIONS})
    c['imports_equivalent']+=' Separate wrapper creation/index1, service0A (not index3), object stores and shared LDR.'
    return c


def creation_for_input(creations,e):
    found=[s['sequence'] for s in creations if s['role']==e['role'] and s['initialized'] is not None and
           s['initialized']['sequence']<e['sequence'] and s['analysis']['control_block']==e['tcb_address'] and
           s['analysis']['handle']==e['registers']['r0']]
    require(len(found)<=1,'Ambiguous creation/reuse; not a stable identity')
    return found[0] if found else None


def classify(creations,pairs,e,p):
    pc=e['registers']['pc']; r=e['registers']; phases=[k for k,v in p['joint_points'].items() if v==pc]
    if not phases:return launch.classify(pairs,e,p)
    phase=phases[0]
    if phase=='word08_store':
        found=[s['sequence'] for s in creations if s['role']==e['role'] and s['initialized'] is not None and
               s['analysis']['object_address']==r['r5']]
        require(len(found)<=1,'Ambiguous original object update')
        return ('word08_store',found[0]) if found else ('unmatched-update',None)
    if phase=='create_input':
        require(not any(s['role']==e['role'] and s['initialized'] is None and
                        s['input']['registers']['sp']==r['sp'] for s in creations),'Overlapping live creation stack')
        return phase,len(creations)
    found=[]
    for s in creations:
        if s['role']!=e['role'] or s['initialized'] is not None:continue
        start=s['input']['registers']; sp=start['sp']-104
        ok=r['r5']==sp if phase=='create_built' else r['sp']==sp and r['r4']==start['r0']
        if ok:found.append(s)
    require(len(found)<=1,'Ambiguous original creation stack')
    if not found:return 'unmatched-construct' if phase=='create_built' else 'unmatched-initialized',None
    s=found[0]
    require((phase=='create_built' and s['built'] is None) or
            (phase=='create_initialized' and s['built'] is not None),'Creation phase out of order')
    return phase,s['sequence']


def create_plan(creations,e,p):
    phase=e['phase'];r=e['registers'];q=p['wrapper'];out=[]
    if phase in ('word08_store','unmatched-update'):out.append(('updated_object_before',r['r5'],32))
    if phase in ('create_built','unmatched-construct'):out.append(('handle_word',r['r4']+8,4))
    if phase=='create_input':
        out += [('input_config',r['r2'],28),('object_before',r['r0'],32),
                ('stack_word28',r['sp']-64,4),('name_template',q['name_address'],8)]
    elif phase=='create_built':
        out += [('native_config',r['r5'],56),('tcb',r['r4'],216),('frame',r['r0'],76)]
    elif phase=='create_initialized':
        s=creations[e['pair_index']];a=s['input']['registers']
        out += [('object',a['r0'],32),('input_config',a['r2'],28),('tcb',s['built']['registers']['r4'],216)]
    return out


def check_create(s,p):
    e,b,x=s['input'],s['built'],s['initialized'];q=p['wrapper'];r=e['registers'];sp=r['sp']-104
    cfg=bytes.fromhex(e['memory']['input_config']);template=bytes.fromhex(e['memory']['name_template'])
    expected=native_config(r['r0'],cfg,q['shared_entry'],template,int.from_bytes(bytes.fromhex(e['memory']['stack_word28']),'little'))
    require(b is not None,'Missing original construction')
    br=b['registers'];tb=words(bytes.fromhex(b['memory']['tcb']),216);f=words(bytes.fromhex(b['memory']['frame']),76)
    require(br['r5']==sp and bytes.fromhex(b['memory']['native_config'])==expected and
            bounded_ram(p['context'],br['r4'],216) and bounded_ram(p['context'],br['r0'],76),'Original joint config/TCB bound differs')
    cw=words(expected,56)
    require(tb[3:6]==cw[:3] and tb[0xBC//4]==br['r0']==tb[0xB8//4]-76 and
            f[16]==0x33 and f[18]==q['shared_entry']&~1 and f[12]==0 and
            bytes.fromhex(b['memory']['tcb'])[204:212]==copied_name(expected),'Original joint initial frame differs')
    handle=tb[2]
    require(0<handle<0x80000000 and int.from_bytes(bytes.fromhex(b['memory']['handle_word']),'little')==handle,'Original constructor handle differs')
    a=dict(control_block=br['r4'],handle=handle,object_address=r['r0'],callback=r['r1'],
           configured_entry=tb[5],mode=cfg[0],input_label_hex=cfg[16:24].hex())
    if x is not None:
        ob=bytes.fromhex(x['memory']['object']);ic=bytes.fromhex(x['memory']['input_config']);changed=bytearray(cfg)
        struct.pack_into('<H',changed,26,handle&0xFFFF)
        require(x['registers']['sp']==sp and x['registers']['r4']==r['r0'] and x['registers']['r5']==r['r2'] and
                x['registers']['r0']==0 and ob[:16]==struct.pack('<4I',handle,r['r1'],cw[3],cw[4]) and
                ob[16]==cfg[0] and ob[20:24]==cfg[12:16] and ob[24:32]==expected[48:56] and ic==changed,
                'Original initialized object/config differs')
        xt=words(bytes.fromhex(x['memory']['tcb']),216)
        require(xt[2:6]==tb[2:6],'Original initialized TCB fields differ')
    return a


def object_at(s,sequence):
    before=[e for e in s['updates'] if e['sequence']<sequence]
    return bytes.fromhex(before[-1]['updated_object_after'] if before else s['initialized']['memory']['object'])


def ingest(creations,pairs,e,p):
    phase,pi=classify(creations,pairs,e,p)
    require((phase,pi)==(e['phase'],e['pair_index']),'Derived joint phase differs')
    if phase=='create_input':
        require(len(creations)<CAP,'Creation bound exceeded')
        require(e['registers']['cpsr']&0x3F==0x33,'Outside original Thumb SVC wrapper')
        expected=step_effect(e['registers'],p['wrapper'],'entry')
        saved=[e['registers']['r'+str(n)] for n in range(13) if 0x4FF7&(1<<n)]+[e['registers']['lr']]
        require(e['after_registers']==expected and e['after_stack']==struct.pack('<12I',*saved).hex(),'Original wrapper PUSH differs')
        creations.append(dict(sequence=pi,role=e['role'],input=e,built=None,initialized=None,analysis=None,updates=[]))
    elif phase in ('create_built','create_initialized'):
        s=creations[pi];s['built' if phase=='create_built' else 'initialized']=e
        handle=int.from_bytes(bytes.fromhex(e['memory']['handle_word']),'little') if phase=='create_built' else None
        require(e['after_registers']==step_effect(e['registers'],p['wrapper'],'constructed' if phase=='create_built' else 'started',handle),
                'Original creation instruction effect differs')
        s['analysis']=check_create(s,p)
    elif phase in ('word08_store','unmatched-update'):
        before=bytes.fromhex(e['memory']['updated_object_before']);after=bytearray(before)
        struct.pack_into('<I',after,8,e['registers']['r4'])
        require(e['after_registers']==dict(e['registers'],pc=e['registers']['pc']+2) and
                e['updated_object_after']==after.hex(),'Original word08 STR memory/register effect differs')
        if pi is not None:
            s=creations[pi]
            require(before[:16]==object_at(s,e['sequence'])[:16],'Unexplained object mutation before original STR')
            s['updates'].append(e)
    elif phase in ('unmatched-construct','unmatched-initialized'):
        if phase=='unmatched-construct':
            h=int.from_bytes(bytes.fromhex(e['memory']['handle_word']),'little')
            require(e['after_registers']==step_effect(e['registers'],p['wrapper'],'constructed',h),'Unmatched original LDR differs')
        else:raise ValueError('Unmatched wrapper initialization')
    else:
        if phase=='input':
            require(len(pairs)<CAP,'Launch bound exceeded')
            require(e.get('creation_index')==creation_for_input(creations,e),'Derived creation association differs')
        launch.ingest(pairs,e,p)
        if phase in ('input','entered'):
            ci=e.get('creation_index') if phase=='input' else pairs[pi]['input'].get('creation_index')
            if ci is not None:
                s=creations[ci];a=s['analysis'];tb=words(bytes.fromhex(e['tcb']),216)
                require(tb[2]==a['handle'] and tb[3]==a['object_address'] and tb[5]==a['configured_entry'],
                        'Same-process creation/launch TCB differs')
                ob=bytes.fromhex(e['launch_object'])
                require(ob[:16]==object_at(s,e['sequence'])[:16],'Created object fields changed without observed original store')
                if phase=='entered':
                    require(e['registers']['pc']==p['wrapper']['shared_entry']&~1 and e['registers']['r1']==a['object_address'] and
                            e['after_registers']['r1']==a['callback'],'Independent shared-entry object/LDR differs')
    return phase,pi


def links(creations,pairs):
    out=[]
    for s in pairs:
        ci=s['input'].get('creation_index')
        if ci is None or not launch.complete(s):continue
        a=creations[ci]['analysis']
        require(s['role']==creations[ci]['role'],'Foreign engine joint link')
        out.append(dict(role=s['role'],creation_index=ci,launch_index=s['sequence'],**a))
    require(len({x['creation_index'] for x in out})==len(out),'Creation reused by multiple launches')
    return out


def ready(creations,pairs,minimum):
    rows=links(creations,pairs)
    return (len(rows)>=minimum and {x['role'] for x in rows}=={'master','slave'} and
            all(s['initialized'] is not None for s in creations) and pairs and all(map(launch.complete,pairs)))


def summarize(creations,pairs):
    rows=links(creations,pairs); used={x['creation_index'] for x in rows}
    return dict(joint_chains=len(rows),links=rows,creations=len(creations),launches=len(pairs),
                observed_word08_stores=sum(len(s['updates']) for s in creations),
                creations_without_observed_launch=[s['sequence'] for s in creations if s['sequence'] not in used],
                launches_without_observed_creation=[s['sequence'] for s in pairs if s['input'].get('creation_index') is None],
                launch_summary=launch.summarize(pairs),**{n:False for n in LIMITATIONS})
