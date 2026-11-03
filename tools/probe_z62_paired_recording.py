"""Continue an observed video-mode control using its dedicated empty test card."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

from z62_video_codec import audit_video


def require(value,message):
    if not value:
        raise ValueError(message)


def run(proof,output,resume=None):
    previous=json.loads(proof.read_text(encoding='utf-8'))
    require(previous.get('completed') is True and previous.get('scenario')=='selector-before-shutter',
            'A completed selector-before-shutter control is required')
    url=previous['url']; parsed=urllib.parse.urlsplit(url)
    require(parsed.scheme=='http' and parsed.hostname=='127.0.0.1' and parsed.port and
            parsed.path in ('','/') and not parsed.query and not parsed.fragment,'Local console required')
    output.mkdir(parents=True,exist_ok=False)
    result={'schema':1,'completed':False,'implementation_level':'C','factory_capture_chain_verified':False,
        'camera_accessed':False,'proof_sha256':hashlib.sha256(proof.read_bytes()).hexdigest(),
        'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'events':[],'states':[]}
    def request(path,body=None):
        req=urllib.request.Request(url+path,data=None if body is None else json.dumps(body).encode(),
                                  headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=40) as response:
            return response.read()
    def state():
        value=json.loads(request('/software/status')); result['states'].append(value); return value
    def event(kind,payload,reject=None):
        row={'type':kind,'payload':payload,'outcome':'unknown'}; result['events'].append(row)
        try:
            response=json.loads(request('/camera/event',{'type':kind,'payload':payload}))
        except urllib.error.HTTPError as exc:
            message=exc.read().decode('utf-8','replace'); row.update(outcome='rejected',status=exc.code,message=message)
            if reject and exc.code==400 and reject in message:
                return
            raise
        row.update(outcome='accepted',response=response)
        require(reject is None,'A forbidden operation was accepted')
        return response
    def wait(label,predicate,timeout=180):
        deadline=time.monotonic()+timeout; report=0
        while time.monotonic()<deadline:
            value=state()
            if predicate(value):
                print(label+': confirmed at '+str(value['virtual_time_ns'])+' ns',flush=True); return value
            require(value['video'].get('phase')!='error','Video failed: '+str(value['video'].get('error')))
            require(value['pipeline_mode']['phase']!='timed-out','Mode confirmation reached its virtual deadline')
            if time.monotonic()>=report:
                print(label+': '+value['pipeline_mode']['phase']+' / '+value['video']['phase'],flush=True)
                report=time.monotonic()+15
            time.sleep(.8)
        raise TimeoutError(label+' not observed')
    try:
        first=state(); old=previous['states'][-1]
        if resume is not None:
            prior=json.loads(resume.read_text(encoding='utf-8'))
            last=prior['events'][-1]
            require(prior.get('completed') is False and prior.get('every_video_frame_has_output_provenance') is True and
                    prior.get('proof_sha256')==result['proof_sha256'] and last.get('outcome')=='rejected' and
                    last.get('type')=='mode' and last.get('payload')=={'mode':'photo'} and
                    last.get('status')==400 and 'camera_operation_busy' in last.get('message',''),
                    'Resume requires the explicit post-playback busy rejection')
            require(first['clock_epoch']==old['clock_epoch'] and first['card']['photos']==0 and first['card']['videos']==1,
                    'Continuation session or card changed')
            item=next(row for row in first['card']['images'] if row['kind']=='video')
            data=request('/software/file/'+urllib.parse.quote(item['name'],safe=''))
            require(hashlib.sha256(data).hexdigest()==prior['video_sha256'],'Saved video bytes changed')
            for key in ('wrong_mode_shutter_rejected','video_sha256','independent_decode','every_video_frame_has_output_provenance'):
                result[key]=prior[key]
            result['resumed_from']={'path':str(resume),'sha256':hashlib.sha256(resume.read_bytes()).hexdigest(),
                'record_commands_replayed':0,'prior_mode_request_explicitly_rejected':True}
            wait('post-playback input released',lambda s:not s['half_pressed'] and not s['full_pressed'] and
                 s['view']=='live' and s['pipeline_mode']['ready'])
            event('mode',{'mode':'photo'})
            photo=wait('return photo output',lambda s:s['pipeline_mode']['ready'] and
                       s['pipeline_mode']['confirmed_mode']=='photo',360)
            result['photo_return_confirmation']=photo['pipeline_mode']
            result['completed']=True
            return result
        require(first['clock_epoch']==old['clock_epoch'] and first['pipeline_mode']['ready'] and
                first['pipeline_mode']['confirmed_mode']=='video' and not first['card']['images'],
                'Control session changed or its test card is no longer empty')
        event('shutter',{'stage':'full','pressed':True},reject='pipeline_mode_not_confirmed')
        require(not state()['full_pressed'] and not state()['card']['images'],
                'Rejected photo operation changed the test camera')
        result['wrong_mode_shutter_rejected']=True
        event('record',{'action':'start'})
        wait('recording samples',lambda s:s['video']['recording'] and s['video']['frames']>=4)
        event('record',{'action':'start'},reject='already_recording')
        event('record',{'action':'stop'})
        final=wait('MP4 commit',lambda s:s['card']['videos']==1 and s['video'].get('phase')=='saved')
        event('record',{'action':'stop'},reject='not_recording')
        item=next(row for row in final['card']['images'] if row['kind']=='video')
        name=item['name']; data=request('/software/file/'+urllib.parse.quote(name,safe=''))
        with (output/name).open('xb') as handle:
            handle.write(data)
        full=json.loads(request('/software/item/'+urllib.parse.quote(name,safe='')))
        with (output/'video-item.json').open('x',encoding='utf-8') as handle:
            json.dump(full,handle,ensure_ascii=False,indent=2)
        result['video_sha256']=hashlib.sha256(data).hexdigest()
        result['independent_decode']=audit_video(data)
        samples=full['metadata']['samples']
        require(len(samples)==len(result['independent_decode']['timestamps_us']),'Decoded frame count differs')
        for sample in samples:
            row=sample['output_lineage']; source=sample['native_scene_source']
            require(row['valid'] and row['mode']=='video' and sample['pipeline_mode']=='video' and
                    all(row[k]==source[v] for k,v in (('epoch','epoch'),('publish_id','publish_id'),
                       ('frame_id','frame_id'),('time_ns','virtual_time_ns'))),
                    'Video frame lost its committed-output provenance')
        result['every_video_frame_has_output_provenance']=True
        event('playback',{'action':'open'})
        wait('video playback',lambda s:s['view']=='playback' and s['selected_image']==name)
        event('playback',{'action':'close'})
        wait('live video restored',lambda s:s['view']=='live' and s['pipeline_mode']['ready'] and
             not s['half_pressed'] and not s['full_pressed'])
        event('mode',{'mode':'photo'})
        photo=wait('return photo output',lambda s:s['pipeline_mode']['ready'] and
                   s['pipeline_mode']['confirmed_mode']=='photo',360)
        result['photo_return_confirmation']=photo['pipeline_mode']
        result['completed']=True
    except Exception as exc:
        result['failure']={'type':type(exc).__name__,'message':str(exc)}
    finally:
        with (output/'result.json').open('x',encoding='utf-8') as handle:
            json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('events','states')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resume-after-playback',type=Path)
    args=parser.parse_args()
    raise SystemExit(0 if run(args.proof,args.output,args.resume_after_playback)['completed'] else 1)
