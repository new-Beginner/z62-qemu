"""Recompute the stock startup contract and verify bounded observation receipts.

Does not certify a Fenestra integration, camera update or hardware safety.
"""
import argparse
import json
from pathlib import Path
import subprocess

from startup_contract import ROOT, BASE, collect, read_inputs, sha, require
from observe_startup import QEMU_REL, QEMU_SHA


def verify(paths, static):
    expected, images = collect(), read_inputs()
    require(json.loads(static.read_text(encoding='utf-8')) == expected, 'Static contract changed')
    require(len(paths)>=2, 'Require two independent observation processes')
    receipts=[]
    for path in paths:
        path=path.resolve()
        require(path.is_relative_to(ROOT/'analysis'), 'Run path escaped project')
        r=json.loads(path.read_text(encoding='utf-8'))
        require(r['completed'] and r['owned_process_closed'] and r['exit_code']==0, 'Incomplete observation')
        require(r['contract']==expected, 'Run/current contract mismatch')
        require(r['firmware_loaded'] and r['reset_pc_initialized_by_qemu_loader'], 'Missing EG boot setup')
        for name in ('firmware_integrated','flash_safety_verified','camera_accessed',
                     'debugger_guest_registers_written','debugger_guest_memory_written',
                     'original_firmware_patched','earlier_camera_loader_executed','parameters_loaded',
                     'card_attached','controller_loaded','full_scatter_dispatch_execution_verified',
                     'startup_complete_hook_verified'):
            require(r[name] is False, 'Changed scope flag: '+name)
        for name,digest in r['sources'].items():
            p=(ROOT/name).resolve()
            require(p.is_relative_to(ROOT) and sha(p.read_bytes())==digest, 'Run source changed: '+name)
        require(r['qemu_sha256']==QEMU_SHA and sha((ROOT/QEMU_REL).read_bytes())==QEMU_SHA, 'QEMU identity changed')
        require(sha(path.with_suffix('.qemu.log').read_bytes())==r['log_sha256'], 'QEMU log changed')
        copied=0
        for role,contract in expected['roles'].items():
            rows=[h for h in r['hits'] if h['role']==role]
            required=['before-inline','after-inline','runtime-thumb','kernel-entry']
            kinds=[h['kind'] for h in rows]
            require(all(k in kinds for k in required), 'Missing startup checkpoint: '+role)
            require([kinds.index(k) for k in required]==sorted(kinds.index(k) for k in required), 'Checkpoint order mismatch')
            require(set(r['seen'][role])==set(kinds), 'Recorded checkpoint set mismatch')
            for k in required[:3]:
                require(kinds.count(k)==1, 'Duplicate core-zero checkpoint: '+k)
            for row in rows:
                regs,system=row['registers'],row['system_registers']
                state=contract['startup']
                require(bool(regs['cpsr'] & 32)==(row['kind']=='runtime-thumb'), 'Wrong instruction state')
                require(system['TTBR0_S']==state['ttbr0'] and system['TTBCR_S']==0, 'Original TTBR not active')
                require(system['DACR_S']==state['dacr'] and system['VBAR_EL1_S']==state['vbar'], 'Original domain/vector mismatch')
                sctlr=system['SCTLR_EL1_S']
                require(sctlr & 0x1005==0x1005, 'MMU and both caches must remain enabled')
                require(sctlr & ((1<<29)|(1<<28))==0, 'Unexpected AFE/TRE translation mode')
                require(all(system[n]==0 for n in ('DFSR_S','IFSR_S','DFSR','IFSR')), 'Fault state in observed CPU')
                addresses={'before-inline':BASE+0xBE74,'after-inline':BASE+0xBF88,
                           'runtime-thumb':state['runtime_thumb'],'kernel-entry':BASE+0xAC}
                require(row['kind'] in addresses and regs['pc']==addresses[row['kind']], 'Checkpoint PC mismatch')
            before=rows[kinds.index('before-inline')]
            require(before['page_table_sha256']==sha(images[role][0x10000:0x14000]), 'Original TTBR content mismatch')
            require(before['registers']['sp']==contract['startup']['core0_stack_tops']['SVC'], 'Core-zero SVC stack mismatch')
            after=rows[kinds.index('after-inline')]
            require(after['third_destination_head_unchanged'] is True, 'Zero-length sample changed')
            require(len(after['copy_checks'])==2, 'Incomplete early copies')
            for check,copy in zip(after['copy_checks'],contract['startup']['early_copies'][:2]):
                require(check['destination']==copy['destination'] and check['size']==copy['size'], 'Copy range mismatch')
                require(check['equal'] and check['actual_sha256']==check['expected_sha256']==copy['source_sha256'], 'Copy content mismatch')
                copied+=copy['size']
        require(r['observed_copy_bytes']==copied==820912, 'Early copy total mismatch')
        receipts.append(dict(file=path.relative_to(ROOT).as_posix(),sha256=sha(path.read_bytes()),pid=r['owned_pid'],
                             early_copy_bytes=copied,hits=len(r['hits'])))
    require(len({r['pid'] for r in receipts})==len(receipts), 'Repeated process identity')
    original=json.loads((ROOT/'analysis/fenestra-feasibility/source-check.json').read_text(encoding='utf-8'))
    for row in original['original_inputs']:
        data=(ROOT/row['file']).read_bytes()
        require(len(data)==row['size'] and sha(data)==row['sha256'], 'Original firmware changed')
    head=subprocess.check_output(['git','-C',str(ROOT/'third_party/z62-qemu'),'rev-parse','HEAD'],text=True).strip()
    require(head=='4f4389944fc339d107f22f5f7ca3f90cc34b78de', 'Submodule commit changed')
    dirty=subprocess.check_output(['git','-C',str(ROOT/'third_party/z62-qemu'),'status','--porcelain'],text=True)
    require(not dirty.strip(), 'Pinned submodule was changed')
    return dict(schema=1,bounded_early_startup_verified=True,runs=receipts,
                verification_source_sha256=sha(Path(__file__).read_bytes()),
                original_inputs_unchanged=len(original['original_inputs']),qemu_unchanged=True,
                executable_space_reserved=False,startup_complete_hook_verified=False,card_loading_verified=False,
                firmware_integrated=False,flash_safety_verified=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--static',type=Path,required=True)
    p.add_argument('--run',type=Path,action='append',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();output=a.output.resolve()
    require(output.is_relative_to(ROOT/'analysis') and not output.exists(), 'Use new analysis output')
    result=verify(a.run,a.static)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))
