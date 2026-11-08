"""r19 bounded original two-argument queue callback, not a queue/RTOS SDK."""
import struct
from startup_contract import BASE,PROFILES,read_inputs,require,instructions
import business_contract as b
from pool_calls import REGISTERS
from task_create_contract import bounded_read
from task_launch_contract import bounded_stack
from task_context import bounded_ram

TOOL='fenestra-z62-queue/0.1.0'
STARTS={'master':0x1038A99C,'slave':0x10067710}
CAP=8
STORE_CAP=32
EVENT_CAP=256
SAVED=('r4','r5','r6','r7','r8','lr')
LIMITATIONS=tuple(sorted(set(b.LIMITATIONS+('business_semantics_verified','queue_ownership_verified',
    'queue_concurrency_verified','nested_service_abi_verified','phase1_passed','phase2_entered',
    'physical_gate_open','absolute_safety_verified'))))


def collect():
    c=b.collect()
    for role,image in read_inputs().items():
        p=c['roles'][role];start=STARTS[role];code=instructions(image,start,68,True)
        expected={0:'2de9f041',4:'c907',6:'00f13004',10:'19d0',12:'374f',14:'c026',16:'00f54045',
            20:'d4e90010',24:'8842',26:'11d0',28:'411c',30:'b1fbf6f2',34:'00eb4010',38:'06fb1211',
            42:'6160',44:'04ebc001',48:'d5f83826',52:'0831',54:'002a',56:'ecd0',58:'3846',60:'9047',62:'e9e7',64:'bde8f081'}
        require({i['address']-start:i['bytes'] for i in code}==expected,'Original queue instructions differ')
        literal=((start+12+4)&~3)+0xdc
        global_word=int.from_bytes(image[literal-BASE:literal-BASE+4],'little')
        require(BASE<=literal and literal+4<=BASE+len(image)-2,'Queue literal outside original ROM')
        # The loaded word is an opaque argument (42070001), NOT a dereferenced RAM pointer.
        d=p['dispatchers'][1]
        p['queue']=dict(start=start,entry=start,load=start+20,store=start+42,nested=start+60,
            nested_return=start+62,pop=start+64,call=d['call'],returned=d['returned'],loop=d['loop'],
            literal_address=literal,literal_bytes=image[literal-BASE:literal-BASE+4].hex(),global_word=global_word,
            instructions=code)
    c.update(tool=TOOL,imports_equivalent='Raw ARM/Thumb: kind2 dispatcher BLX, queue PUSH/LDRD/STR/BLX/POP and literal global; no conventional imports; not complete services.',
        **{n:False for n in LIMITATIONS})
    return c


def next_index(index):
    require(type(index) is int and 0<=index<192,'Queue index outside static 192 slots')
    return (index+1)%192


def slot(obj,index):
    next_index(index)
    require(type(obj) is int and 0<=obj<=0xffffffff-0xc638,'Queue object address overflow')
    return obj+56+index*264


def load_effect(r,raw):
    require(len(raw)==8,'Original LDRD read size differs')
    producer,consumer=struct.unpack('<2I',raw);next_index(producer);next_index(consumer)
    return dict(r,r1=producer,r0=consumer,pc=r['pc']+4)


def check_store(r,a,before,after,index):
    producer,consumer=struct.unpack('<2I',before)
    require(consumer==index and r['r1']==next_index(index) and after==struct.pack('<2I',producer,r['r1']) and
        a==dict(r,pc=r['pc']+2),'Original queue STR memory/register effect differs')


def pop_effect(r,raw):
    require(len(raw)==24,'Original POP read size differs')
    words=struct.unpack('<6I',raw);target=words[-1];pc=target&~1
    require(target!=0 and (target&1 or pc%4==0),'Unverified POP return ISA/alignment')
    return dict(r,**dict(zip(SAVED[:-1],words[:-1])),sp=r['sp']+24,pc=pc,
        cpsr=(r['cpsr']&~32)|(32 if target&1 else 0))


def points(c):
    return {a for p in c['roles'].values() for k,a in p['queue'].items() if k in
        ('entry','load','store','nested','nested_return','pop','call','returned')}


def classify(calls,e,p):
    r=e['registers'];q=p['queue'];phases=[k for k in ('call','entry','load','store','nested','nested_return','pop','returned') if r['pc']==q[k]]
    require(len(phases)==1,'Unknown original queue breakpoint');phase=phases[0]
    if phase=='call':return phase,None
    tb=e['current'][e['local_cpu']]
    matches=[i for i,s in enumerate(calls) if s['role']==e['role'] and s['tcb_address']==tb and s['returned'] is None and
        r['sp']==s['called']['registers']['sp']-(0 if phase in ('entry','returned') else 24)]
    require(len(matches)==1,'Unpaired/ambiguous original queue '+phase)
    return phase,matches[0]


def read_plan(calls,e,p):
    r=e['registers'];phase,i=classify(calls,e,p);tb=e['current'][e['local_cpu']]
    require(bounded_ram(p['context'],tb,32),'Unbounded queue TCB')
    obj=r['r4'] if phase=='call' else calls[i]['object_address']
    plan=[('object',obj,48),('tcb',tb,32)]
    if phase=='call':plan.append(('message',r['sp'],4))
    if phase not in ('call','entry'):plan.append(('saved',r['sp'] if phase!='returned' else r['sp']-24,24))
    if phase in ('load','store','nested','nested_return','pop'):
        plan += [('indices',obj+48,8),('field',obj+0xc638,4)]
    if phase in ('store','nested'):
        s=calls[i];require(s['last_load'] is not None,'Missing queue index load')
        index=s['last_load']['after_registers']['r0']
        plan.append(('slot',slot(obj,index),264))
    return plan


def ingest(calls,e,p):
    r=e['registers'];a=e['after_registers'];q=p['queue'];phase,i=classify(calls,e,p)
    require((phase,i)==(e['phase'],e['pair_index']) and r['cpsr']&0x3f==0x33,'Queue phase/Thumb SVC differs')
    plan=read_plan(calls,e,p)
    require(set(e['memory'])=={label for label,_,_ in plan},'Queue memory labels differ')
    for label,address,size in plan:
        require(bounded_read(p,address,size) and len(bytes.fromhex(e['memory'][label]))==size,'Unbounded/wrong-sized queue read')
    raw=bytes.fromhex(e['memory']['object']);words=struct.unpack('<8I',bytes.fromhex(e['memory']['tcb']))
    obj=r['r4'] if phase=='call' else calls[i]['object_address']
    require(words[3]==obj and words[5]==p['shared_entry']|1 and int.from_bytes(raw[4:8],'little')==p['dispatchers'][1]['start']|1,
        'Queue TCB/object/shared entry differs')
    if phase=='call':
        require(len(calls)<CAP,'Outer queue call bound exceeded')
        message=int.from_bytes(bytes.fromhex(e['memory']['message']),'little');target=int.from_bytes(raw[36:40],'little')
        b.check_arguments(r,2,obj,message,target)
        require(target==q['start']|1 and a==b.blx_effect(r,'r2'),'Queue outer target/BLX differs')
        require(e['target_current']==e['current'] and e['target_system']==e['system'],'Queue outer target state differs')
        tb=e['current'][e['local_cpu']]
        require(not any(s['role']==e['role'] and s['tcb_address']==tb and s['returned'] is None for s in calls),'Overlapping queue activation')
        calls.append(dict(sequence=e['sequence'],role=e['role'],object_address=obj,tcb_address=tb,handle=words[2],
            message=message,called=e,entered=None,last_load=None,loads=[],stores=[],nested=[],popped=None,returned=None))
        return
    s=calls[i];original=s['called']['after_registers']
    require(words[2]==s['handle'] and int.from_bytes(raw[36:40],'little')==q['start']|1,'Queue handle/field changed')
    if phase=='entry':
        require(s['entered'] is None and r==original and bounded_stack(p,r['sp']-24,24),'Queue entry differs')
        require(a==dict(r,pc=r['pc']+4,sp=r['sp']-24) and e['after_stack']==struct.pack('<6I',*(r[n] for n in SAVED)).hex(),
            'Original queue PUSH effect differs');s['entered']=e;return
    require(s['entered'] is not None,'Queue point before original PUSH')
    saved=s['entered']['after_stack']
    require(e['memory']['saved']==saved,'Original queue saved stack changed')
    if phase=='returned':
        require(s['popped'] is not None and r['sp']==s['called']['registers']['sp'] and
            all(r[n]==s['called']['registers'][n] for n in ('r4','r5','r6','r7','r8','r9','r10','r11')) and
            a==dict(r,pc=q['loop']),'Original outer return-loop differs');s['returned']=e;return
    require(r['r4']==obj+48,'Queue base register differs')
    if phase=='pop':
        require(s['popped'] is None and all(n['returned'] is not None for n in s['nested']) and
            a==pop_effect(r,bytes.fromhex(saved)) and a['pc']==q['returned'],'Original queue POP effect differs')
        s['popped']=e;return
    require(r['r5']==obj+0xc000 and r['r6']==192 and r['r7']==q['global_word'],'Queue geometry/global registers differ')
    if phase=='load':
        require(all(n['returned'] is not None for n in s['nested']) and a==load_effect(r,bytes.fromhex(e['memory']['indices'])),
            'Original queue LDRD effect/order differs')
        s['last_load']=e;s['loads'].append(e);return
    require(s['last_load'] is not None,'Queue operation without LDRD');last=s['last_load'];index=last['after_registers']['r0']
    if phase=='store':
        require(sum(len(x['stores']) for x in calls)<STORE_CAP,'Queue store bound exceeded')
        require(last['after_registers']['r0']!=last['after_registers']['r1'] and r['r0']==index*33 and
            not any(x['load_sequence']==last['sequence'] for x in s['stores']),'Queue source index/stride/order differs')
        check_store(r,a,bytes.fromhex(e['memory']['indices']),bytes.fromhex(e['after_indices']),index)
        s['stores'].append(dict(load_sequence=last['sequence'],index=index,event=e));return
    if phase=='nested':
        require(s['stores'] and s['stores'][-1]['load_sequence']==last['sequence'] and
            all(n['returned'] is not None for n in s['nested']),'Nested queue call without original store')
        target=int.from_bytes(bytes.fromhex(e['memory']['field']),'little')
        require(r['r0']==q['global_word'] and r['r1']==slot(obj,index) and r['r2']==target and
            a==b.blx_effect(r,'r2'),'Nested field/slot/BLX arguments differ')
        require(e['target_current']==e['current'] and e['target_system']==e['system'],'Nested target state differs')
        s['nested'].append(dict(sequence=e['sequence'],index=index,slot_address=r['r1'],target=target,called=e,returned=None));return
    require(phase=='nested_return' and s['nested'] and s['nested'][-1]['returned'] is None,'Unpaired nested return')
    n=s['nested'][-1];before=n['called']['registers']
    require(all(r[k]==before[k] for k in ('sp','r4','r5','r6','r7','r8','r9','r10','r11')) and
        a==dict(r,pc=q['load']),'Original nested return-loop differs');n['returned']=e


def local_summary(calls):
    return dict(outer_calls=len(calls),entered=sum(s['entered'] is not None for s in calls),
        index_loads=sum(len(s['loads']) for s in calls),index_stores=sum(len(s['stores']) for s in calls),
        nested_calls=sum(len(s['nested']) for s in calls),nested_returned=sum(n['returned'] is not None for s in calls for n in s['nested']),
        popped=sum(s['popped'] is not None for s in calls),outer_returned=sum(s['returned'] is not None for s in calls),
        all_observed_outer_calls_returned=bool(calls) and all(s['returned'] is not None for s in calls),
        pending=[dict(sequence=s['sequence'],role=s['role'],object_address=s['object_address'],tcb_address=s['tcb_address'],
            loads=len(s['loads']),stores=len(s['stores']),active_nested=[dict(sequence=n['sequence'],target=n['target'],slot_address=n['slot_address'])
                for n in s['nested'] if n['returned'] is None]) for s in calls if s['returned'] is None],
        **{n:False for n in LIMITATIONS})
