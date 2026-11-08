"""Bounded wrapper -> creation -> field stores -> service0A return, NOT full start ABI."""
from collections import Counter
import struct
from startup_contract import BASE, PROFILES, read_inputs, require, instructions
from pool_calls import REGISTERS
from task_create_contract import collect as creates, bounded_read, copied_name
from task_entry_contract import collect as starts
from task_context import bounded_ram, words

TOOL='fenestra-z62-task-wrapper/0.1.3'
PHASES=('entry','call','native','constructed','created','field','start','native_start','started')
# Historical phase labels start/native_start/started mean wrapper service0A call/entry/return;
# native_start is NOT the r10/index3 first-launch API.
LIMITATIONS=('complete_task_abi_verified','complete_descriptor_layout_verified','descriptor_ownership_verified',
             'business_task_completed','task_lifetime_verified','system_mode_verified','stable_task_identity_verified',
             'native_task_failure_matrix_verified','complete_startup_api_verified','wrapper_caller_return_verified')


def collect():
    cr,st=creates(),starts();roles={}
    for role,img in read_inputs().items():
        anchor=bytes.fromhex('2de9f74f1546d2f804808eb04ff00009');at=img.find(anchor)
        require(at>=0 and img.find(anchor,at+1)<0,'Ambiguous original wrapper')
        entry=BASE+at
        for off,raw in ((0x76,'206081460f98e760c4e90108'),(0x9A,'fff7aeff11b0bde8f08f')):
            require(img[at+off:at+off+len(bytes.fromhex(raw))]==bytes.fromhex(raw),'Original wrapper store/start anchor changed')
        shared,name=struct.unpack_from('<2I',img,at+0xE6)
        require(shared==(entry-10)|1 and img[at-10:at-6]==bytes.fromhex('49680847'),'Original shared entry changed')
        api=int(instructions(img,entry+0x72,4,True)[0]['operands'].lstrip('#'),16)
        service_api=int(instructions(img,entry-6,6,True)[1]['operands'].lstrip('#'),16)
        service_code=struct.unpack_from('<I',img,service_api-BASE+0x24)[0]
        require(service_code==0x800A0200 and img[service_api-BASE:service_api-BASE+4]==bytes.fromhex('7847c046'),'Original service0A stub changed')
        needle=struct.pack('<I',st['roles'][role]['start']);ref=img.find(needle)
        require(ref>=12 and img.find(needle,ref+1)<0,'Ambiguous original kernel service table')
        table_offset=ref-12;table=struct.unpack_from('<11I',img,table_offset)
        require(table[1]==cr['roles'][role]['entry'] and table[3]==st['roles'][role]['start'],'Original service table relation differs')
        service_target=table[(service_code>>16)&0xFF]
        require(img[service_target-BASE:service_target-BASE+4]==bytes.fromhex('f0412de9'),'Original service0A entry changed')
        p=dict(role=role,points=dict(entry=entry,call=entry+0x72,native=cr['roles'][role]['entry'],
            constructed=cr['roles'][role]['constructed'],created=entry+0x76,field=entry+0x7E,
            start=entry+0x9A,native_start=service_target,started=entry+0x9E),
            create_api=api,start_veneer=entry-6,shared_entry=shared,name_address=name,service_code=service_code,
            service_table_address=BASE+table_offset,service_table_words=list(table),service_stub_address=service_api,
            service_stub_bytes=img[service_api-BASE:service_api-BASE+40].hex(),service_instructions=instructions(img,service_target,24,False),
            context=cr['roles'][role]['context'],wrapper_instructions=instructions(img,entry,0xA4,True),
            create_svc=instructions(img,api,0x20,False),start_veneer_instructions=instructions(img,entry-6,6,True))
        require(bounded_read(p,name,8),'Unbounded original name template');roles[role]=p
    return dict(schema=1,tool=TOOL,inputs=PROFILES,roles=roles,
        imports_equivalent='Raw ARM/Thumb; wrapper BLX->SVC6 constructor, Thumb veneer->SVC6 service0A (NOT r10 start/index3), original kernel/TCB anchors. No conventional import table.',
        **{n:False for n in LIMITATIONS})


def native_config(obj,cfg,shared,name,word28=0):
    require(len(cfg)==28 and len(name)==8 and cfg[0] in (0,1,2) and type(word28) is int and 0<=word28<2**32,'Unknown wrapper config/mode')
    a,b=struct.unpack_from('<2I',cfg,4)
    return struct.pack('<12I',obj,1 if cfg[0]==0 else 0x20001,shared,a,b,0,0,0,0,0,word28,cfg[0])+name


def step_effect(r,p,phase,handle=None):
    require(phase in PHASES,'Unknown original phase');pc=r['pc'];a=dict(r)
    if phase in ('entry','native','native_start'):
        mask={'entry':0x4FF7,'native':0x4FF0,'native_start':0x41F0}[phase]
        a.update(pc=pc+4,sp=r['sp']-mask.bit_count()*4)
    elif phase=='call':a.update(pc=p['create_api'],lr=pc+5,cpsr=r['cpsr']&~32)
    elif phase=='constructed':
        require(type(handle) is int,'Missing original handle load');a.update(pc=pc+4,r4=handle)
    elif phase=='created':a['pc']=pc+2
    elif phase=='field':a['pc']=pc+4
    elif phase=='start':a.update(pc=p['start_veneer'],lr=pc+5)
    elif phase=='started':a.update(pc=pc+2,sp=r['sp']+0x44)
    return a


def matching(pairs,events,role,phase,r):
    found=[]
    for s in pairs:
        if s['role']!=role or 'started' in s['stages']:continue
        e=events[s['stages']['entry']]['registers'];sp=e['sp']-104
        if phase=='native':ok=r['r0']==sp
        elif phase=='constructed':ok=r['r5']==sp
        elif phase=='native_start':ok='created' in s['stages'] and r['r0']==events[s['stages']['created']]['registers']['r0']
        else:ok=r['sp']==sp and r['r4']==e['r0'] and r['r5']==e['r2']
        if ok:found.append(s)
    require(len(found)<=1,'Ambiguous live wrapper association')
    if found:require(phase==PHASES[len(found[0]['stages'])],'Original wrapper phase out of order')
    return found[0] if found else None


def read_plan(p,phase,r,pair,events):
    plan=[]
    if phase=='constructed':plan.append(('handle_word',r['r4']+8,4))
    if pair is None:return plan
    e=r if phase=='entry' else events[pair['stages']['entry']]['registers']
    if phase=='entry':plan += [('input_config',e['r2'],28),('object_before',e['r0'],32),('stack_word28',e['sp']-64,4)]
    elif phase=='call':plan += [('native_config',r['sp'],56),('name_template',p['name_address'],8)]
    elif phase=='native':plan += [('native_config',r['r0'],56)]
    elif phase=='constructed':plan += [('native_config',r['r5'],56),('tcb',r['r4'],216),('frame',r['r0'],76)]
    elif phase in ('created','field'):plan += [('object_before',e['r0'],32)]
    elif phase in ('start','started'):plan += [('object',e['r0'],32),('input_config',e['r2'],28)]
    return plan


def check_pair(s,events,p):
    require(list(s['stages'])==list(PHASES) and s['role']==p['role'],'Incomplete original wrapper chain')
    a={k:events[v] for k,v in s['stages'].items()};e=a['entry'];r=e['registers'];cfg=bytes.fromhex(e['memory']['input_config']);obj=r['r0'];sp=r['sp']-104
    require(bounded_read(p,obj,32) and bounded_read(p,r['r2'],28) and bounded_read(p,sp,104),'Unbounded wrapper inputs')
    require(BASE+16<=r['r1']&~1<BASE+PROFILES[p['role']]['size']-18,'Unbounded original callback input')
    old_word28=int.from_bytes(bytes.fromhex(e['memory']['stack_word28']),'little')
    expected=native_config(obj,cfg,p['shared_entry'],bytes.fromhex(a['call']['memory']['name_template']),old_word28)
    for phase in ('call','native','constructed'):
        require(bytes.fromhex(a[phase]['memory']['native_config'])==expected,'Wrapper/native config differs')
    require(a['call']['registers']['r0']==sp and a['call']['registers']['sp']==sp and a['native']['registers']['r0']==sp,'Native config pointer differs')
    b=a['constructed'];br=b['registers'];tb=words(bytes.fromhex(b['memory']['tcb']),216);f=words(bytes.fromhex(b['memory']['frame']),76);cw=words(expected,56)
    require(br['sp']==a['native']['registers']['sp']-56 and br['r5']==sp and bounded_ram(p['context'],br['r4'],216) and
            bounded_ram(p['context'],br['r0'],76),'Original nested constructor frame differs')
    require(tb[3:6]==cw[:3] and tb[0xBC//4]==br['r0']==tb[0xB8//4]-76 and
            f[16]==0x33 and f[18]==p['shared_entry']&~1 and f[12]==0 and
            bytes.fromhex(b['memory']['tcb'])[204:212]==copied_name(expected),'Original nested TCB/name/frame differs')
    handle=tb[2];require(0<handle<0x80000000 and handle==int.from_bytes(bytes.fromhex(b['memory']['handle_word']),'little'),'Original TCB return word differs')
    c=a['created'];require(c['registers']['r0']==handle and c['registers']['sp']==sp and c['registers']['r4']==obj,'Original create return differs')
    before=bytes.fromhex(c['memory']['object_before']);after=bytearray(before);struct.pack_into('<I',after,0,handle)
    require(c['object_after']==after.hex(),'Original STR object return-word write differs')
    v=a['field'];vr=v['registers'];require(vr['r0']==r['r1'] and vr['r8']==cw[3] and vr['r4']==obj and vr['sp']==sp,'Original field store inputs differ')
    before=bytes.fromhex(v['memory']['object_before']);require(before[:4]==struct.pack('<I',handle) and before[12:16]==struct.pack('<I',cw[4]),'Original neighboring fields differ')
    after=bytearray(before);struct.pack_into('<2I',after,4,r['r1'],cw[3]);require(v['object_after']==after.hex(),'Original STRD callback/word08 write differs')
    for phase in ('start','started'):
        x=a[phase];ob=bytes.fromhex(x['memory']['object']);ic=bytes.fromhex(x['memory']['input_config']);ex=bytearray(cfg);struct.pack_into('<H',ex,26,handle&0xFFFF)
        require(x['registers']['sp']==sp and x['registers']['r4']==obj and ob[:16]==struct.pack('<4I',handle,r['r1'],cw[3],cw[4]) and
                ob[16]==cfg[0] and ob[20:24]==cfg[12:16] and ob[24:32]==expected[48:56] and ic==ex,'Original pre/post start initialized fields differ')
    require(a['start']['registers']['r0']==obj and a['start']['registers']['r1']==1 and
            a['native_start']['registers']['r0']==handle and a['native_start']['registers']['r1']==1,'Original nested service0A arguments differ')
    status=a['started']['registers']['r0'];require(status==0,'Outside successful original service0A-return sample')
    return dict(object_address=obj,input_config_address=r['r2'],native_config_address=sp,control_block=br['r4'],
        callback_input=r['r1'],native_return_word08=handle,mode_byte=cfg[0],name_hex=expected[48:56].hex(),
        input_label_hex=cfg[16:24].hex(),preserved_unassigned_word28=old_word28,
        service_0a_argument=1,service_0a_return=status,bounded_wrapper_initialization_verified=True,
        **{n:False for n in LIMITATIONS})


def summarize(pairs,events,c):
    out={}
    for role,p in c['roles'].items():
        rows=[check_pair(s,events,p) for s in pairs if s['role']==role]
        out[role]=dict(chains=len(rows),modes=dict(Counter(str(r['mode_byte']) for r in rows)),
            names=dict(Counter(r['name_hex'] for r in rows)),input_labels=dict(Counter(r['input_label_hex'] for r in rows)),
            callback_values=len({r['callback_input'] for r in rows}),
            **{n:False for n in LIMITATIONS})
    return out


def sample_ready(pairs,minimum):
    return (len(pairs)>=minimum and {s['role'] for s in pairs}=={'master','slave'} and
            all('started' in s['stages'] for s in pairs))
