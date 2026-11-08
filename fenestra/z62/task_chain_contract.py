"""r17: same-process creation/index3/shared-BX/target first instruction, not completion."""
from collections import Counter
from startup_contract import ROOT,BASE,require,read_inputs,instructions
import task_joint_contract as joint
from task_joint_contract import CAP,EVENT_CAP,launch,bounded_read,bounded_ram
from task_callback_contract import SHARED,bx_effect,first_effect,check_shared

TOOL='fenestra-z62-task-chain/0.1.0'
LIMITATIONS=tuple(sorted(set(joint.LIMITATIONS+('business_callback_return_verified',
    'complete_business_task_list_verified','descriptor_ownership_verified'))))
creation_for_input=joint.creation_for_input
classify=joint.classify
create_plan=joint.create_plan
object_at=joint.object_at


def collect():
    c=joint.collect()
    for role,image in read_inputs().items():
        pc=SHARED[role];raw=image[pc-BASE:pc-BASE+4]
        require(raw==bytes.fromhex('49680847'),'Original shared LDR/BX differs')
        c['roles'][role].update(shared_entry=pc,shared_bytes=raw.hex(),
            shared_instructions=instructions(image,pc,4,True),descriptor_read_bytes=8,target_read_bytes=16)
    c.update(tool=TOOL,**{n:False for n in LIMITATIONS})
    c['imports_equivalent']+=' Independent shared object+4 field, original BX and bounded target first instruction.'
    return c


def check_callback(e,p,creation=None):
    cb=e['callback']
    require(cb['target_system']==e['system'] and cb['after_system']==e['system'],
            'Callback target system/fault state differs')
    result=check_shared(e,p)
    if creation is not None:
        require(cb['descriptor_address']==creation['object_address'] and
                cb['descriptor']==e['launch_object'][:16] and
                result['field_target']==creation['callback'],'Same creation callback/object differs')
    result.update(same_creation_callback_verified=creation is not None,**{n:False for n in LIMITATIONS})
    return result


def ingest(creations,pairs,e,p):
    phase,pi=joint.ingest(creations,pairs,e,p)
    needed=phase=='entered' and e['registers']['cpsr']&32
    require(('callback' in e)==bool(needed),'Missing/unexpected callback observation')
    if needed:
        ci=pairs[pi]['input'].get('creation_index')
        a=check_callback(e,p,None if ci is None else creations[ci]['analysis'])
        require(e['callback_analysis']==a,'Callback analysis differs')
    return phase,pi


def links(creations,pairs):
    out=joint.links(creations,pairs)
    for row in out:
        e=pairs[row['launch_index']]['entered']
        require(e['callback_analysis']['same_creation_callback_verified'] is True,'Missing same-chain callback')
        row.update(callback_target=e['callback_analysis']['field_target'],
                   first_instruction_kind=e['callback_analysis']['first_instruction_kind'])
    return out


def ready(creations,pairs,minimum):
    return joint.ready(creations,pairs,minimum) and len(links(creations,pairs))>=minimum


def summarize(creations,pairs):
    out=joint.summarize(creations,pairs);out['links']=links(creations,pairs)
    callbacks=[s['entered']['callback_analysis'] for s in pairs if 'callback_analysis' in s['entered']]
    out.update(callback_samples=len(callbacks),same_chain_callback_samples=len(out['links']),
        callback_first_instructions=dict(sorted(Counter(a['first_instruction_kind'] for a in callbacks).items())),
        **{n:False for n in LIMITATIONS})
    return out
