"""Build the isolated C input ownership fix without modifying bound r65."""
import argparse
import json
from pathlib import Path
import shutil
import build_reference_qemu as reference
from build_z62_raw_stream import copy_verified_source
import run_z62_paired_ingress as parent
import z62_paired_handoff_device as device


def build(jobs):
    prior=parent.verify_build(); old_root=parent.DEFAULT_QEMU.parent.parent
    old=json.loads((old_root/'reference-build-manifest.json').read_text(encoding='utf-8'))
    work=reference.guard_workspace(device.WORK,'z62',updates=True)
    if shutil.disk_usage(work.parent).free<12*1024**3:
        raise ValueError('Need 12 GiB for an independent handoff build')
    ident=device.identity(); work.mkdir(parents=True,exist_ok=False)
    (work/reference.MARKER).write_text(json.dumps(reference.identity('z62',True)),encoding='utf-8')
    source=work/'source/qemu-10.2.4'
    print('Copying verified r65; correcting only level-C source ownership',flush=True)
    copy_verified_source(Path(old['source']),source,old['prepared_source_file_sha256'])
    changed=device.apply_source(source); hashes=dict(old['prepared_source_file_sha256'])
    for name in changed:
        hashes[name]=reference.upstream.digest(source/name)
    (work/'prepared-paired-handoff.json').write_text(json.dumps({'paired_handoff_device':ident,
        'source_hashes':hashes,'complete_build':False},indent=2),encoding='utf-8')
    msys=Path(old['msys2_dir']); built=reference.run_build(source,work/'build',msys,jobs)
    reference.verify_devices(work/'build'); runtime=work/'runtime'; runtime.mkdir()
    dlls=reference.upstream.stage_windows(built,msys,runtime); binary=runtime/built.name
    checks=reference.smoke_checks(binary,'z62')
    if ident!=device.identity():
        raise ValueError('Handoff adapter changed during build')
    common={'binary':str(binary),'binary_sha256':reference.upstream.digest(binary),
            'builder_sha256':reference.upstream.digest(Path(__file__)),'paired_handoff_device':ident}
    names=('reference','functional','transaction','capcom','raw-stream','finite-stats','preview',
           'capture-contacts','raw-boundary','continuous-stats','analog-input','scene-source','scene-file',
           'preview-results','preview-results-format','grid','grid-geometry','photo-results','video-isp',
           'video-isp-format','statistics-observe','raw-stop-control','mmio-filter','paired-ingress')
    for name in names:
        previous=old_root/(name+'-build-manifest.json')
        record=json.loads(previous.read_text(encoding='utf-8'))
        record.update(common); record['parent_manifest_sha256']=reference.upstream.digest(previous)
        if 'generated_source_sha256' in record:
            record['handoff_parent_generated_source_sha256']=dict(record['generated_source_sha256'])
            for filename in record['generated_source_sha256']:
                key=filename if filename in hashes else 'hw/arm/'+filename
                if key in changed:
                    record['generated_source_sha256'][filename]=hashes[key]
        if name=='reference':
            record.update(source=str(source),build=str(work/'build'),runtime=str(runtime),prepared_source_file_sha256=hashes,
                          runtime_dll_sha256=dlls,binary_bytes=binary.stat().st_size,jobs=jobs,checks=checks,
                          inherited_from=str(old_root),firmware_run=False)
        with (work/(name+'-build-manifest.json')).open('x',encoding='utf-8') as handle:
            json.dump(record,handle,indent=2)
    result={**common,'schema':1,'version':device.VERSION,'parent_binary_sha256':prior['binary_sha256'],
            'generated_source_sha256':{name:hashes[name] for name in changed},'checks':checks}
    with (work/'paired-handoff-build-manifest.json').open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--jobs',type=int,default=8)
    args=parser.parse_args()
    if not 1<=args.jobs<=32:
        parser.error('jobs must be 1..32')
    print(json.dumps(build(args.jobs),indent=2),flush=True)
