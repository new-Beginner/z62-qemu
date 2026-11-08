"""Revalidate bounded memory-init evidence; never certifies allocator/flash safety."""
import argparse
import copy
import json
from pathlib import Path
import subprocess

from memory_contract import collect
from startup_contract import ROOT,read_inputs,sha,require
from observe_startup import QEMU_REL,QEMU_SHA

FALSE_FIELDS=('firmware_integrated','flash_safety_verified','camera_accessed','debugger_guest_registers_written',
              'debugger_guest_memory_written','injected_calls','parameters_loaded','card_attached','controller_loaded',
              'earlier_camera_loader_executed','allocator_call_abi_verified','allocation_lifetime_verified',
              'plugin_execution_in_heap_verified')


def check_run(r,expected,images):
    require(r['completed'] and r['memory_initialization_verified'] and r['owned_process_closed'] and r['exit_code']==0,
            'Incomplete memory observation')
    require(r['contract']==expected,'Run/current contract mismatch')
    require(r['firmware_loaded'] and r['reset_pc_initialized_by_qemu_loader'],'Missing stock EG boot setup')
    require(all(r[k] is False for k in FALSE_FIELDS),'Changed scope flag')
    require(len(r['hits'])==8,'Expected exactly eight primary checkpoints')
    for role,p in expected['roles'].items():
        rows=[h for h in r['hits'] if h['role']==role]
        kinds=['pool-before','pool-after','heap-after','services-after']
        require([h['kind'] for h in rows]==kinds and r['seen'][role]==kinds,'Checkpoint order/set mismatch')
        require(len({h['thread'] for h in rows})==1,'Primary thread changed')
        owner=rows[0]['thread'];require(owner==('01' if role=='master' else '03'),'Unexpected primary CPU mapping')
        stack=rows[0]['registers']['sp'];g=p['geometry'];count=g['count']
        addresses=(p['pool_init'],p['pool_return'],p['heap_return'],p['services_return'])
        for index,(row,pc) in enumerate(zip(rows,addresses)):
            reg,system=row['registers'],row['system_registers']
            require(reg['pc']==pc and reg['cpsr']&32==0,'Checkpoint PC/state mismatch')
            require(reg['sp']==stack+(8 if index==3 else 0),'Stack not restored')
            require(index==0 or reg['r0']==0,'Original routine returned failure')
            require(system['TTBR0_S']==p['copied_table'] and system['TTBCR_S']==0,'Original copied table not active')
            require(system['DACR_S']==0x55555555 and system['VBAR_EL1_S']==p['vector'],'Domain/vector changed')
            require(system['SCTLR_EL1_S']&0x1005==0x1005,'MMU/cache disabled')
            require(all(system[n]==0 for n in ('DFSR_S','IFSR_S','DFSR','IFSR')),'Observed CPU fault state')
        require(rows[0]['registers']['lr']==p['pool_return'],'Pool caller changed')
        require(rows[0]['pool_config_before'][:2]==[g['start'],g['end']],'Initial pool bounds mismatch')
        require(rows[0]['installed_table_sha256']==sha(images[role][0x10000:0x14000]),'RAM page table differs')
        require(rows[1]['pool_state']==[count,count,g['start'],g['pool_end']],'Pool state mismatch')
        require(rows[1]['pool_config'][0]==g['end'],'Pool cursor mismatch')
        require(rows[1]['first_headers']==[4,4,1,0,(count<<2)|1,0] and
                rows[1]['tail_header']==[(count<<2)|1,0],'Pool boundary header mismatch')
        require(rows[2]['heap_control']==[0,0x800],'Heap control mismatch')
        require(len(rows[2]['list_groups'])==4,'Missing heap lists')
        for actual,group in zip(rows[2]['list_groups'],p['list_groups']):
            b=group['base'];flags=group['flags']
            require(actual==dict(**group,words=[b+8,b+8,b+16,b+16,flags]),'Heap empty list mismatch')
    return True


def negative_checks(valid,expected,images):
    def row(r,kind):return next(h for h in r['hits'] if h['role']=='master' and h['kind']==kind)
    def omitted(r):r['hits'].pop()
    def ret(r):row(r,'pool-after')['registers']['r0']=1
    def table(r):row(r,'pool-before')['system_registers']['TTBR0_S']^=0x4000
    def count(r):row(r,'pool-after')['pool_state'][1]+=1
    def header(r):row(r,'pool-after')['tail_header'][0]^=1
    def links(r):row(r,'heap-after')['list_groups'][0]['words'][0]+=8
    def scope(r):r['allocator_call_abi_verified']=True
    def seen(r):r['seen']['master']=[]
    def thread(r):row(r,'pool-after')['thread']='02'
    def stack(r):row(r,'services-after')['registers']['sp']+=4
    def pc(r):row(r,'heap-after')['registers']['pc']+=4
    def lr(r):row(r,'pool-before')['registers']['lr']+=4
    rejected=[]
    for mutate in (omitted,ret,table,count,header,links,scope,seen,thread,stack,pc,lr):
        r=copy.deepcopy(valid);mutate(r)
        try:check_run(r,expected,images)
        except ValueError:rejected.append(mutate.__name__)
        else:raise ValueError('Altered evidence accepted: '+mutate.__name__)
    return rejected


def verify(paths,static):
    expected,images=collect(),read_inputs()
    require(json.loads(static.read_text(encoding='utf-8'))==expected,'Static contract changed')
    require(len(paths)>=2,'Two independent processes required')
    receipts=[];negative=[]
    for path in paths:
        path=path.resolve();require(path.is_relative_to(ROOT/'analysis'),'Run escaped project')
        r=json.loads(path.read_text(encoding='utf-8'));check_run(r,expected,images)
        for name,digest in r['sources'].items():
            p=(ROOT/name).resolve();require(p.is_relative_to(ROOT) and sha(p.read_bytes())==digest,'Changed runtime source: '+name)
        require(r['qemu_sha256']==QEMU_SHA and sha((ROOT/QEMU_REL).read_bytes())==QEMU_SHA,'Changed QEMU')
        require(sha(path.with_suffix('.qemu.log').read_bytes())==r['log_sha256'],'Changed run log')
        if not negative:negative=negative_checks(r,expected,images)
        receipts.append(dict(file=path.relative_to(ROOT).as_posix(),sha256=sha(path.read_bytes()),pid=r['owned_pid']))
    require(len({r['pid'] for r in receipts})==len(receipts),'Same observation process reused')
    baseline=json.loads((ROOT/'analysis/fenestra-feasibility/source-check.json').read_text(encoding='utf-8'))
    for row in baseline['original_inputs']:
        data=(ROOT/row['file']).read_bytes();require(len(data)==row['size'] and sha(data)==row['sha256'],'Original input changed')
    repo=ROOT/'third_party/z62-qemu'
    require(subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==
            '4f4389944fc339d107f22f5f7ca3f90cc34b78de','Submodule commit changed')
    require(not subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True).strip(),'Submodule dirty')
    return dict(schema=1,bounded_memory_initialization_verified=True,runs=receipts,negative_receipt_checks=negative,
                verifier_source_sha256=sha(Path(__file__).read_bytes()),original_inputs_unchanged=4,qemu_unchanged=True,
                allocator_call_abi_verified=False,allocation_lifetime_verified=False,plugin_execution_in_heap_verified=False,
                firmware_integrated=False,flash_safety_verified=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--static',type=Path,required=True)
    p.add_argument('--run',type=Path,action='append',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();output=a.output.resolve();require(output.is_relative_to(ROOT/'analysis') and not output.exists(),'Use new analysis output')
    result=verify(a.run,a.static);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))
