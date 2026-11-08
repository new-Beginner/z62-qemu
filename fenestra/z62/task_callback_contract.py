"""Bounded original shared-entry field -> BX -> target first-instruction contract."""
from collections import Counter
import struct
from startup_contract import BASE, PROFILES, read_inputs, require, instructions
from task_entry_contract import collect as entries, check_prepared, check_pair, summarize as entry_summary, LIMITATIONS as ENTRY_LIMITATIONS
from task_create_contract import bounded_read

TOOL='fenestra-z62-task-callback/0.1.0'
LIMITATIONS=ENTRY_LIMITATIONS+('descriptor_ownership_verified','complete_descriptor_layout_verified',
    'business_callback_return_verified','complete_business_task_list_verified')
SHARED={'master':0x103DEBBC,'slave':0x1006CB80}


def collect():
    c=entries()
    for role,image in read_inputs().items():
        pc=SHARED[role];raw=image[pc-BASE:pc-BASE+4]
        require(raw==bytes.fromhex('49680847'),'Original shared LDR/BX differs')
        c['roles'][role].update(shared_entry=pc,shared_bytes=raw.hex(),
            shared_instructions=instructions(image,pc,4,True),descriptor_read_bytes=8,target_read_bytes=16)
    c.update(tool=TOOL,**{n:False for n in LIMITATIONS})
    return c


def bx_effect(r):
    target=r['r1'];pc=target&~1
    require(target!=0 and (bool(target&1) or pc%4==0),'Unaligned ARM BX target')
    return dict(r,pc=pc,cpsr=(r['cpsr']&~32)|(32 if target&1 else 0))


def first_effect(r,raw):
    """Finite decoded original opcodes only. Return expected registers and PUSH bytes."""
    pc=r['pc'];names=None;kind=None
    if not r['cpsr']&32:
        require(len(raw)>=4,'Truncated ARM first instruction');word=int.from_bytes(raw[:4],'little');mask=word&0xFFFF
        require(word>>16==0xE92D and mask and not mask&0xA000,'Uncovered ARM target instruction')
        names=[('r'+str(i)) if i<13 else 'lr' for i in range(15) if mask&(1<<i)]
        size=4;kind='arm-push'
    else:
        require(len(raw)>=2,'Truncated Thumb first instruction');h=int.from_bytes(raw[:2],'little')
        if h&0xFE00==0xB400 and h&0x1FF:
            names=['r'+str(i) for i in range(8) if h&(1<<i)]+(['lr'] if h&0x100 else [])
            size=2;kind='thumb-push'
        elif raw[:4]==bytes.fromhex('2de9f05f'):
            names=['r'+str(i) for i in range(4,13)]+['lr'];size=4;kind='thumb-push-wide'
        elif raw[:2]==bytes.fromhex('90b0'):
            return dict(r,pc=pc+2,sp=r['sp']-64),None,'thumb-sub-sp-64'
        elif raw[:4]==bytes.fromhex('00f12005'):
            return dict(r,pc=pc+4,r5=(r['r0']+32)&0xFFFFFFFF),None,'thumb-add-r5-r0-32'
        elif raw[:2]==bytes.fromhex('0024'):
            return dict(r,pc=pc+2,r4=0,cpsr=(r['cpsr']&~0xC0000000)|0x40000000),None,'thumb-movs-r4-zero'
        else:raise ValueError('Uncovered Thumb target instruction')
    sp=r['sp']-4*len(names);require(0<=sp<=0xFFFFFFFF,'Stack arithmetic wrapped')
    return dict(r,pc=pc+size,sp=sp),dict(address=sp,bytes=struct.pack('<'+'I'*len(names),*(r[n] for n in names)).hex()),kind


def check_shared(e,p):
    b,a=e['registers'],e['after_registers'];c=e['callback'];d=c['descriptor_address']
    require(b['pc']==p['shared_entry'] and b['cpsr']&0x3F==0x33,'Not original shared Thumb SVC entry')
    require(d==b['r1'] and bounded_read(p,d,8),'Unbounded descriptor read')
    raw=bytes.fromhex(c['descriptor']);require(len(raw)==8,'Truncated independent descriptor read')
    field=struct.unpack('<2I',raw)[1];target=field&~1
    require(BASE+16<=target and target+16<=BASE+PROFILES[p['role']]['size']-2,'Field target outside original member')
    require(a==dict(b,pc=b['pc']+2,r1=field),'Independent field/LDR result differs')
    bx=bx_effect(a);require(c['after_bx']==bx,'BX PC/ISA/arguments differ')
    require(c['target_current']==e['current'] and e['local_cpu'] in (0,1) and
            len(c['target_current'])==2,'Target current TCB changed')
    rom=c['target_rom'];require(rom['address']==target and len(bytes.fromhex(rom['bytes']))==16,'Target read changed')
    expected,stack,kind=first_effect(bx,bytes.fromhex(rom['bytes']))
    require(c['after_target']==expected and c['stack_write']==stack,'Target first instruction/register/stack effect differs')
    if stack:require(bounded_read(p,stack['address'],len(bytes.fromhex(stack['bytes']))),'Unbounded PUSH read')
    return dict(descriptor_address=d,field_offset=4,field_target=field,target_pc=target,
        target_thumb=bool(field&1),first_instruction_kind=kind,independent_field_load_verified=True,
        bx_target_verified=True,target_first_instruction_verified=True,**{n:False for n in LIMITATIONS})


def summarize(pairs,c):
    out=entry_summary(pairs,c)
    for role,p in c['roles'].items():
        rows=[check_shared(s['entered'],p) for s in pairs if s['role']==role and s['entered']['registers']['cpsr']&32]
        out[role].update(callback_samples=len(rows),
            targets=[dict(address=a,samples=n) for a,n in sorted(Counter(r['field_target'] for r in rows).items())],
            first_instructions=dict(sorted(Counter(r['first_instruction_kind'] for r in rows).items())),
            **{n:False for n in LIMITATIONS})
    return out
