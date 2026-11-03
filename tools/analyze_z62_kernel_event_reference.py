"""Record original event layout evidence and the precise limits of public references."""
import argparse
import json
from pathlib import Path
import re
import subprocess

from record_z62_action_evidence import workspace, digest, require
from z62_kernel_event_layout import contract

ROOT=Path(__file__).resolve().parents[1]


def analyze(master, output):
    master,output=map(workspace,(master,output)); layout=contract(master.read_bytes())
    repository=ROOT/'references/rtos/tkernel_2'
    revision=subprocess.run(['git','-C',str(repository),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    require(revision=='5778f619bdb354443551888dc2e9aa191e684da8','Public reference revision changed')
    files=('kernel/tkernel/src/eventflag.c','include/sys/svc/tkfncd.h','include/tk/syscall.h','include/tk/errno.h')
    reference={'repository':'https://github.com/tron-forum/tkernel_2','commit':revision,
        'files':{name:{'sha256':digest(repository/name),
            'url':'https://github.com/tron-forum/tkernel_2/blob/'+revision+'/'+name} for name in files}}
    source=(repository/'include/sys/svc/tkfncd.h').read_text(encoding='utf-8')
    code=re.search(r'^#define\s+TFN_WAI_FLG\s+(0x[0-9a-fA-F]+)',source,re.M)
    require(code is not None,'Public wait selector not found')
    reference['public_wait_selector']=code.group(1).lower()
    upstream=ROOT/'third_party/nightglasses-z7ii-qemu'
    upstream_revision=subprocess.run(['git','-C',str(upstream),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    notes=('docs/runtime/kernel.md','docs/runtime/displaywait.md','docs/runtime/wait/observation.md')
    record={'schema':1,'completed_analysis':True,'layout':layout,'analyzer_sha256':digest(Path(__file__)),
        'target_wait_selector':'0x80300500','public_reference':reference,
        'public_selector_matches_target':reference['public_wait_selector']=='0x80300500',
        'target_rtos_product_or_version_proven':False,
        'reused_z72_research':{'repository':'https://github.com/nightglasses/z7ii-qemu',
            'local_commit':upstream_revision,'notes':{name:digest(upstream/name) for name in notes},
            'reuse_scope':'Kernel entry hypotheses only; Z62 ROM operands and live CB identity are independently checked.'},
        'camera_accessed':False,'guest_memory_written':False}
    with output.open('x',encoding='utf-8') as handle: json.dump(record,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in record.items() if k not in ('layout','reused_z72_research')},ensure_ascii=False))
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--master',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); analyze(args.master,args.output)
