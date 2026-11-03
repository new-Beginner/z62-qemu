"""Test separated shutter stages on the same r72 host after a controlled fresh restart."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request


def require(value,message):
    if not value:
        raise ValueError(message)


def run(proof,output):
    control=json.loads(proof.read_text(encoding='utf-8'))
    require(control['completed_observation'] and control['video_mode_confirmed'] and control['source_unchanged'] and
            control['functional_acceptance_eligible'],'A successful same-profile no-shutter control is required')
    # The control launcher defaults to this explicitly local, isolated endpoint.
    url='http://127.0.0.1:8688'
    output.mkdir(parents=True,exist_ok=False)
    result={'schema':1,'completed_observation':False,'camera_accessed':False,'guest_software_written':False,
        'control_sha256':hashlib.sha256(proof.read_bytes()).hexdigest(),'events':[],'samples':[],
        'read_errors':[],'functional_acceptance_eligible':True,
        'source_sha256':{**control['source_sha256'],str(Path(__file__)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    journal=(output/'observations.jsonl').open('x',encoding='utf-8')
    def log(kind,value):
        journal.write(json.dumps({'kind':kind,'value':value},ensure_ascii=False)+'\n'); journal.flush()
    def request(endpoint,body=None):
        req=urllib.request.Request(url+endpoint,data=None if body is None else json.dumps(body).encode(),
                                  headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=40) as response:
            return json.load(response)
    def event(kind,payload):
        row={'type':kind,'payload':payload,'outcome':'unknown'}; result['events'].append(row); log('send',row)
        try:
            row['response']=request('/camera/event',{'type':kind,'payload':payload})
        except urllib.error.HTTPError as exc:
            row.update(outcome='rejected',status=exc.code,body=exc.read().decode('utf-8','replace')); log('reply',row); raise
        row['outcome']='accepted'; log('reply',row)
    def sample(label):
        row=request('/paired/diagnostics'); row['label']=label; result['samples'].append(row); log('sample',row)
        if row['host_capture_attempted']:
            result['functional_acceptance_eligible']=False
        return row
    def wait(label,predicate,seconds):
        deadline=time.monotonic()+seconds; report=0
        while time.monotonic()<deadline:
            try:
                row=sample(label)
            except (OSError,ValueError) as exc:
                error={'label':label,'type':type(exc).__name__,'message':str(exc)}
                result['read_errors'].append(error); log('read-error',error); time.sleep(2); continue
            if time.monotonic()>=report:
                print(json.dumps({'label':label,'ns':row['virtual_time_ns'],'selector':row['selector'],
                    'mode':row['output']['mode'],'phase':row['pipeline_mode']['phase']}),flush=True)
                report=time.monotonic()+20
            if predicate(row):
                return row
            time.sleep(2)
        raise TimeoutError(label+' exceeded the host observation limit')
    def released_state(predicate,seconds=120):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            state=request('/software/status'); log('software-state',state)
            if predicate(state):
                return state
            time.sleep(.7)
        raise TimeoutError('Input stage not observed')
    try:
        before=request('/software/status')
        require(before['pipeline_mode']['ready'] and before['mode']=='video' and not before['card']['images'],
                'The selected control session is no longer in its verified empty-video state')
        require(before['pipeline_mode']['output']['epoch']==control['final_diagnostic']['output']['epoch'],
                'The endpoint belongs to another VM epoch')
        row={'type':'restart','outcome':'unknown'}; result['events'].append(row); log('send',row)
        row['response']=request('/restart',{}); row['outcome']='accepted'; log('reply',row)
        first=wait('fresh-photo-and-original-gate',lambda s:s['pipeline_mode']['ready'] and
            s['pipeline_mode']['confirmed_mode']=='photo' and s['selector']['original_observed_gate'],900)
        fresh=request('/software/status')
        require(fresh['clock_epoch']!=before['clock_epoch'] and not fresh['card']['images'],'Restart did not create a fresh empty VM')
        result['initial_gate']=first
        event('shutter',{'stage':'half','pressed':True})
        half=released_state(lambda s:s['half_pressed'])
        released_state(lambda s:s['half_pressed'] and s['virtual_time_ns']>=half['virtual_time_ns']+200_000_000)
        result['after_half']=sample('separated-half-before-full')
        event('shutter',{'stage':'full','pressed':True})
        full=released_state(lambda s:s['full_pressed'] and s['card']['photos']==1)
        released_state(lambda s:s['full_pressed'] and s['virtual_time_ns']>=full['virtual_time_ns']+200_000_000)
        event('shutter',{'stage':'full','pressed':False})
        released_state(lambda s:not s['full_pressed'] and s['half_pressed'])
        event('shutter',{'stage':'half','pressed':False})
        done=released_state(lambda s:not s['full_pressed'] and not s['half_pressed'])
        result['photo']=done['card']['images'][0]
        result['after_release']=sample('full-and-half-released')
        event('mode',{'mode':'video'})
        final=wait('video-after-separated-stages',lambda s:s['pipeline_mode']['phase']=='timed-out' or
            (s['pipeline_mode']['ready'] and s['pipeline_mode']['confirmed_mode']=='video'),420)
        result['final']=final
        result['video_mode_confirmed']=bool(final['pipeline_mode']['ready'] and final['pipeline_mode']['confirmed_mode']=='video')
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
    parser.add_argument('--proof',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); result=run(args.proof,args.output)
    raise SystemExit(0 if result['completed_observation'] and result['source_unchanged'] else 1)
