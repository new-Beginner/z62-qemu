"""Stock Z62 RTOS memory initialization, not an allocator ABI or free-space map."""
import argparse
import json
from pathlib import Path
import sys

from startup_contract import ROOT, BASE, PROFILES, analyze, arm_literal, u32, instructions, read_inputs, sha, require, section


def arm_call(data, address):
    word=u32(data,address-BASE)
    require(word >> 24 == 0xEB, 'Expected unconditional ARM BL')
    delta=word & 0xFFFFFF
    if delta & 0x800000:
        delta-=0x1000000
    return address+8+4*delta


def literal(data,address,register):
    return arm_literal(data,address-BASE,register)


def pool_geometry(start,end):
    require(0 <= start < end <= 2**32 and end-start > 0x1018, 'Invalid pool bounds')
    start=(start+7)&~7
    pool_end=(start+((end-start-8)//0x808)*8+0x807)&~0x7FF
    count=(end-pool_end)//0x800
    require(start < pool_end < end and count>2, 'Insufficient pool geometry')
    require(start+count*8+8<=pool_end, 'Pool headers overlap data area')
    return dict(start=start,end=end,pool_end=pool_end,count=count,block_bytes=0x800)


def list_groups(base):
    require(0 <= base <= 2**32-112 and base%4==0, 'Invalid heap list base')
    return [dict(flags=flags,base=(base+(56 if flags&0x300==0x300 else 0)+(28 if not flags&0x10 else 0))&~7)
            for flags in (0,0x10,0x300,0x310)]


def api_candidates(data,role,state):
    alloc,release={'master':(0x10108154,0x101082F4),
                   'slave':(0x10039B28,0x10039CC8)}[role]
    require(data[alloc-BASE:alloc-BASE+12]==bytes.fromhex('f04f2de9010811e3e4439fe5'),
            'Pool allocator prologue changed')
    require(data[release-BASE:release-BASE+8]==bytes.fromhex('4c129fe5f0472de9'),
            'Pool release wrapper changed')
    require(literal(data,alloc+8,4)==literal(data,release,1)==state,
            'Pool API candidates reference a different state')
    return dict(allocate_entry=alloc,release_entry=release,instruction_state='ARM',
                static_allocate_r0='count of 2048-byte blocks, NOT bytes',
                static_allocate_r1='bit16 is inspected; full flags contract unverified',
                static_allocate_return='address or zero; runtime behavior unverified',
                static_release_r0='candidate pool pointer; invalid/interior/double-free contract unverified',
                allocate_code=instructions(data,alloc,0x1A0,False),
                release_code=instructions(data,release,0x164,False),
                observed_calls=False,complete_abi_verified=False)


def profile(data,role):
    stock=analyze(data,role)
    rtos=arm_call(data,BASE+0xA4)
    service=arm_call(data,rtos+0x40)
    calls=[service+offset for offset in (0x50,0x64,0x78,0x8C,0xA0)]
    stages=[arm_call(data,call) for call in calls]
    pool,heap=stages[-2:]
    init_list=arm_call(data,heap+0x30)
    table=literal(data,BASE+0x278,0)
    require(table==literal(data,BASE+0x28C,0), 'Installed table target differs from copy')
    start,end=[literal(data,BASE+offset,1) for offset in (0x354,0x35C)]
    geometry=pool_geometry(start,end)
    config=literal(data,rtos+0x50,0)
    pool_config=literal(data,pool+0x14,4)
    pool_state=literal(data,pool+0x48,2)
    control=literal(data,heap+0x20,1)
    groups=list_groups(literal(data,init_list+4,2))
    # Decode the original stores which pass the two config bounds to the pool.
    require(literal(data,rtos+0x6C,2)==pool_config and literal(data,rtos+0x98,1)==pool_config+4,
            'RTOS does not populate the pool bound object')
    mappings=[section(data,address) for address in range(start&~0xFFFFF,end,0x100000)]
    require(all(m['physical_address']==m['virtual_address'] and m['ap_bits']==1 for m in mappings),
            'Initial heap sections must be native privileged RW')
    return dict(role=role,sha256=PROFILES[role]['sha256'],rtos_entry=rtos,service_entry=service,
                config=config,copied_table=table,service_calls=calls,service_stages=stages,
                pool_init=pool,pool_return=calls[-2]+4,heap_init=heap,heap_return=calls[-1]+4,
                services_return=rtos+0x44,pool_config=pool_config,pool_state=pool_state,
                heap_control=control,list_init=init_list,list_groups=groups,geometry=geometry,
                sections=mappings,vector=stock['startup']['vbar'],
                static_pool_api_candidates=api_candidates(data,role,pool_state),
                code=dict(config_writer=instructions(data,BASE+0x2F4,0x74,False),
                          rtos_prefix=instructions(data,rtos,0xCC,False),
                          services=instructions(data,service,0xB0,False),
                          pool_init=instructions(data,pool,0xB4,False),
                          heap_init=instructions(data,heap,0x58,False),
                          list_init=instructions(data,init_list,0x50,False)),
                allocator_call_abi_verified=False,allocation_lifetime_verified=False,
                plugin_execution_in_heap_verified=False,firmware_integrated=False,flash_safety_verified=False)


def collect():
    import capstone
    return dict(schema=1,tool='fenestra-z62-memory-init/0.1',
                sources={name:sha((ROOT/name).read_bytes()) for name in (
                    Path(__file__).relative_to(ROOT).as_posix(),'fenestra/z62/startup_contract.py')},
                tools=dict(python=sys.version,capstone=capstone.__version__),
                roles={r:profile(d,r) for r,d in read_inputs().items()},
                imports_equivalent='Raw ARM/Thumb; original direct calls, literal loads and RTOS config stores',
                camera_accessed=False,firmware_integrated=False,flash_safety_verified=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    output=p.parse_args().output.resolve()
    require(output.is_relative_to(ROOT/'analysis') and not output.exists(),'Use new analysis output')
    result=collect();output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({r:dict(geometry=v['geometry'],pool_init=hex(v['pool_init']),heap_init=hex(v['heap_init']))
                      for r,v in result['roles'].items()},indent=2))
