"""Build r9 in an independent verified r8 source snapshot."""
import argparse
import json
from pathlib import Path
import build_reference_qemu as reference
from build_z62_raw_stream import copy_verified_source
import run_z62_finite_stats as parent
import z62_preview_device as device


def build(jobs):
    prior=parent.verify_build(parent.DEFAULT_QEMU)
    parent_root=parent.DEFAULT_QEMU.parent.parent
    old=json.loads((parent_root/'reference-build-manifest.json').read_text(encoding='utf-8'))
    work=reference.guard_workspace(device.WORK,'z62',updates=True)
    identity=device.identity()
    work.mkdir(parents=True,exist_ok=False)
    (work/reference.MARKER).write_text(json.dumps(reference.identity('z62',True)),encoding='utf-8')
    source=work/'source/qemu-10.2.4'
    print('Preparing verified r8 source snapshot',flush=True)
    copy_verified_source(Path(old['source']),source,old['prepared_source_file_sha256'])
    device.apply_source(source)
    hashes=dict(old['prepared_source_file_sha256'])
    changed=list(device.INPUTS)+[p.name for p in device.HEADERS]
    for name in changed: hashes['hw/arm/'+name]=reference.upstream.digest(source/'hw/arm'/name)
    (work/'prepared-preview-source.json').write_text(json.dumps({'preview_device':identity,
        'source_hashes':hashes,'parent_binary_sha256':prior['binary_sha256'],'complete_build':False},indent=2),encoding='utf-8')
    msys=Path(old['msys2_dir'])
    binary=reference.run_build(source,work/'build',msys,jobs)
    reference.verify_devices(work/'build')
    runtime=work/'runtime';runtime.mkdir()
    dlls=reference.upstream.stage_windows(binary,msys,runtime)
    staged=runtime/binary.name
    checks=reference.smoke_checks(staged,'z62')
    if identity!=device.identity(): raise ValueError('Preview source changed during build')
    common={'binary':str(staged),'binary_sha256':reference.upstream.digest(staged),
            'builder_sha256':reference.upstream.digest(Path(__file__)),'preview_device':identity}
    for name in ('reference','functional','transaction','capcom','raw-stream','finite-stats'):
        previous=parent_root/(name+'-build-manifest.json')
        record=json.loads(previous.read_text(encoding='utf-8'));record.update(common)
        record['parent_manifest_sha256']=reference.upstream.digest(previous)
        if name=='reference':
            record.update(source=str(source),build=str(work/'build'),runtime=str(runtime),
                prepared_source_file_sha256=hashes,runtime_dll_sha256=dlls,binary_bytes=staged.stat().st_size,
                checks=checks,jobs=jobs,inherited_from=str(parent_root),firmware_run=False)
        elif name in ('functional','transaction'):
            key='generated_'+name+'_sha256';record['base_'+key]=record[key]
            record[key]={n:hashes['hw/arm/'+n] for n in record[key]}
        elif name=='finite-stats':
            record['base_generated_source_sha256']=record['generated_source_sha256']
            record['generated_source_sha256']={n:hashes['hw/arm/'+n] for n in record['generated_source_sha256']}
        else:
            record['base_source_board_sha256']=record['source_board_sha256']
            record['source_board_sha256']=hashes['hw/arm/nikon-z72.c']
            if name=='raw-stream':
                record['base_source_header_sha256']=record['source_header_sha256']
                record['source_header_sha256']=hashes['hw/arm/nikon-z62-raw-stream.h']
        with (work/(name+'-build-manifest.json')).open('x',encoding='utf-8') as handle: json.dump(record,handle,indent=2)
    manifest={**common,'schema':1,'version':device.VERSION,'checks':checks,
        'parent_binary_sha256':prior['binary_sha256'],
        'generated_source_sha256':{n:hashes['hw/arm/'+n] for n in changed}}
    with (work/'preview-build-manifest.json').open('x',encoding='utf-8') as handle: json.dump(manifest,handle,indent=2)
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--jobs',type=int,default=12)
    args=p.parse_args()
    if not 1<=args.jobs<=32: p.error('jobs must be 1..32')
    print(json.dumps(build(args.jobs),indent=2))
