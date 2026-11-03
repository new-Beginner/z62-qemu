"""Same r72 diagnostic configuration and initial gate, with no shutter input."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request


def require(value,message):
    if not value:
        raise ValueError(message)


def run(url,session,output):
    parsed=urllib.parse.urlsplit(url)
    require(parsed.scheme=='http' and parsed.hostname=='127.0.0.1' and parsed.port and
            parsed.path in ('','/') and not parsed.query and not parsed.fragment,'Local diagnostic console required')
    module=session/'source/tools/z62_console.py'; tree=ast.parse(module.read_text(encoding='utf-8'))
    profiles=[ast.literal_eval(node.value) for top in tree.body if isinstance(top,ast.ClassDef) and top.name=='Z62Machine'
        for node in top.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='diagnostic_profile' for t in node.targets)]
    require(len(profiles)==1 and profiles[0]['version']=='2026.11.03-paired-diagnostic-r72','Unexpected generated host')
    profile=profiles[0]
    for name,digest in profile['runtime_file_sha256'].items():
        require(hashlib.sha256((Path(profile['runtime_binary']).parent/name).read_bytes()).hexdigest()==digest,
                'Runtime bytes differ')
    output.mkdir(parents=True,exist_ok=False)
    result={'schema':1,'completed_observation':False,'scenario':'same-original-gate; selector-video; no-shutter',
        'camera_accessed':False,'guest_software_written':False,'profile':profile,'events':[],'samples':[],
        'read_errors':[],'functional_acceptance_eligible':True,
        'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (Path(__file__),module,session/'source/tools/z62_paired_diagnostic_console.py')}}
    journal=(output/'observations.jsonl').open('x',encoding='utf-8')
    def emit(kind,row):
        journal.write(json.dumps({'kind':kind,'value':row},ensure_ascii=False)+'\n'); journal.flush()
    def request(endpoint,body=None):
        req=urllib.request.Request(url.rstrip('/')+endpoint,data=None if body is None else json.dumps(body).encode(),
                                  headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=40) as response:
            return json.load(response)
    def sample(label):
        value=request('/paired/diagnostics'); value['label']=label
        result['samples'].append(value); emit('sample',value)
        if value['host_capture_attempted']:
            result['functional_acceptance_eligible']=False
        return value
    def wait(label,predicate,seconds):
        deadline=time.monotonic()+seconds; report=0
        while time.monotonic()<deadline:
            try:
                row=sample(label)
            except (OSError,ValueError) as exc:
                error={'label':label,'type':type(exc).__name__,'message':str(exc)}
                result['read_errors'].append(error); emit('read-error',error); time.sleep(2); continue
            if time.monotonic()>=report:
                print(json.dumps({'label':label,'ns':row['virtual_time_ns'],'selector':row['selector'],
                    'output_mode':row['output']['mode'],'pipeline_phase':row['pipeline_mode']['phase']}),flush=True)
                report=time.monotonic()+20
            if predicate(row):
                return row
            time.sleep(2)
        raise TimeoutError(label+' exceeded host observation limit')
    try:
        result['initial_gate']=wait('same-initial-photo-and-original-gate',lambda row:row['pipeline_mode']['ready'] and
            row['pipeline_mode']['confirmed_mode']=='photo' and row['selector']['original_observed_gate'],900)
        software=request('/software/status')
        require(software['card']['present'] and not software['card']['images'] and not software['half_pressed'] and
                not software['full_pressed'],'A fresh empty control card and released inputs are required')
        row={'type':'mode','payload':{'mode':'video'},'outcome':'unknown'}; result['events'].append(row); emit('send',row)
        try:
            response=request('/camera/event',{'type':'mode','payload':{'mode':'video'}})
        except urllib.error.HTTPError as exc:
            row.update(outcome='rejected',status=exc.code,body=exc.read().decode('utf-8','replace')); emit('reply',row); raise
        row.update(outcome='accepted',response=response); emit('reply',row)
        final=wait('same-profile-video-no-shutter',lambda value:value['pipeline_mode']['phase']=='timed-out' or
            (value['pipeline_mode']['ready'] and value['pipeline_mode']['confirmed_mode']=='video'),420)
        result['final']=final
        result['video_mode_confirmed']=bool(final['pipeline_mode']['ready'] and final['pipeline_mode']['confirmed_mode']=='video')
        result['final_card']=request('/software/status')['card']
        require(not result['final_card']['images'],'The no-shutter control created media')
        result['completed_observation']=True
    except Exception as exc:
        result['failure']={'type':type(exc).__name__,'message':str(exc)}
    finally:
        try:
            result['final_diagnostic']=sample('final-diagnostic')
        except (OSError,ValueError) as exc:
            result['final_diagnostic_error']={'type':type(exc).__name__,'message':str(exc)}
        result['source_unchanged']=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==digest
            for p,digest in result['source_sha256'].items())
        journal.close()
        with (output/'result.json').open('x',encoding='utf-8') as handle:
            json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:result.get(k) for k in ('completed_observation','video_mode_confirmed',
        'functional_acceptance_eligible','source_unchanged','failure')}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8688')
    parser.add_argument('--session',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); result=run(args.url,args.session,args.output)
    raise SystemExit(0 if result['completed_observation'] and result['source_unchanged'] else 1)
