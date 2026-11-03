"""Recheck permanent fault artifacts and C photo/UI evidence without a live VM."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path

import numpy as np
from PIL import Image
import rawpy

import run_z62_output_lineage as hardware
from z62_async_video_card import AsyncVideoCard

ROOT=Path(__file__).resolve().parents[1]


def require(value,message):
    if not value:
        raise ValueError(message)


def verify(output):
    hashes={}
    def read(path):
        data=path.read_bytes(); hashes[path.relative_to(ROOT).as_posix()]=hashlib.sha256(data).hexdigest(); return data
    native_root=ROOT/'analysis/z62-persistent-diagnostic-r74/native-fault-2'
    native=json.loads(read(native_root/'result.json'))
    require(native['completed'] and native['raw_stack_survives_cleanup'] and native['process_closed'] and
        native['guest_firmware_executed'] is False and native['functional_acceptance_eligible'] is False,
        'Native fault mechanism evidence differs')
    log=native_root/'permanent/vm-scratch/first-timeout/host-gdb.txt'
    require(hashlib.sha256(read(log)).hexdigest()==native['capture']['log_sha256'],'Persistent raw stack changed')
    require(not (native_root/'vm-scratch').exists(),'Native VM scratch was not actually removed')
    flow_root=ROOT/'analysis/z62-persistent-diagnostic-r74/photo-flow-1'
    flow=json.loads(read(flow_root/'result.json'))
    require(flow['completed_flow'] and flow['unperturbed_flow_verified'] and
            flow['final_diagnostic']['host_capture_attempted'] is False,'C photo flow was incomplete or perturbed')
    photos={}
    for state in flow['states']:
        for item in state['card']['images']:
            photos[item['name']]=item
    require(len(photos)==2,'Expected two actual photo groups')
    means=[]; jpeg_b=None
    for index,item in enumerate(sorted(photos.values(),key=lambda row:row['name'])):
        meta=item['metadata']; row=meta['output_lineage']; source=meta['native_scene_source']
        require(row['valid'] and row['mode']=='photo' and row['pixel_identity_proven'] is False and
            all(row[k]==source[v] for k,v in (('epoch','epoch'),('publish_id','publish_id'),
                ('frame_id','frame_id'),('time_ns','virtual_time_ns'))),'Photo lost its committed source')
        require(meta['exposure']['iso']==(100,200)[index] and abs(meta['lens']['focus_position']-.65)<1e-8,
                'Photo settings differ from the requested C model states')
        for file in item['files']:
            data=read(flow_root/file['name'])
            require(hashlib.sha256(data).hexdigest()==file['sha256'],'Downloaded photo bytes changed')
            if file['name'].endswith('.NEF'):
                with rawpy.imread(BytesIO(data)) as raw:
                    array=raw.raw_image.copy()
                require(array.shape==(1006,1514) and hashlib.sha256(array.astype('<u2').tobytes()).hexdigest()==meta['raw14_sha256'],
                        'Independent NEF samples no longer match the saved C digest')
                means.append(float(array.mean()))
            else:
                with Image.open(BytesIO(data)) as image:
                    image.load(); require(image.size==(640,424),'JPEG dimensions changed')
                    if index==1:
                        jpeg_b=image.convert('RGB')
    require(means[1]>means[0]*1.1,'Decoded exposure response is absent')
    with Image.open(BytesIO(read(flow_root/'playback-2x.jpg'))) as image:
        actual=np.asarray(image.convert('RGB'),dtype=np.float32)
    expected=jpeg_b.crop((160,106,480,318)).resize((640,424),Image.Resampling.NEAREST)
    mse=float(np.mean((actual-np.asarray(expected,dtype=np.float32))**2))
    require(mse<150,'Saved playback pixels do not reproduce the expected 2x crop')
    ui_root=ROOT/'artifacts/z62-committed-ui-r75-1'
    card=AsyncVideoCard(ui_root)
    try:
        summary=card.summary(); require(summary['photos']==1,'GUI photo did not survive normal close/reopen')
        item=summary['images'][0]; require(item['metadata']['exposure']['iso']==400,'GUI draft was not actually applied')
        for file in item['files']:
            data=card.read(file['name']); require(hashlib.sha256(data).hexdigest()==file['sha256'],'Persisted GUI file differs')
            if file['name'].endswith('.NEF'):
                with rawpy.imread(BytesIO(data)) as raw:
                    require(hashlib.sha256(raw.raw_image.astype('<u2').tobytes()).hexdigest()==item['metadata']['raw14_sha256'],
                            'GUI NEF failed independent sample verification')
    finally:
        card.close()
    for name in ('photo-playback-controls.jpg','photo-playback-pane.jpg'):
        path=ROOT/'analysis/z62-committed-ui-r75'/name
        with Image.open(BytesIO(read(path))) as image:
            image.verify()
    build=hardware.verify_build()
    require(build['binary_sha256']==native['qemu_sha256'],'Core identity differs')
    result={'schema':1,'evidence_verification_completed':True,'qemu_sha256':build['binary_sha256'],
        'persistent_fault_test_verified':True,'spontaneous_timeout_root_cause_verified':False,
        'c_photo_flow_unperturbed_verified':True,'independent_nef_mean_values':means,'playback_crop_mse':mse,
        'gui_saved_iso':400,'gui_card_close_reopen_verified':True,'implementation_level':'C',
        'factory_capture_chain_verified':False,'factory_af_verified':False,'flash_safety_verified':False,
        'file_sha256':hashes}
    with output.open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='file_sha256'}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); verify(args.output)
