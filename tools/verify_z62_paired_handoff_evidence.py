"""Verify r66 and the red-to-green source handoff regression, preserving failures."""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import verify_z62_paired_ingress_evidence as parent
import run_z62_paired_handoff as host


def verify(directory):
    directory=directory.resolve(); build=host.verify_build()
    with patch.object(parent,'host',host):
        result=parent.verify(directory)
    hashes=result['artifact_sha256']
    def digest(path):
        value=hashlib.sha256(path.read_bytes()).hexdigest(); hashes[str(path)]=value
        return value
    path=directory/'handoff-2.json'; raw=path.read_bytes(); handoff=json.loads(raw)
    digest(path)
    parent.require(handoff['completed'] is True and handoff['qemu_sha256']==build['binary_sha256'] and
        handoff['retired_notifications']==1 and handoff['scheduled_old_work_and_output_backpressure_preserved'] is True and
        handoff['failed_replacement_preserves_notification_and_memory'] is True,'Handoff regression failed')
    probe=Path(__file__).with_name('probe_z62_paired_ingress_handoff.py')
    parent.require(digest(probe)==handoff['probe_sha256'] and
        digest(Path(__file__).with_name('probe_z62_paired_ingress.py'))==handoff['native_helper_sha256'],
        'Handoff proof source changed')
    digest(Path(__file__)); digest(Path(parent.__file__))
    outer=directory/'live-1/paired-handoff-lifecycle.json'
    if outer.exists():
        live=json.loads(outer.read_text(encoding='utf-8')); digest(outer)
        parent.require(digest(outer.with_name('paired-ingress-lifecycle.json'))==live['inherited_result_sha256'],
                       'Inherited original-firmware observation changed')
        for name,value in live['source_sha256'].items():
            parent.require(digest(Path(name))==value,'Handoff observer source changed')
        parent.require(all(live[k]==result['original_firmware_observation'][k] for k in
            ('completed_observation','process_closed','functional_acceptance_eligible','host_debugger_attached',
             'strict_mode_recovery_verified','video_new_pixels_reached_factory_lcd',
             'photo_return_new_pixels_reached_factory_lcd')),'Outer original-firmware verdict differs')
    result.update(version='2026.11.03-paired-handoff-evidence-r66',vmstate_version=54,
                  native_handoff_regression_verified=True,retired_notifications_are_completions=False)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Handoff verification evidence is immutable')
    result=verify(args.directory)
    with args.output.open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    print(json.dumps({'completed_verification':True,'qemu_sha256':result['qemu_sha256'],
        'artifact_count':len(result['artifact_sha256']),
        'original_firmware_observation':result.get('original_firmware_observation')},indent=2),flush=True)
