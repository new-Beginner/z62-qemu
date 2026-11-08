"""Original SVC task launch frame to actual first entry: a bounded local contract."""
from collections import Counter
from startup_contract import BASE, PROFILES, read_inputs, instructions, require
from pool_calls import REGISTERS
from task_context import collect as contexts, bounded_ram, words

TOOL='fenestra-z62-task-entry/0.1.1'
LIMITATIONS=('complete_task_abi_verified','business_task_completed','task_lifetime_verified',
             'startup_api_return_verified','system_mode_verified','stable_task_identity_verified')


def collect():
    ctx=contexts();roles={}
    for role,image in read_inputs().items():
        anchor=bytes.fromhex('f05f2de901b0a0e10050a0e1');at=image.find(anchor)
        require(at>=0 and image.find(anchor,at+1)<0,'Ambiguous native task start')
        entry=BASE+at;pc=entry+0x1A8
        require(image[at+0x198:at+0x1AC]==bytes.fromhex('bc0094e500b080e50c1094e5041080e50400a0e1'),
                'Original argument-frame/publish anchor differs')
        roles[role]=dict(role=role,start=entry,checkpoint=pc,context=ctx['roles'][role],
            instructions=instructions(image,entry,0x1B8,False),tcb_bytes=216,frame_bytes=76)
    return dict(schema=1,tool=TOOL,inputs=PROFILES,roles=roles,
        imports_equivalent='Raw ARM/Thumb: original start r1->r11, frame stores, native scheduling call, and context restore are the local service anchors; no conventional import table.',
        **{n:False for n in LIMITATIONS})


def check_prepared(e,p):
    r=e['registers'];tb=words(bytes.fromhex(e['tcb']),216);f=words(bytes.fromhex(e['frame']),76)
    require(set(r)==set(REGISTERS) and r['pc']==p['checkpoint'] and r['cpsr']&0x3F==0x13,'Not original SVC publish checkpoint')
    require(e['tcb_address']==r['r4'] and bounded_ram(p['context'],r['r4'],216) and
            bounded_ram(p['context'],e['frame_address'],76),'Unbounded TCB/frame')
    require(e['frame_address']==r['r0']==tb[0xBC//4]==tb[0xB8//4]-76,'Initial frame/SP differs')
    require(r['r5']==0 and tb[2]!=0 and tb[2]<0x80000000,'Native validation status/TCB word differs')
    require(f[:2]==[r['r11'],tb[3]] and r['r1']==tb[3],'Original launch argument slots differ')
    require((tb[4]>>8)&3==0 and f[16]==(0x13|(0x20 if tb[5]&1 else 0)) and f[18]==tb[5]&~1,
            'Outside original SVC initial-frame contract')
    require(BASE+16<=f[18]<BASE+PROFILES[p['role']]['size']-18,'Entry outside original payload')
    return dict(control_block=r['r4'],native_handle_word08=tb[2],entry_pc=f[18],configured_entry=tb[5],
        expected_sp=tb[0xB8//4],expected_arguments=f[:2],expected_cpsr=f[16],task_entry_observed=False,
        **{n:False for n in LIMITATIONS})


def check_pair(pair,p):
    require(pair['role']==p['role'],'Entry role differs')
    a=check_prepared(pair['prepared'],p);e=pair['entered'];r=e['registers'];tb=words(bytes.fromhex(e['tcb']),216)
    require(e['tcb_address']==a['control_block'] and e['local_cpu'] in (0,1) and len(e['current'])==2 and
            e['current'][e['local_cpu']]==a['control_block'],'New current TCB differs')
    require(tb[2]==a['native_handle_word08'] and tb[5]==a['configured_entry'] and tb[3]==a['expected_arguments'][1],
            'Target TCB fields changed before first entry')
    require(r['pc']==a['entry_pc'] and r['sp']==a['expected_sp'] and r['cpsr']&0x3F==a['expected_cpsr'] and
            [r['r0'],r['r1']]==a['expected_arguments'],'Actual entry PC/SP/ISA/arguments differ')
    return dict(a,task_entry_observed=True,entry_arguments=[r['r0'],r['r1']],
                entered_on_local_cpu=e['local_cpu'],business_task_completed=False)


def summarize(pairs,c):
    out={}
    for role,p in c['roles'].items():
        rows=[check_pair(s,p) for s in pairs if s['role']==role]
        out[role]=dict(entries=len(rows),arm=sum(not r['configured_entry']&1 for r in rows),
            thumb=sum(bool(r['configured_entry']&1) for r in rows),
            nonzero_start_argument=sum(bool(r['entry_arguments'][0]) for r in rows),
            nonzero_extension_word=sum(bool(r['entry_arguments'][1]) for r in rows),
            entry_pcs=[dict(address=a,samples=n) for a,n in sorted(Counter(r['entry_pc'] for r in rows).items())],
            **{n:False for n in LIMITATIONS})
    return out
