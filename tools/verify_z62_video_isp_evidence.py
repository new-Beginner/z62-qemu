"""Replay r59b source packets / LCD evidence; retain strict recovery limits."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image
import run_z62_video_isp_format as host
import z62_scene_packet as packet
import z62_scene_response as measure

ROOT=Path(__file__).resolve().parents[1]
MAIN_BYTES=1520*846*3//2
WORK_BYTES=1520*423


def require(value,message):
    if not value: raise ValueError(message)


def verify(case,output):
    if output.exists(): raise FileExistsError('Existing video evidence inventory is immutable')
    build=host.verify_build()
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    result=read(case/'video-isp-lifecycle.json');life=read(case/'lifecycle.json');trace=read(case/'trace.json')
    inputs=read(case/'inputs.json')
    require(result['qemu_sha256']==build['binary_sha256'],'Video binary identity differs')
    require(result['completed_observation'] is True and result['process_closed'] is True and
            trace['process_closed'] is True and trace['detach']=='OK','Original video window did not close')
    require(result['sources_unchanged_during_run'] is True and not result['read_errors'],'Video observation/source failure')
    for name,digest in result['source_sha256'].items():
        require(hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,'Observed source changed: '+name)
    sources=[result['initial_source'],*result['publications']]
    for source in sources:
        payload=packet.make_packet(Image.new('RGB',(64,64),(source['gray'],)*3),
            epoch=source['epoch'],publish_id=source['publish_id'],frame_id=source['frame_id'],
            virtual_time_ns=source['virtual_time_ns'])
        info,raw=packet.parse_packet(payload)
        require(info['raw_sha256']==source['raw_sha256'] and
                hashlib.sha256(payload).hexdigest()==source['packet_sha256'],'Source packet cannot be replayed')
        offset=502*2272+752*3//2
        require(raw[offset:offset+48].hex()==source['raw_reference'],'RAW reference differs from source')
    for row in result['observations']:
        png=case/row['lcd_file'];source=row['expected_source']
        require(hashlib.sha256(png.read_bytes()).hexdigest()==row['lcd_sha256'],'Saved LCD changed')
        with Image.open(png) as img:
            actual=measure.measure(source['gray'],bytes.fromhex(source['raw_reference']),
                [bytes.fromhex(p) for p in row['raw_patches']],
                [{'y':bytes.fromhex(p['y']),'uv':bytes.fromhex(p['uv'])} for p in row['nv12_patches']],img)
        require(actual==row['measure'],'Saved pixel measurement differs')
        tags={'scene-used-publish-id':'publish_id','scene-used-epoch':'epoch',
              'scene-used-frame-id':'frame_id','scene-used-time-ns':'virtual_time_ns'}
        tag_match=all(row['source'][key]==source[name] for key,name in tags.items())
        mode_match=row['mode_heights'][1]==576 if row['kind'].startswith('video') else row['mode_heights'][1] in (680,682)
        verified=bool(tag_match and mode_match and row['display_enabled'] and row['index']==3 and
                      all(actual[key] for key in ('raw_matches','nv12_matches','lcd_matches')))
        require(verified==row['pixel_response_verified'],'Pixel verdict differs from evidence')
    before,after,photo=result['video_before'],result['video_after'],result['photo_after']
    video_ok=bool(before and after and before['pixel_response_verified'] and after['pixel_response_verified'] and
        before['expected_source']['gray']==40 and after['expected_source']['gray']==210 and
        after['video_batches']>after['expected_source']['video_batches_before'])
    photo_ok=bool(photo and photo['pixel_response_verified'] and photo['expected_source']['gray']==40)
    require(video_ok==result['video_new_pixels_reached_factory_lcd'] and
            photo_ok==result['photo_return_new_pixels_reached_factory_lcd'],'Scene response summary differs')
    require(result['strict_mode_recovery_verified']==life['assessment']['recovery_observed'],
            'Old strict recovery verdict was changed')
    samples=inputs['counter_samples']
    require(all(row['known'] is True and not row['errors'] for row in samples),'Unknown video producer sample')
    for row in samples:
        s=row['stream'];b=s['video-batches']
        require(s['video-main-bytes']==b*4*MAIN_BYTES and s['video-work-bytes']==b*8*WORK_BYTES,
                'Committed MAIN/WORK counts are inconsistent')
    require(max(row['stream']['video-batches'] for row in samples)>0,'No video work was committed')
    native=read(case.parent/'native-format-1.json');legacy=read(case.parent/'legacy-format-1.json')
    require(native['completed'] is True and legacy['completed'] is True and
            native['binary_sha256']==legacy['binary_sha256']==build['binary_sha256'],
            'New/old native device checks missing')
    require(native['owned_raw_snapshot'] is True and native['late_rejection_all_output_bytes_preserved'] is True,
            'Source ownership or failure preflight proof missing')
    evidence=sorted(p for p in case.parent.rglob('*') if p.is_file() and
                    p.suffix in ('.json','.png','.txt','.md','.log'))
    names=('tools/z62_video_isp_device.py','tools/run_z62_video_isp.py','tools/build_z62_video_isp.py',
        'tools/z62_video_isp_format_device.py','tools/run_z62_video_isp_format.py','tools/build_z62_video_isp_format.py',
        'tools/probe_z62_video_isp.py','tools/probe_z62_video_isp_format.py','tools/trace_z62_video_isp_lifecycle.py',
        'tools/verify_z62_video_isp_evidence.py','tools/check_z62_video_isp_pixels.py','tests/test_z62_video_isp.py',
        'tests/native/z62_video_isp_pixels_test.c','qemu/z62-video-isp/nikon-z62-video-pixels.h',
        'qemu/z62-video-isp/nikon-z62-video-profile.h','qemu/z62-video-isp/nikon-z62-video-isp.h')
    receipt={'schema':1,'version':'2026.11.03-video-isp-evidence-r59b','verification_completed':True,
        'qemu_sha256':build['binary_sha256'],'original_guest_seconds':life['final_state']['virtual_seconds'],
        'original_stops':trace['stops'],'source_packets_replayed':len(sources),
        'pixel_observations_remeasured':len(result['observations']),
        'video_new_pixels_reached_factory_lcd':video_ok,'photo_return_new_pixels_reached_factory_lcd':photo_ok,
        'video_factory_state':{'ready':after['original_ready'],'input_inhibit':after['input_inhibit']} if after else None,
        'last_producer_sample':samples[-1],'selector_events':life['events'],
        'original_ready_callback_hits':life['original_ready_callback_hits'],
        'strict_lifecycle_assessment':life['assessment'],
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names},
        'evidence_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence},
        'work_is_temporal_history':False,'guest_raw_layout_converted':False,
        'whole_frame_pixel_identity_verified':False,'physical_isp_equivalent':False,'whole_camera_verified':False}
    with output.open('x',encoding='utf-8') as handle:json.dump(receipt,handle,indent=2)
    print(json.dumps({key:receipt[key] for key in ('verification_completed','original_guest_seconds','original_stops',
        'source_packets_replayed','pixel_observations_remeasured','video_new_pixels_reached_factory_lcd',
        'photo_return_new_pixels_reached_factory_lcd','video_factory_state','strict_lifecycle_assessment')},indent=2))
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();verify(args.case,args.output)
