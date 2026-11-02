"""Verify r8's finite-capture evidence without claiming complete emulation."""
import argparse
import hashlib
import json
from pathlib import Path

import run_z62_finite_stats as host

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'analysis/z62-finite-r8'


def check():
    manifest=host.verify_build(host.DEFAULT_QEMU.resolve())
    evidence={}
    def read(name):
        path=BASE/name
        raw=path.read_bytes()
        evidence[name]=hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    qtest=read('qtest.json')
    legacy=read('legacy-raw-stream.json')
    for data in (qtest,legacy):
        if data.get('completed') is not True or data.get('binary_sha256')!=manifest['binary_sha256']:
            raise ValueError('Native test identity/completion mismatch')
    native=read('native/report.json')
    if not native.get('observation_completed') or not native.get('clean_exit') or native.get('qemu_exit_code')!=0:
        raise ValueError('Original-firmware run incomplete')
    if native.get('raw_transactions') or native.get('metadata_events') or native.get('camera_accessed'):
        raise ValueError('Unexpected host transactions/camera access')
    last=native['samples'][-1]['capture']['finite_stats_status']
    master=last['engines']['master']
    if not last['known'] or [master[k] for k in ('finite-batches','finite-frames','finite-bytes','finite-rejected')]!=[2,122,93696,0]:
        raise ValueError('Finite work did not complete naturally')
    if last['engines']['slave']['finite-frames']!=0:
        raise ValueError('Unexpected slave work')
    command=json.loads((BASE/'native/command.json').read_text())
    if any('laboratory-metadata-completion=on' in value for value in command):
        raise ValueError('Unexpected metadata fixture')
    menu=read('menu/report.json')
    if not menu.get('process_closed') or not menu.get('menu_cycle_state_passed') or len(menu['cycles'])!=3:
        raise ValueError('Menu-cycle acceptance incomplete')
    if not all(c.get('navigation_passed') and c.get('reopened') and c.get('returned_applv') for c in menu['cycles']):
        raise ValueError('Menu navigation failed')
    candidate=read('candidate/report.json')
    if not candidate.get('sentinel_executed') or not candidate.get('probe_completed'):
        raise ValueError('Candidate execution not confirmed')
    entry=read('entry/report.json')
    if not entry.get('completed') or not entry.get('process_closed') or entry.get('forced_cleanup'):
        raise ValueError('Unified entry did not stop normally')
    backend=read('backend-payloads/trace.json')
    if not backend.get('process_closed') or backend.get('detach')!='OK' or backend.get('failure'):
        raise ValueError('Backend trace incomplete')
    counts=backend['summary']['counts']
    if counts.get('finite-batch-consumer')!=2 or counts.get('finite-data-consumer')!=1:
        raise ValueError('Native consumer chain missing')
    graphs=[h['extra_observation']['native_graph'] for h in backend['hits']
            if 'native_graph' in h.get('extra_observation',{})]
    if sorted(set(g['count'] for g in graphs))!=[11,18]:
        raise ValueError('Native backend graphs missing')
    result={'schema':1,'binary_sha256':manifest['binary_sha256'],'evidence_sha256':evidence,
        'finite_frames':122,'finite_batches':2,'finite_bytes':93696,'menu_cycles':3,
        'candidate_sentinel_executed':True,'cmd_entry_verified':True,
        'native_backend_graph_sizes':[11,18], 'hardware_accuracy_verified':False,
        'live_view_verified':False,'complete_emulator':False,'flash_safety_verified':False}
    result['display_first_observed']=next(s['virtual_seconds'] for s in native['samples'] if s.get('display_enabled'))
    result['batch_first_observed']={str(n):next(s['virtual_seconds'] for s in native['samples']
        if s.get('capture',{}).get('finite_stats_status',{}).get('engines',{}).get('master',{}).get('finite-batches',0)>=n)
        for n in (1,2)}
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    result=check()
    if args.output:
        with args.output.open('x',encoding='utf-8') as handle: json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2))
