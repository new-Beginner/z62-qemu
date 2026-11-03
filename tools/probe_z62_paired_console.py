"""Exercise only an empty, dedicated local C camera card through its HTTP API."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image


def require(value,message):
    if not value:
        raise ValueError(message)


def run(url,output,resume=None,selector_only=False):
    parsed=urllib.parse.urlsplit(url)
    require(parsed.scheme=='http' and parsed.hostname=='127.0.0.1' and parsed.port and
            parsed.path in ('','/') and not parsed.query and not parsed.fragment,'Local isolated console required')
    url=url.rstrip('/'); output.mkdir(parents=True,exist_ok=False)
    result={'schema':1,'completed':False,'implementation_level':'C','factory_capture_chain_verified':False,
        'camera_accessed':False,'url':url,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'events':[],'states':[],'artifacts':{}}
    result['scenario']='selector-before-shutter' if selector_only else 'photo-video-playback'
    def save_json(name,data):
        with (output/name).open('x',encoding='utf-8') as handle:
            json.dump(data,handle,ensure_ascii=False,indent=2)
    def request(path,body=None):
        req=urllib.request.Request(url+path,data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=40) as response:
            return response.read()
    def status():
        value=json.loads(request('/software/status'))
        result['states'].append(value)
        return value
    def event(kind,payload):
        row={'type':kind,'payload':payload,'outcome':'unknown'}
        result['events'].append(row)
        try:
            value=json.loads(request('/camera/event',{'type':kind,'payload':payload}))
        except urllib.error.HTTPError as exc:
            row.update(outcome='rejected',status=exc.code,response=exc.read().decode('utf-8','replace'))
            raise
        row.update(outcome='accepted',response=value)
        return value
    def wait(label,predicate,seconds=360):
        deadline=time.monotonic()+seconds; next_report=0
        while time.monotonic()<deadline:
            state=status()
            if predicate(state):
                print(label+': confirmed at '+str(state['virtual_time_ns'])+' ns',flush=True)
                return state
            if state['pipeline_mode']['phase']=='timed-out':
                raise TimeoutError(label+' reached its virtual-time confirmation deadline')
            if time.monotonic()>=next_report:
                print(label+': '+state['pipeline_mode']['phase']+' at '+str(state['virtual_time_ns'])+' ns',flush=True)
                next_report=time.monotonic()+15
            time.sleep(.8)
        raise TimeoutError(label+' did not satisfy the observed-state gate')
    def ready(mode):
        return lambda s:s['pipeline_mode']['ready'] and s['pipeline_mode']['confirmed_mode']==mode
    def download(name):
        data=request('/software/file/'+urllib.parse.quote(name,safe=''))
        with (output/name).open('xb') as handle:
            handle.write(data)
        result['artifacts'][name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        return data
    try:
        state=status()
        require(state['pipeline_mode']['profile_version']=='2026.11.03-paired-console-r71','Unexpected console profile')
        require(state['card']['present'],'Dedicated test card required')
        previous=None
        if resume is not None:
            previous=json.loads(resume.read_text(encoding='utf-8'))
            require(previous.get('completed') is False and previous.get('failure')=={
                'type':'ModuleNotFoundError','message':"No module named 'rawpy'"} and
                len(previous.get('events',[]))==3 and
                [e['type'] for e in previous['events']]==['photo-format','shutter','shutter'] and
                all(e['outcome']=='accepted' for e in previous['events']),
                'Resume is restricted to the recorded missing-decoder failure')
            require(state['card']['photos']==1 and state['card']['videos']==0 and
                    state['card']['images']==previous['states'][-1]['card']['images'],
                    'The dedicated card changed since the interrupted validation')
            result['resumed_from']={'path':str(resume),'sha256':hashlib.sha256(resume.read_bytes()).hexdigest(),
                                   'capture_commands_replayed':0}
        else:
            require(not state['card']['images'],'Use a new empty test-only directory card')
        state=wait('initial photo output',ready('photo'))
        require(state['pipeline_mode']['output']['valid'],'No actual committed output')
        if selector_only:
            require(previous is None,'A selector-only control must use a fresh empty card')
            response=event('mode',{'mode':'video'})
            require(response['state']['mode']=='photo','Mode changed before a committed output')
            state=wait('video without prior shutter',ready('video'))
            result['video_mode_confirmation']=state['pipeline_mode']
            result['completed']=True
            return result
        if previous is None:
            event('photo-format',{'format':'jpeg-nef'})
            try:
                event('shutter',{'stage':'full','pressed':True})
            finally:
                event('shutter',{'stage':'full','pressed':False})
        state=wait('JPEG and NEF saved',lambda s:s['card']['photos']==1,120)
        photo=next(row for row in state['card']['images'] if row['kind']=='photo')
        metadata=photo['metadata']; lineage=metadata['output_lineage']
        require(lineage['valid'] and lineage['mode']=='photo' and
                lineage['publish_id']==metadata['native_scene_source']['publish_id'],'Saved photo lost its output provenance')
        for item in photo['files']:
            data=download(item['name'])
            if previous is not None:
                require(result['artifacts'][item['name']]==previous['artifacts'][item['name']],
                        'Saved photo bytes changed before independent validation resumed')
            if item['name'].endswith('.JPG'):
                with Image.open(BytesIO(data)) as image:
                    image.load()
                    result['jpeg_decode']={'format':image.format,'size':list(image.size)}
            elif item['name'].endswith('.NEF'):
                import rawpy
                with rawpy.imread(BytesIO(data)) as raw:
                    decoded=raw.raw_image.copy()
                    require(hashlib.sha256(decoded.astype('<u2').tobytes()).hexdigest()==metadata['raw14_sha256'],
                            'LibRaw pixels differ from the saved C source digest')
                    result['nef_decode']={'shape':list(decoded.shape),'rawpy':rawpy.__version__,
                        'libraw':list(rawpy.libraw_version),'raw14_sha256':metadata['raw14_sha256'],
                        'factory_equivalence_verified':False}
        result['photo_output_lineage']=lineage
        response=event('mode',{'mode':'video'})
        require(response['state']['mode']=='photo' and response['state']['pipeline_mode']['requested_mode']=='video',
                'A mode request was prematurely reported as completed')
        state=wait('video mode and current frame',ready('video'))
        result['video_mode_confirmation']=state['pipeline_mode']
        event('record',{'action':'start'})
        wait('continuous video samples',lambda s:s['video']['recording'] and s['video']['frames']>=4,180)
        event('record',{'action':'stop'})
        state=wait('MP4 saved',lambda s:s['card']['videos']==1 and s['video'].get('phase')=='saved',180)
        video=next(row for row in state['card']['images'] if row['kind']=='video')
        from z62_video_codec import audit_video
        result['video_decode']=audit_video(download(video['name']))
        full=json.loads(request('/software/item/'+urllib.parse.quote(video['name'],safe='')))
        save_json('video-item.json',full)
        event('mode',{'mode':'photo'})
        state=wait('return to photo current frame',ready('photo'))
        result['photo_return_confirmation']=state['pipeline_mode']
        event('playback',{'action':'open'})
        state=wait('video playback',lambda s:s['view']=='playback' and s['selected_image']==video['name'],120)
        event('playback',{'action':'previous'})
        wait('photo playback',lambda s:s['selected_image']==photo['name'],120)
        event('zoom',{'factor':2})
        wait('photo zoom',lambda s:s['zoom']==2,120)
        result['playback_zoom_verified']=True
        # Only this probe's newly created photo group is deleted; both downloads are retained above.
        event('delete',{})
        wait('test photo deletion',lambda s:s['card']['photos']==0 and s['card']['videos']==1,120)
        result['test_photo_deleted']=True
        event('playback',{'action':'close'})
        wait('live photo restored',lambda s:s['view']=='live' and ready('photo')(s),120)
        result['completed']=True
    except Exception as exc:
        result['failure']={'type':type(exc).__name__,'message':str(exc)}
    finally:
        save_json('result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('states','events')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8685')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resume-missing-decoder',type=Path)
    parser.add_argument('--selector-only',action='store_true')
    args=parser.parse_args()
    raise SystemExit(0 if run(args.url,args.output,args.resume_missing_decoder,args.selector_only)['completed'] else 1)
