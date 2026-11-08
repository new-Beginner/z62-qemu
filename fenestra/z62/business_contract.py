"""r18 finite original setter/STRD -> dispatch BLX -> return-loop contract."""
from collections import Counter
import struct
from startup_contract import BASE,PROFILES,read_inputs,require,instructions
from task_launch_contract import collect as launch_collect,bounded_stack,LIMITATIONS as OLD_LIMITATIONS
from task_create_contract import bounded_read
from task_context import bounded_ram
from pool_calls import REGISTERS

TOOL='fenestra-z62-business/0.1.0'
CAP=128
EVENT_CAP=1024
STARTS={'master':(0x1035C940,0x103A2890),'slave':(0x1005E9E4,0x1006A7F4)}
SHARED={'master':0x103DEBBC,'slave':0x1006CB80}
WRAPPER={'master':0x103DEBC6,'slave':0x1006CB8A}
SAVED=('r4','r5','r6','r7','r8','lr')
LIMITATIONS=tuple(sorted(set(OLD_LIMITATIONS+('all_business_callbacks_return_verified',
    'business_callback_return_verified','message_semantics_verified','registration_ownership_verified',
    'complete_descriptor_layout_verified','complete_business_task_list_verified','deletion_reuse_verified',
    'same_creation_launch_business_chain_verified'))))


def collect():
    c=launch_collect()
    for role,image in read_inputs().items():
        p=c['roles'][role];rows=[]
        signature=bytes.fromhex('08b500f120050446002000906a46a16a')
        found=[];off=-1
        while True:
            off=image.find(signature,off+1)
            if off<0:break
            found.append(BASE+off)
        require(tuple(found)==STARTS[role],'Original dispatcher identities differ')
        for kind,start in enumerate(found,1):
            size=30 if kind==1 else 32;setter=start+size;code=instructions(image,start,size,True)
            setup=instructions(image,setter,40,True);call=start+size-4
            require(code[-2]['bytes']==('8847' if kind==1 else '9047') and code[-1]['mnemonic']=='b' and
                code[-1]['operands']==f'#{hex(start+12)}','Original dispatch BLX/loop differs')
            require(setup[0]['bytes']=='2de9f041' and setup[8]['bytes']=='c4e90967' and
                setup[-1]['mnemonic']=='b.w' and setup[-1]['operands']==f'#{hex(WRAPPER[role])}',
                'Original setter STRD/wrapper branch differs')
            ldr=setup[-2];disp=int(ldr['operands'].split('#')[1].split(']')[0],0)
            literal=((ldr['address']+4)&~3)+disp
            require(int.from_bytes(image[literal-BASE:literal-BASE+4],'little')==start|1,'Setter dispatch literal differs')
            rows.append(dict(kind=kind,start=start,loop=start+12,call=call,returned=call+2,
                target_register='r1' if kind==1 else 'r2',setter=setter,store=setter+22,
                instructions=code,setter_instructions=setup,dispatch_literal_address=literal,
                dispatch_literal_bytes=image[literal-BASE:literal-BASE+4].hex()))
        p.update(dispatchers=rows,shared_entry=SHARED[role])
    c.update(tool=TOOL,imports_equivalent='Raw ARM/Thumb: original setters/prologue/STRD, literal dispatch targets, field loads/BLX and loop branches; no dynamic import table; not a complete SDK.',
        **{n:False for n in LIMITATIONS})
    return c


def points(c):
    return {d[n] for p in c['roles'].values() for d in p['dispatchers'] for n in ('setter','store','call','returned')}


def descriptor(p,pc):
    matches=[(d,phase) for d in p['dispatchers'] for phase,key in
        (('register','setter'),('store','store'),('call','call'),('returned','returned')) if pc==d[key]]
    require(len(matches)==1,'Unknown/ambiguous business breakpoint')
    return matches[0]


def blx_effect(r,register):
    target=r[register];pc=target&~1
    require(target!=0 and (target&1 or pc%4==0),'Invalid original BLX target')
    return dict(r,pc=pc,lr=(r['pc']+2)|1,cpsr=(r['cpsr']&~32)|(32 if target&1 else 0))


def check_store_effect(before,after,raw,updated):
    expected=raw[:36]+struct.pack('<2I',before['r6'],before['r7'])+raw[44:]
    require(len(raw)==48 and len(updated)==48 and updated==expected and
        after==dict(before,pc=before['pc']+4),'Original STRD memory/register effect differs')


def check_arguments(r,kind,obj,message,target):
    require(kind in (1,2) and r['r4']==obj and r['r5']==obj+32,'Dispatch object registers differ')
    require((r['r0']==message and r['r1']==target) if kind==1 else
        (r['r0']==obj and r['r1']==message and r['r2']==target),'Original dispatch signature/arguments differ')


def registration_for(rows,role,kind,obj,sequence):
    candidates=[i for i,s in enumerate(rows) if s['role']==role and s['kind']==kind and
        s['object_address']==obj and s['sequence']<sequence]
    if not candidates:return None
    i=max(candidates,key=lambda i:rows[i]['sequence']);s=rows[i]
    require(s['stored'] is not None and s['stored']['sequence']<sequence,'Call during incomplete registration')
    return i


def classify(rows,calls,e,p):
    d,phase=descriptor(p,e['registers']['pc']);r=e['registers'];role=e['role']
    if phase=='register':return d,phase,None
    if phase=='store':
        candidates=[i for i,s in enumerate(rows) if s['stored'] is None and s['role']==role and s['kind']==d['kind'] and
            s['input']['registers']['sp']-24==r['sp'] and s['object_address']==r['r4']]
    elif phase=='call':return d,phase,registration_for(rows,role,d['kind'],r['r4'],e['sequence'])
    else:
        tb=e['current'][e['local_cpu']]
        candidates=[i for i,s in enumerate(calls) if s['returned'] is None and s['role']==role and s['kind']==d['kind'] and
            s['called']['registers']['sp']==r['sp'] and s['tcb_address']==tb and s['object_address']==r['r4']]
    require(len(candidates)==1,'Unpaired/ambiguous original business '+phase)
    return d,phase,candidates[0]


def read_plan(rows,calls,e,p):
    r=e['registers'];phase=e['phase']
    if phase=='register':return [('object',r['r0'],48)]
    if phase=='store':return [('object',r['r4'],48),('saved_stack',r['sp'],24)]
    tb=e['current'][e['local_cpu']]
    require(bounded_ram(p['context'],tb,32),'Unbounded current business TCB')
    return [('object',r['r4'],48),('message_slot',r['sp'],4),('tcb',tb,32)]


def ingest(rows,calls,e,p):
    r=e['registers'];a=e['after_registers'];d,phase,i=classify(rows,calls,e,p)
    require((e['phase'],e['kind'],e['pair_index'])==(phase,d['kind'],i),'Derived business phase differs')
    require(r['cpsr']&0x3F==0x33,'Business point is not original Thumb SVC')
    require(set(e['memory'])=={label for label,_,_ in read_plan(rows,calls,e,p)},'Business read labels differ')
    for label,address,size in read_plan(rows,calls,e,p):
        require(bounded_read(p,address,size) and len(bytes.fromhex(e['memory'][label]))==size,'Unbounded/wrong-sized business read')
    raw=bytes.fromhex(e['memory']['object'])
    if phase=='register':
        require(len(rows)<CAP and bounded_stack(p,r['sp']-24,24),'Registration/stack bound exceeded')
        target=r['r1']&~1
        require(BASE+16<=target and target+16<=BASE+PROFILES[e['role']]['size']-2 and
            (r['r1']&1 or target%4==0),'Registration callback outside original ROM')
        require(a==dict(r,pc=r['pc']+4,sp=r['sp']-24) and
            e['after_stack']==struct.pack('<6I',*(r[n] for n in SAVED)).hex(),'Original setter PUSH effect differs')
        require(not any(s['stored'] is None and s['role']==e['role'] and s['object_address']==r['r0'] for s in rows),
            'Overlapping registration of same object')
        rows.append(dict(sequence=e['sequence'],role=e['role'],kind=d['kind'],object_address=r['r0'],input=e,stored=None))
    elif phase=='store':
        s=rows[i];b=s['input']['registers']
        require(all(r[n]==v for n,v in dict(r4=b['r0'],r5=b['r3'],r6=b['r1'],r7=b['r2']).items()) and
            e['memory']['saved_stack']==s['input']['after_stack'],'Setter source/saved stack differs')
        check_store_effect(r,a,raw,bytes.fromhex(e['after_object']));s['stored']=e
    elif phase=='call':
        require(len(calls)<CAP and bounded_stack(p,r['sp'],4),'Business call/stack bound exceeded')
        tb=e['current'][e['local_cpu']];words=struct.unpack('<8I',bytes.fromhex(e['memory']['tcb']))
        require(words[3]==r['r4'] and words[5]==p['shared_entry']|1 and
            int.from_bytes(raw[4:8],'little')==d['start']|1,'Original TCB/object/dispatcher relation differs')
        message=int.from_bytes(bytes.fromhex(e['memory']['message_slot']),'little')
        field=int.from_bytes(raw[36:40],'little');check_arguments(r,d['kind'],r['r4'],message,field)
        if i is not None:
            original=bytes.fromhex(rows[i]['stored']['after_object'])
            require(raw[36:44]==original[36:44] and field==rows[i]['input']['registers']['r1'],
                'Registration/independent call field differs')
        require(a==blx_effect(r,d['target_register']),'Actual business BLX PC/ISA/LR/arguments differ')
        require(e['target_current']==e['current'] and e['target_system']==e['system'],'Business BLX current/system differs')
        require(not any(s['returned'] is None and s['role']==e['role'] and s['tcb_address']==tb for s in calls),
            'Overlapping business activation of same TCB')
        calls.append(dict(sequence=e['sequence'],role=e['role'],kind=d['kind'],object_address=r['r4'],
            tcb_address=tb,handle=words[2],registration_index=i,field_target=field,message=message,called=e,returned=None))
    else:
        s=calls[i];b=s['called']['registers'];words=struct.unpack('<8I',bytes.fromhex(e['memory']['tcb']))
        require(words[2]==s['handle'] and words[3]==s['object_address'] and words[5]==p['shared_entry']|1 and
            all(r[n]==b[n] for n in ('sp',)+tuple('r'+str(j) for j in range(4,12))),
            'Business return TCB/object/SP/callee-saved differs')
        require(a==dict(r,pc=d['loop']),'Original return-loop branch effect differs');s['returned']=e


def ready(rows,calls,minimum):
    returned=[s for s in calls if s['returned'] is not None and s.get('registration_index',0) is not None]
    return (len(returned)>=minimum and {s['role'] for s in returned}=={'master','slave'} and
        {s['kind'] for s in returned}=={1,2} and all(s['stored'] is not None for s in rows) and
        all(s['returned'] is not None for s in calls))


def summarize(rows,calls):
    out={}
    for role in ('master','slave'):
        selected=[s for s in calls if s['role']==role]
        registered=[s for s in selected if s['registration_index'] is not None]
        out[role]=dict(registrations=sum(s['role']==role for s in rows),calls=len(selected),
            registered_calls=len(registered),returned=sum(s['returned'] is not None for s in selected),
            unregistered_calls=sum(s['registration_index'] is None for s in selected),
            signatures=dict(sorted(Counter(str(s['kind']) for s in selected).items())),
            targets=[dict(address=a,samples=n) for a,n in sorted(Counter(s['field_target'] for s in selected).items())],
            registrations_without_call=sum(not any(q['registration_index']==i for q in calls) for i,s in enumerate(rows) if s['role']==role),
            return_r0_values=dict(sorted(Counter(str(s['returned']['registers']['r0']) for s in selected if s['returned'] is not None).items())))
    return out
