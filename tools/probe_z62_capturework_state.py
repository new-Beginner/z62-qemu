"""Read the active C1.70 capture-work/group configuration without controls or IRQs."""
import argparse
import importlib
import json
from pathlib import Path
import sys
import time
import urllib.request

from probe_z62_capture_submit import owner,profiles,stopped_snapshot,MASTER_SHA
from record_z62_action_evidence import workspace,digest,require,bind
from z62_kernel_event_layout import resolve,contract,read_words
from probe_z62_prepare_packet import clock

BUFFER=(0x1A08,0x1A14,0x1A18,0x1A24,0x1A3C,0x1A40,0x1A44,0x1A48,0x1A4C,
        0x1A50,0x1A54,0x1A58,0x1A5C,0x1A60,0x1A64,0x1A68,0x1A6C,0x1A80)
GROUP=(*range(0x3800,0x3988,4),*range(0x3A00,0x3A54,4),*range(0x3A94,0x3ABC,4),
       0x3B18,0x3B24,0x3B3C,0x3B44,0x3B48,0x3B4C,0x3B50,0x3B60,0x3B80,
       0x3C50,0x3C60,0x3C80,0x3D50,0x3D60,0x3D80)


def run(url,session,output):
    session,output=map(workspace,(session,output)); output.mkdir(parents=True,exist_ok=False)
    record={'schema':1,'version':'2026.11.04-capturework-state-r86','completed_observation':False,
        'camera_accessed':False,'controls_sent':[],'guest_memory_written':False,
        'completion_injected':False,'functional_acceptance_eligible':False}
    remote=None
    journal=(output/'observations.jsonl').open('x',encoding='utf-8')
    def request(endpoint):
        require(url.startswith('http://127.0.0.1:') and endpoint in ('/paired/diagnostics','/software/status','/status'),
                'Read-only local console required')
        with urllib.request.urlopen(url.rstrip('/')+endpoint,timeout=40) as response: return json.load(response)
    try:
        bind(session,output,output/'source-binding.json')
        image=(session/'inputs/master.bin').read_bytes(); layout=contract(image)
        require(digest(session/'inputs/master.bin')==MASTER_SHA,'Original master required')
        deadline=time.monotonic()+900; report=0
        while time.monotonic()<deadline:
            state=request('/paired/diagnostics')
            journal.write(json.dumps({'kind':'initial','value':state})+'\n'); journal.flush()
            if time.monotonic()>=report:
                print('INITIAL',state['virtual_time_ns'],state['pipeline_mode']['phase'],flush=True); report=time.monotonic()+20
            if state['pipeline_mode']['ready'] and state['selector']['original_observed_gate']:
                record['initial']=state; break
            time.sleep(2)
        else: raise TimeoutError('Initial observation limit')
        software=request('/software/status'); record['software_before']=software
        require(not software['half_pressed'] and not software['full_pressed'] and not software['card']['images'] and
                state['capture_flow']['active_word']==0,'Fresh no-control state required')
        status=request('/status'); require(Path(status['package_root']).samefile(session),'Wrong console session')
        profile=profiles(session); record['profile']=profile
        paths=list((session/'runs').glob('*/command.json')); require(len(paths)==1,'Single VM required')
        command=json.loads(paths[0].read_text(encoding='utf-8')); binary=Path(command[0])
        require(digest(binary)==profile['diagnostic_profile']['binary_sha256'],'Runtime differs')
        port=int(command[command.index('-gdb')+1].rsplit(':',1)[1]); record['owner']=owner(port,binary)
        record['source_sha256']={str(p):digest(p) for p in (Path(__file__),paths[0],
            Path(__file__).with_name('z62_kernel_event_layout.py'),session/'source/analyze/qemu_display.py')}
        sys.path.insert(0,str(session/'source')); Remote=importlib.import_module('analyze.qemu_display').Remote
        remote=Remote(port); record['attachment_stop']=remote.command('?'); remote.select_thread(1)
        def words(offsets): return {hex(0x20068000+o):hex(read_words(remote,0x20068000+o,1)[0]) for o in offsets}
        record['virtual_time_ns']=clock(remote); record['kernel_event']=resolve(remote,layout)
        record['queue_and_capture']=stopped_snapshot(remote)
        record['frontend']=words((0x500,0x1D00,0x1D04,0x1E78,0x1E7C,0x1F00))
        record['packing']=words(range(0x1514,0x1534,4)); record['buffers']=words(BUFFER)
        record['packing_lut_words']=read_words(remote,0x20069600,128)
        record['group']=words(GROUP)
        record['capture_controls']=words((0,4,8,0xC,0x10,0x14,0x18,0x60,0x100,0x104))
        record['configuration_readback_is_write_provenance']=False
        record['completed_observation']=True
    except Exception as exc: record['failure']={'type':type(exc).__name__,'message':str(exc)}
    finally:
        if remote is not None:
            try: record['detach']=remote.command('D')
            except Exception as exc: record['cleanup_error']=str(exc)
            remote.sock.close()
        try: record['after_detach']=request('/paired/diagnostics')
        except Exception as exc: record['after_detach_error']={'type':type(exc).__name__,'message':str(exc)}
        if 'source_sha256' in record:
            record['sources_unchanged']=all(digest(Path(p))==sha for p,sha in record['source_sha256'].items())
        journal.close()
        with (output/'result.json').open('x',encoding='utf-8') as handle: json.dump(record,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:record.get(k) for k in ('completed_observation','failure','detach','cleanup_error','sources_unchanged')},ensure_ascii=False),flush=True)
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8688'); parser.add_argument('--session',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    result=run(args.url,args.session,args.output)
    raise SystemExit(0 if result['completed_observation'] and result.get('detach')=='OK' else 1)
