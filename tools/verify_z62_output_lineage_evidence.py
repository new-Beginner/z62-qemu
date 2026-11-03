"""Verify native gates and retain the limited scope of interactive results."""
import argparse
import hashlib
import json
from pathlib import Path

import run_z62_output_lineage as hardware

ROOT=Path(__file__).resolve().parents[1]


def require(value,message):
    if not value:
        raise ValueError(message)


def verify(output):
    build=hardware.verify_build()
    hashes={}
    def read(name):
        path=ROOT/name; data=path.read_bytes(); hashes[name]=hashlib.sha256(data).hexdigest()
        return json.loads(data)
    native=read('analysis/z62-output-lineage-r69/native-1.json')
    paired=read('analysis/z62-output-lineage-r69/paired-regression-1.json')
    handoff=read('analysis/z62-output-lineage-r69/handoff-regression-1.json')
    for record in (native,paired,handoff):
        require(record['completed'] is True and record['qemu_sha256']==build['binary_sha256'],
                'Native evidence belongs to another binary or failed')
    for key in ('default_off_preserves_data','actual_video_provenance','publication_not_completion',
        'backpressure_preserves_record','mode_is_commit_mode','readonly','reset',
        'rejected_isp_has_no_committed_tags','legacy_stream_provenance','actual_photo_provenance'):
        require(native.get(key) is True,'Missing native gate: '+key)
    require(len(paired['launches'])==3 and all(row['process_closed'] and row['exit_code']==0 for row in paired['launches']),
            'Paired native processes did not close normally')
    for row in paired['launches']:
        require(hashlib.sha256(Path(row['log']).read_bytes()).hexdigest()==row['log_sha256'],'Native log changed')
        hashes[str(Path(row['log']).relative_to(ROOT)).replace('\\','/')]=row['log_sha256']
    require(handoff['retired_notifications']==1 and handoff['scheduled_old_work_and_output_backpressure_preserved'] and
            handoff['failed_replacement_preserves_notification_and_memory'],'Handoff contract differs')
    photo=read('analysis/z62-paired-console-r71/http-2/result.json')
    selector=read('analysis/z62-paired-console-r71/selector-before-shutter-1/result.json')
    recording=read('analysis/z62-paired-console-r71/recording-1/result.json')
    returned=read('analysis/z62-paired-console-r71/recording-2/result.json')
    require(photo['completed'] is False and photo['failure']['type']=='TimeoutError','Photo-to-video boundary changed')
    require(photo['jpeg_decode']['size']==[640,424] and photo['nef_decode']['shape']==[1006,1514],
            'Independent photo sizes differ')
    for name,entry in photo['artifacts'].items():
        path=ROOT/'analysis/z62-paired-console-r71/http-2'/name
        require(path.stat().st_size==entry['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256'],
                'Downloaded photo changed')
        hashes[path.relative_to(ROOT).as_posix()]=entry['sha256']
    require(selector['completed'] is True and selector['video_mode_confirmation']['ready'],'Selector control failed')
    require(recording['every_video_frame_has_output_provenance'] and recording['wrong_mode_shutter_rejected'],
            'Video provenance or actual key refusal failed')
    video=ROOT/'analysis/z62-paired-console-r71/recording-1/Z62_0001.MP4'
    digest=hashlib.sha256(video.read_bytes()).hexdigest()
    require(digest==recording['video_sha256']==returned['video_sha256'],'Saved video changed')
    hashes[video.relative_to(ROOT).as_posix()]=digest
    require(returned['completed'] is False and returned['failure']['type']=='HTTPError',
            'Return failure must remain explicitly recorded')
    item=read('analysis/z62-paired-console-r71/recording-1/video-item.json')
    samples=item['metadata']['samples']; decoded=recording['independent_decode']
    require(len(samples)==len(decoded['timestamps_us'])==9 and decoded['duration_us']==296543,
            'Actual recording counts or duration differ')
    for sample in samples:
        row=sample['output_lineage']; source=sample['native_scene_source']
        require(row['valid'] and row['mode']=='video' and row['pixel_identity_proven'] is False and
                all(row[k]==source[v] for k,v in (('epoch','epoch'),('publish_id','publish_id'),
                    ('frame_id','frame_id'),('time_ns','virtual_time_ns'))),'A video sample lost its source identity')
    closed=read('analysis/z62-paired-console-r71/session-4-final/session.json')
    require(closed['clean_exit'] is True and closed['paired_profile']['hardware_version']==build['version'] and
            closed['parameters']['groups']['group23.bin']['zero_body'] is False,'Final session metadata regressed')
    for folder in ('session-2-before-close','session-3-video-before-close','session-4-final'):
        prefix='analysis/z62-paired-console-r71/'+folder
        archive=read(prefix+'/archive.json')
        for name,expected in archive['file_sha256'].items():
            data=(ROOT/prefix/name).read_bytes()
            require(hashlib.sha256(data).hexdigest()==expected,'Archived session source changed: '+name)
            hashes[prefix+'/'+name]=expected
    for name in ('tools/run_z62_paired_console.py','tools/z62_paired_console.py','tools/z62_paired_camera.py',
                 'tools/assets/z62-paired-console.js','tests/test_z62_paired_console.py',
                 'tests/test_z62_paired_camera.py'):
        hashes[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    result={'schema':1,'verification_completed':True,'scope':'artifact-consistency-review',
        'qemu_sha256':build['binary_sha256'],'native_gates_passed':True,
        'photo_decode_and_lineage_verified':True,'selector_without_prior_shutter_verified':True,
        'video_file_decode_and_lineage_verified':True,'video_frames':len(samples),
        'interactive_full_flow_verified':False,'photo_to_video_verified':False,'video_return_photo_verified':False,
        'factory_capture_chain_verified':False,'factory_af_verified':False,'flash_safety_verified':False,
        'file_sha256':hashes}
    with output.open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='file_sha256'}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); verify(args.output)
