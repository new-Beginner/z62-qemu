"""Observe original selector propagation after an actual shared full-shutter action."""
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
    module=session/'source/tools/z62_console.py'
    tree=ast.parse(module.read_text(encoding='utf-8'))
    profiles=[ast.literal_eval(node.value) for top in tree.body if isinstance(top,ast.ClassDef) and top.name=='Z62Machine'
        for node in top.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='diagnostic_profile' for t in node.targets)]
    require(len(profiles)==1 and profiles[0]['version']=='2026.11.03-paired-diagnostic-r72','Unexpected generated host')
    profile=profiles[0]
    for name,digest in profile['runtime_file_sha256'].items():
        path=Path(profile['runtime_binary']).parent/name
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==digest,'Runtime bytes changed')
    output.mkdir(parents=True,exist_ok=False)
    result={'schema':1,'completed_observation':False,'camera_accessed':False,'guest_software_written':False,
        'scenario':'initial-output-and-original-gate; full-shutter; selector-video',
        'profile':profile,'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (Path(__file__),module,session/'source/tools/z62_paired_diagnostic_console.py')},
        'events':[],'samples':[],'read_errors':[],'functional_acceptance_eligible':True}
    journal=(output/'observations.jsonl').open('x',encoding='utf-8')
    def emit(kind,row):
        journal.write(json.dumps({'kind':kind,'value':row},ensure_ascii=False)+'\n'); journal.flush()
    def request(endpoint,body=None):
        req=urllib.request.Request(url.rstrip('/')+endpoint,data=None if body is None else json.dumps(body).encode(),
                                  headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=40) as response:
            return json.load(response)
    def sample(label):
        row=request('/paired/diagnostics'); row['label']=label
        result['samples'].append(row); emit('sample',row)
        if row['host_capture_attempted']:
            result['functional_acceptance_eligible']=False
        return row
    def event(kind,payload):
        row={'type':kind,'payload':payload,'outcome':'unknown'}; result['events'].append(row); emit('send',row)
        try:
            response=request('/camera/event',{'type':kind,'payload':payload})
        except urllib.error.HTTPError as exc:
            row.update(outcome='rejected',status=exc.code,body=exc.read().decode('utf-8','replace')); emit('reply',row); raise
        row.update(outcome='accepted',response=response); emit('reply',row)
    def wait(label,predicate,seconds):
        deadline=time.monotonic()+seconds; report=0
        while time.monotonic()<deadline:
            try:
                row=sample(label)
            except (OSError,ValueError) as exc:
                error={'label':label,'type':type(exc).__name__,'message':str(exc)}
                result['read_errors'].append(error); emit('read-error',error)
                print(label+': read unavailable; preserving this VM',flush=True); time.sleep(2); continue
            if time.monotonic()>=report:
                print(json.dumps({'label':label,'ns':row['virtual_time_ns'],'selector':row['selector'],
                    'output_mode':row['output']['mode'],'pipeline_phase':row['pipeline_mode']['phase']},ensure_ascii=False),flush=True)
                report=time.monotonic()+20
            if predicate(row):
                return row
            time.sleep(2)
        raise TimeoutError(label+' exceeded its host observation limit')
    try:
        initial=wait('initial-photo-and-original-gate',lambda row:row['pipeline_mode']['ready'] and
            row['pipeline_mode']['confirmed_mode']=='photo' and row['selector']['original_observed_gate'],900)
        software=request('/software/status')
        require(software['card']['present'] and not software['card']['images'],'Use an empty dedicated test card')
        result['initial_gate']=initial
        event('shutter',{'stage':'full','pressed':True})
        event('shutter',{'stage':'full','pressed':False})
        deadline=time.monotonic()+120
        while True:
            software=request('/software/status')
            if software['card']['photos']==1 and not software['half_pressed'] and not software['full_pressed']:
                break
            require(time.monotonic()<deadline,'Photo input or C card commit did not finish')
            time.sleep(1)
        result['photo']=software['card']['images'][0]
        result['after_photo']=sample('after-photo-released')
        event('mode',{'mode':'video'})
        last=wait('video-selector-propagation',lambda row:row['pipeline_mode']['phase']=='timed-out' or
            (row['pipeline_mode']['ready'] and row['pipeline_mode']['confirmed_mode']=='video'),420)
        result['final']=last
        result['video_mode_confirmed']=bool(last['pipeline_mode']['ready'] and last['pipeline_mode']['confirmed_mode']=='video')
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
        'functional_acceptance_eligible','source_unchanged','failure')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8688')
    parser.add_argument('--session',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    record=run(args.url,args.session,args.output)
    raise SystemExit(0 if record['completed_observation'] and record['source_unchanged'] else 1)
