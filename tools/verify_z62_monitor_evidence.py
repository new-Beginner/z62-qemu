"""Verify the scoped monitor fix independently of camera/capture completeness."""
import argparse
import hashlib
import json
from pathlib import Path
from run_z62_preview import DEFAULT_QEMU, verify_build
from z62_qmp_transport import identity

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'analysis/z62-capture-r12'


def check():
    build=verify_build(DEFAULT_QEMU.resolve())
    source=identity()
    hashes={}
    def read(name):
        data=(BASE/name).read_bytes()
        hashes[name]=hashlib.sha256(data).hexdigest()
        return json.loads(data)
    native=read('qmp-recovery2.json')
    if (not native.get('completed') or not native.get('process_closed') or native.get('forced_cleanup')
            or native.get('firmware_loaded') is not False or native.get('transport')!=source or
            native.get('qemu_sha256')!=build['binary_sha256']):
        raise ValueError('Native monitor recovery evidence mismatch')
    if native['diagnostics']['late_replies']!=1 or native['diagnostics']['timed_out_requests']!=1:
        raise ValueError('Timeout/late-reply control was not exercised')
    firmware=read('qmp-firmware-recovery/report.json')
    session=read('qmp-firmware-recovery/session.json')
    recovery=firmware.get('monitor_recovery',{})
    if (not firmware.get('observation_completed') or not firmware.get('clean_exit') or
            firmware.get('monitor_transport')!=source or firmware.get('failure') or
            session['capcom_device']['binary_sha256']!=build['binary_sha256'] or
            recovery.get('pid')!=firmware.get('pid') or recovery.get('recovered_status',{}).get('running') is not True):
        raise ValueError('Original-firmware monitor recovery did not complete')
    for key in ('timed_out_requests','late_replies'):
        if recovery['diagnostics'][key]!=1: raise ValueError('Missing controlled recovery counter')
    later=[r for r in firmware['samples'] if r.get('virtual_seconds',0) and r['virtual_seconds']>2.5]
    if not later or any(r.get('observation_error') for r in later):
        raise ValueError('Observation did not continue after the timeout')
    for name in ('monitor-main-entry','monitor-candidate-entry'):
        record=read(name+'/report.json')
        if (not record.get('completed') or not record.get('process_closed') or record.get('forced_cleanup') or
                not record.get('monitor_transport_verified') or not record.get('half_press_http_verified') or
                record['status']['monitor_transport']['version']!=source['version']):
            raise ValueError('Actual console entry failed: '+name)
        if name.startswith('monitor-candidate') and record['status'].get('firmware_health_known') is not False:
            raise ValueError('Candidate health must remain unknown')
    return {'schema':1,'qemu_sha256':build['binary_sha256'],'monitor_transport':source,
            'evidence_sha256':hashes,'monitor_read_timeout_recovery_verified':True,
            'original_firmware_recovered_without_restart':True,'control_commands_replayed':False,
            'complete_emulator':False,'photo_capture_verified':False,'flash_safety_verified':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    result=check()
    if args.output:
        with args.output.open('x',encoding='utf-8') as out:json.dump(result,out,indent=2)
    print(json.dumps(result,indent=2))
