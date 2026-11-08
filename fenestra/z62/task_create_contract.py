"""Natural stock task construction, bounded config/name/frame/return relations only."""
from collections import Counter
import struct
from startup_contract import BASE, PROFILES, read_inputs, require, instructions
from pool_calls import REGISTERS, CALLEE_SAVED
from task_context import collect as context_collect, bounded_ram, words

TOOL = 'fenestra-z62-task-create/0.1.2'
LIMITATIONS = ('complete_task_abi_verified', 'stable_lifetime_identity_verified',
               'task_name_unique_verified', 'native_task_failure_matrix_verified')


def collect():
    context = context_collect()
    roles = {}
    anchor = bytes.fromhex('b001d4e1143094e55024e1e7b80094e5')
    for role, image in read_inputs().items():
        candidates = []
        at = image.find(anchor)
        while at >= 0:
            entry = at - 0x420
            if entry >= 0 and image[entry:entry+12] == bytes.fromhex('f04f2de914d04de200a0a0e3'):
                candidates.append(BASE+entry)
            at = image.find(anchor, at+1)
        require(len(candidates) == 1, 'Ambiguous original task creation entry')
        entry = candidates[0]
        for delta, raw in ((0x344,'cc0084e20820a0e3'),
                           (0x46C,'084094e596ffffea')):
            require(image[entry-BASE+delta:entry-BASE+delta+len(bytes.fromhex(raw))] == bytes.fromhex(raw),
                    'Original construction/name/return anchor differs')
        roles[role] = dict(role=role, entry=entry, constructed=entry+0x46C,
            context=context['roles'][role], config_bytes=56, tcb_bytes=216, frame_bytes=76,
            instructions=instructions(image,entry,0x474,False))
    return dict(schema=1,tool=TOOL,inputs=PROFILES,roles=roles,
        imports_equivalent='Raw ARM/Thumb, no conventional import table. Original constructor BL/literals, config loads, TCB stores, bounded name-copy call, frame CPSR/PC and return sequence are the local service anchors.',
        **{n:False for n in LIMITATIONS})


def bounded_read(p, address, size):
    """Address guard only, not proof of ownership/allocation/valid ABI."""
    if type(address) is not int or type(size) is not int or not 0 < size <= 4096 or address % 4:
        return False
    lo,hi = {'master':(0xC1800000,0xC617C478),'slave':(0xC1000000,0xC6004000)}[p['role']]
    return (lo <= address and address+size <= hi) or (
        BASE <= address and address+size <= BASE+PROFILES[p['role']]['size']-2)


def copied_name(config):
    require(len(config)==56,'Truncated original config')
    return config[48:56].split(b'\0',1)[0].ljust(8,b'\0')


def check_pair(pair,p):
    require(pair['role']==p['role'] and pair['thread'] in
            {'master':('01','02'),'slave':('03','04')}[p['role']], 'CPU/role mismatch')
    e,b,o=pair['entry'],pair['constructed'],pair['returned']
    r=e['registers']; end=o['registers']
    require(set(r)==set(REGISTERS) and set(end)==set(REGISTERS) and
            r['pc']==p['entry'] and r['cpsr']&0x3F==0x13,'Not original ARM SVC entry')
    require(bounded_read(p,r['r0'],56) and bounded_read(p,r['sp'],36),'Unbounded config/caller SP')
    require(end['sp']==r['sp'] and end['pc']==r['lr']&~1 and
            end['cpsr']&0x3F==(r['cpsr']&0x1F)|(0x20 if r['lr']&1 else 0), 'Original return SP/ISA differs')
    require(all(end[n]==r[n] for n in CALLEE_SAVED),'Callee-saved registers changed')
    cfg=bytes.fromhex(e['config']);cw=words(cfg,56)
    if b is None:
        require(end['r0']&0x80000000 and o.get('tcb') is None,'Unconstructed non-error return')
        return dict(error_return=end['r0'],successful=False,**{n:False for n in LIMITATIONS})
    br=b['registers'];tb=words(bytes.fromhex(b['tcb']),216);frame=words(bytes.fromhex(b['frame']),76)
    tcb=b['tcb_address'];fp=b['frame_address']
    require(br['pc']==p['constructed'] and br['cpsr']&0x3F==0x13 and br['r4']==tcb and
            br['r5']==r['r0'] and br['sp']==r['sp']-56,'Construction/call-frame relation differs')
    require(bounded_ram(p['context'],tcb,216) and bounded_ram(p['context'],fp,76),
            'Construction outside bounded original heap')
    require(b['config']==e['config'],'Config changed during construction')
    require(tb[3:6]==cw[:3], 'Original config words do not match TCB C/10/14')
    require(tb[0xBC//4]==br['r0']==fp==tb[0xB8//4]-76,'Original initial saved-SP relation differs')
    mode=(cw[1]>>8)&3
    cpsr=(0x1F if mode else 0x13)|(0x20 if cw[2]&1 else 0)
    require(frame[16]==cpsr and frame[18]==cw[2]&~1 and frame[12]==mode|(mode<<16),
            'Original initial frame CPSR/PC/mode differs')
    if mode:
        require(frame[13]==tb[0xB4//4],'Original non-SVC initial stack differs')
    name=copied_name(cfg)
    require(bytes.fromhex(b['tcb'])[204:212]==name,'Bounded original name copy differs')
    returned=words(bytes.fromhex(o['tcb']),216)
    require(end['r0']==tb[2]==returned[2] and end['r0']<0x80000000 and end['r0']!=0,
            'Original successful native return/TCB word08 differs')
    require(bytes.fromhex(o['tcb'])[204:212]==name and returned[3:6]==cw[:3],
            'Return config/name relation differs')
    return dict(successful=True,control_block=tcb,native_return_word08=tb[2],
        name_hex=name.hex(),name_display=name.rstrip(b'\0').decode('ascii',errors='backslashreplace'),
        configured_entry=cw[2],initial_cpsr=cpsr,initial_frame=fp,config_address=r['r0'],
        bounded_constructor_relation_verified=True,**{n:False for n in LIMITATIONS})


def summarize(pairs,contract):
    out={}
    for role,p in contract['roles'].items():
        rows=[check_pair(pair,p) for pair in pairs if pair['role']==role]
        good=[r for r in rows if r['successful']]
        out[role]=dict(calls=len(rows),successful=len(good),error_returns=len(rows)-len(good),
            observed_control_block_addresses=len({r['control_block'] for r in good}),
            observed_return_words=len({r['native_return_word08'] for r in good}),
            names=[dict(name_hex=n,name_display=bytes.fromhex(n).rstrip(b'\0').decode('ascii',errors='backslashreplace'),samples=c)
                   for n,c in sorted(Counter(r['name_hex'] for r in good).items())],
            arm_entries=sum(not r['configured_entry']&1 for r in good),
            thumb_entries=sum(bool(r['configured_entry']&1) for r in good),**{n:False for n in LIMITATIONS})
    return out
