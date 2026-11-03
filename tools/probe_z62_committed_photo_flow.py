"""Actual C photo workflow on committed r69 frames; no factory AF claim."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

import numpy as np
from PIL import Image
import rawpy

ROOT=Path(__file__).resolve().parents[1]


def require(value,message):
    if not value:
        raise ValueError(message)


def run(output):
    output=output.absolute()
    require(output.resolve().is_relative_to(ROOT),'Output must stay in workspace')
    output.mkdir(parents=True,exist_ok=False)
    url='http://127.0.0.1:8688'
    result={'schema':1,'completed_flow':False,'implementation_level':'C','factory_af_verified':False,
        'factory_capture_chain_verified':False,'camera_accessed':False,'events':[],'states':[],
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'artifacts':{}}
    journal=(output/'events.jsonl').open('x',encoding='utf-8')
    def record(kind,row):
        journal.write(json.dumps({'kind':kind,'value':row},ensure_ascii=False)+'\n'); journal.flush()
    def request(path,body=None):
        req=urllib.request.Request(url+path,data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=40) as response:
            return response.read()
    def state():
        value=json.loads(request('/software/status')); result['states'].append(value); record('state',value); return value
    def event(kind,payload):
        row={'type':kind,'payload':payload,'outcome':'unknown'}; result['events'].append(row); record('send',row)
        try:
            response=json.loads(request('/camera/event',{'type':kind,'payload':payload}))
        except urllib.error.HTTPError as exc:
            row.update(outcome='rejected',status=exc.code,response=exc.read().decode('utf-8','replace')); record('reply',row); raise
        row.update(outcome='accepted',response=response); record('reply',row)
        return response
    def wait(label,predicate,seconds=180):
        deadline=time.monotonic()+seconds; report=0
        while time.monotonic()<deadline:
            try:
                value=state()
            except (OSError,ValueError) as exc:
                record('read-error',{'label':label,'type':type(exc).__name__,'message':str(exc)}); time.sleep(1); continue
            if predicate(value):
                print(label+': confirmed at '+str(value['virtual_time_ns'])+' ns',flush=True); return value
            if time.monotonic()>=report:
                print(label+': '+value['pipeline_mode']['phase'],flush=True); report=time.monotonic()+15
            time.sleep(.7)
        raise TimeoutError(label+' did not reach its observed-state gate')
    def ready(s):
        return s['pipeline_mode']['ready'] and s['pipeline_mode']['confirmed_mode']=='photo'
    def capture(expected_count):
        try:
            event('shutter',{'stage':'full','pressed':True})
        finally:
            event('shutter',{'stage':'full','pressed':False})
        return wait('photo '+str(expected_count)+' saved and released',lambda s:s['card']['photos']==expected_count and
                    not s['half_pressed'] and not s['full_pressed'])
    def download(item):
        decoded={}
        for file in item['files']:
            data=request('/software/file/'+file['name'])
            with (output/file['name']).open('xb') as handle:
                handle.write(data)
            digest=hashlib.sha256(data).hexdigest()
            require(digest==file['sha256'],'Downloaded media hash differs from card record')
            result['artifacts'][file['name']]={'sha256':digest,'bytes':len(data)}
            if file['name'].endswith('.JPG'):
                with Image.open(BytesIO(data)) as image:
                    image.load(); decoded['jpeg']=image.convert('RGB')
            else:
                with rawpy.imread(BytesIO(data)) as raw:
                    array=raw.raw_image.copy()
                require(hashlib.sha256(array.astype('<u2').tobytes()).hexdigest()==item['metadata']['raw14_sha256'],
                        'Independent LibRaw samples differ from recorded C RAW digest')
                decoded['raw_mean']=float(array.mean()); decoded['raw_shape']=list(array.shape)
        row=item['metadata']['output_lineage']; source=item['metadata']['native_scene_source']
        require(row['valid'] and row['mode']=='photo' and row['pixel_identity_proven'] is False and
            all(row[k]==source[v] for k,v in (('epoch','epoch'),('publish_id','publish_id'),
                ('frame_id','frame_id'),('time_ns','virtual_time_ns'))),'Saved photo source attribution differs')
        return decoded
    try:
        initial=wait('initial committed photo',ready,360)
        require(initial['card']['present'] and not initial['card']['images'],'A fresh empty dedicated test card is required')
        diagnostic=json.loads(request('/paired/diagnostics')); result['initial_diagnostic']=diagnostic
        require(diagnostic.get('persistent_diagnostic_profile',{}).get('version')=='2026.11.03-persistent-diagnostic-r74',
                'The permanent diagnostic profile is required')
        event('lens',{'focus_target':0.65})
        settled=wait('manual C lens settled',lambda s:not s['lens']['moving'] and abs(s['lens']['focus_position']-.65)<1e-8)
        wait('settled lens frame committed',lambda s:ready(s) and s['virtual_time_ns']>=settled['virtual_time_ns']+250_000_000)
        first=capture(1); photo_a=first['card']['images'][0]; decoded_a=download(photo_a)
        require(abs(photo_a['metadata']['lens']['focus_position']-.65)<1e-8 and
                photo_a['metadata']['lens']['moving'] is False,'Saved lens state had not settled')
        event('exposure',{'iso':200})
        previous_revision=photo_a['metadata']['scene_revision']
        wait('new ISO frame committed',lambda s:ready(s) and s['native_scene']['scene_revision']>previous_revision)
        second=capture(2); photo_b=second['card']['images'][-1]; decoded_b=download(photo_b)
        require(photo_a['metadata']['exposure']['iso']==100 and photo_b['metadata']['exposure']['iso']==200,
                'Saved exposure metadata does not match the two requested states')
        require(decoded_b['raw_mean']>decoded_a['raw_mean']*1.1,'ISO change did not change actual decoded RAW brightness')
        result['exposure_pixels']={'iso100_mean':decoded_a['raw_mean'],'iso200_mean':decoded_b['raw_mean'],
            'raw_shape':decoded_b['raw_shape'],'model_calibrated_to_camera':False}
        event('playback',{'action':'open'})
        wait('photo playback',lambda s:s['view']=='playback' and s['selected_image']==photo_b['name'])
        event('zoom',{'factor':2})
        wait('2x playback',lambda s:s['zoom']==2)
        frame=request('/software/frame')
        with (output/'playback-2x.jpg').open('xb') as handle:
            handle.write(frame)
        with Image.open(BytesIO(frame)) as image:
            actual=np.asarray(image.convert('RGB'),dtype=np.float32)
        image=decoded_b['jpeg']; w,h=image.size
        expected=image.crop((w/4,h/4,3*w/4,3*h/4)).resize((w,h),Image.Resampling.NEAREST)
        mse=float(np.mean((actual-np.asarray(expected,dtype=np.float32))**2))
        full_mse=float(np.mean((actual-np.asarray(image,dtype=np.float32))**2))
        require(mse<150 and full_mse>mse+50,'Decoded display is not the expected 2x photo crop')
        result['playback_pixels']={'zoom':2,'expected_crop_mse':mse,'unzoomed_mse':full_mse}
        event('playback',{'action':'previous'})
        wait('previous photo',lambda s:s['selected_image']==photo_a['name'])
        event('playback',{'action':'next'})
        wait('next photo',lambda s:s['selected_image']==photo_b['name'])
        event('delete',{})
        wait('photo B group deleted',lambda s:s['card']['photos']==1 and s['selected_image']==photo_a['name'])
        event('delete',{})
        final=wait('photo A group deleted',lambda s:s['card']['photos']==0 and not s['card']['images'])
        require(final['card']['used_payload_bytes']==0,'Grouped delete left accounted media bytes')
        event('playback',{'action':'close'})
        wait('live photo restored',lambda s:s['view']=='live' and ready(s))
        result['completed_flow']=True
    except Exception as exc:
        result['failure']={'type':type(exc).__name__,'message':str(exc)}
    finally:
        try:
            result['final_diagnostic']=json.loads(request('/paired/diagnostics'))
        except (OSError,ValueError) as exc:
            result['final_diagnostic_error']={'type':type(exc).__name__,'message':str(exc)}
        result['unperturbed_flow_verified']=bool(result['completed_flow'] and
            result.get('final_diagnostic',{}).get('functional_acceptance_eligible') is True)
        journal.close()
        with (output/'result.json').open('x',encoding='utf-8') as handle:
            json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:result.get(k) for k in ('completed_flow','unperturbed_flow_verified',
        'exposure_pixels','playback_pixels','failure')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); result=run(args.output)
    raise SystemExit(0 if result['completed_flow'] else 1)
