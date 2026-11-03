"""Independent r69 build, preserving r66 and all source-bound ancestors."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import build_reference_qemu as reference
from build_z62_raw_stream import copy_verified_source
import run_z62_paired_handoff as parent
import z62_output_lineage_device as device


def resume_workspace(work):
    work=Path(work).absolute()
    if work.resolve()!=device.WORK.resolve() or not work.resolve().is_relative_to(reference.ROOT/'.build'):
        raise ValueError('Unexpected lineage resume directory')
    for part in (work,*work.parents):
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
            raise ValueError('Linked resume directory is protected')
        if (part/reference.CONVERSION_MARKER).exists():
            raise ValueError('Converted source tree is protected')
        marker=part/reference.MARKER
        if marker.exists() and part!=work:
            raise ValueError('Resume directory is nested in a protected workspace')
    marker=work/reference.MARKER
    if not marker.is_file() or json.loads(marker.read_text(encoding='utf-8'))!=reference.identity('z62',True):
        raise ValueError('Lineage resume marker differs')
    if (work/'runtime').exists() or any(work.glob('*-build-manifest.json')):
        raise ValueError('Built or packaged output is immutable; choose a new version')
    return work.resolve()


def build(jobs, msys_root=None, resume=False, toolchain_manifest=None):
    prior=parent.verify_build(); old_root=parent.DEFAULT_QEMU.parent.parent
    old=json.loads((old_root/'reference-build-manifest.json').read_text(encoding='utf-8'))
    work=resume_workspace(device.WORK) if resume else reference.guard_workspace(device.WORK,'z62',updates=True)
    if shutil.disk_usage(work.parent).free<12*1024**3:
        raise ValueError('Need 12 GiB for an independent output-lineage build')
    ident=device.identity()
    source=work/'source/qemu-10.2.4'
    if resume:
        if (work/'output-lineage-build-manifest.json').exists():
            raise ValueError('Completed builds are immutable')
        prepared=json.loads((work/'prepared-output-lineage.json').read_text(encoding='utf-8'))
        if prepared['output_lineage_device']!=ident or prepared['complete_build'] is not False:
            raise ValueError('Prepared lineage source identity differs')
        changed=device.render({name:(Path(old['source'])/name).read_bytes() for name in device.INPUTS})
        hashes=dict(old['prepared_source_file_sha256'])
        for name,data in changed.items():
            hashes[name]=hashlib.sha256(data).hexdigest()
        if hashes!=prepared['source_hashes']:
            raise ValueError('Prepared source inventory differs')
        print('Verifying all prepared source before resuming',flush=True)
        for name,digest in hashes.items():
            if reference.upstream.digest(source/name)!=digest:
                raise ValueError('Prepared source changed: '+name)
    else:
        work.mkdir(parents=True,exist_ok=False)
        (work/reference.MARKER).write_text(json.dumps(reference.identity('z62',True)),encoding='utf-8')
        print('Copying verified r66; adding only opt-in output provenance',flush=True)
        copy_verified_source(Path(old['source']),source,old['prepared_source_file_sha256'])
        changed=device.apply_source(source); hashes=dict(old['prepared_source_file_sha256'])
        for name in changed:
            hashes[name]=reference.upstream.digest(source/name)
        (work/'prepared-output-lineage.json').write_text(json.dumps({'output_lineage_device':ident,
            'source_hashes':hashes,'complete_build':False},indent=2),encoding='utf-8')
    msys=Path(msys_root) if msys_root is not None else Path(old['msys2_dir'])
    toolchain=Path(toolchain_manifest) if toolchain_manifest else msys.parent/'z62-toolchain-manifest.json'
    if toolchain.is_file():
        locked=json.loads(toolchain.read_text(encoding='utf-8'))
        if locked.get('complete') is not True or Path(locked['root']).resolve()!=msys.resolve():
            raise ValueError('Toolchain lock does not describe this root')
        queried=subprocess.run([str(msys/'usr/bin/bash.exe'),'--noprofile','--norc','-c',
            'export PATH=/usr/bin:/ucrt64/bin:/c/Windows/System32; pacman -Q'],
            capture_output=True,text=True,encoding='utf-8',timeout=30,check=True,
            env=dict(os.environ,MSYSTEM='UCRT64',PATH=str(msys/'usr/bin')+';'+os.environ.get('SystemRoot','C:/Windows')+'/System32'))
        if queried.stdout.splitlines()!=locked['package_versions']:
            raise ValueError('Installed dependency versions differ from the selected toolchain lock')
    built=reference.run_build(source,work/'build',msys,jobs)
    reference.verify_devices(work/'build'); runtime=work/'runtime'; runtime.mkdir()
    dlls=reference.upstream.stage_windows(built,msys,runtime); binary=runtime/built.name
    checks=reference.smoke_checks(binary,'z62')
    if ident!=device.identity():
        raise ValueError('Lineage adapter/header changed during build')
    common={'binary':str(binary),'binary_sha256':reference.upstream.digest(binary),
            'builder_sha256':reference.upstream.digest(Path(__file__)),'output_lineage_device':ident}
    if toolchain.is_file():
        common['toolchain_manifest_sha256']=reference.upstream.digest(toolchain)
        common['toolchain_manifest']=str(toolchain)
    names=('reference','functional','transaction','capcom','raw-stream','finite-stats','preview',
           'capture-contacts','raw-boundary','continuous-stats','analog-input','scene-source','scene-file',
           'preview-results','preview-results-format','grid','grid-geometry','photo-results','video-isp',
           'video-isp-format','statistics-observe','raw-stop-control','mmio-filter','paired-ingress','paired-handoff')
    for name in names:
        previous=old_root/(name+'-build-manifest.json')
        record=json.loads(previous.read_text(encoding='utf-8'))
        record.update(common); record['parent_manifest_sha256']=reference.upstream.digest(previous)
        if 'msys2_dir' in record:
            record['msys2_dir']=str(msys)
        if 'generated_source_sha256' in record:
            record['lineage_parent_generated_source_sha256']=dict(record['generated_source_sha256'])
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
    with (work/'output-lineage-build-manifest.json').open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--jobs',type=int,default=8)
    parser.add_argument('--msys-root',type=Path); parser.add_argument('--resume',action='store_true')
    parser.add_argument('--toolchain-manifest',type=Path)
    args=parser.parse_args()
    if not 1<=args.jobs<=32:
        parser.error('jobs must be 1..32')
    print(json.dumps(build(args.jobs,args.msys_root,args.resume,args.toolchain_manifest),indent=2),flush=True)
