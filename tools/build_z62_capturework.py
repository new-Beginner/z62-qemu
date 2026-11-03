"""Build independent r89 from the source-bound r69 parent inside workspace."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
from unittest.mock import patch

import build_reference_qemu as reference
from build_z62_raw_stream import copy_verified_source
import run_z62_output_lineage as parent
import z62_capturework_device as device
import z62_workspace_paths as paths


def compile_native(source,build,msys,jobs):
    """Keep GCC's assembler temporary filename in the verified ASCII alias.

    The inherited builder exports /tmp, which MSYS expands to the relocated
    Unicode physical root. Do not change that frozen builder or its receipts.
    """
    build.mkdir(parents=True,exist_ok=True)
    previous=build/'config.log'
    if previous.is_file():
        archive=build.parent/'configure-attempts'; archive.mkdir(exist_ok=True)
        target=archive/('config-'+str(len(list(archive.glob('config-*.log')))+1)+'.log')
        with target.open('xb') as handle: handle.write(previous.read_bytes())
        meson_log=build/'meson-logs/meson-log.txt'
        if meson_log.is_file():
            with target.with_name(target.stem+'-meson.log').open('xb') as handle: handle.write(meson_log.read_bytes())
    scratch=str(paths.ALIAS/'.runtime/tmp').replace('\\','/')
    ucrt=str(msys/'ucrt64').replace('\\','/')
    env=dict(os.environ,MSYSTEM='UCRT64',CHERE_INVOKING='1',PYTHONUTF8='1',PYTHONIOENCODING='utf-8',
        LANG='C.UTF-8',LC_ALL='C.UTF-8',MSYS2_ENV_CONV_EXCL='TMP;TEMP;TMPDIR;GCC_EXEC_PREFIX',
        GCC_EXEC_PREFIX=ucrt+'/lib/gcc/',CC='gcc --sysroot='+ucrt,CXX='g++ --sysroot='+ucrt,
        PATH=str(msys/'usr/bin')+';'+os.environ.get('SystemRoot','C:/Windows')+'/System32',
        WINDRES=shlex.join(['windres','--use-temp-file','-I',Path(os.path.relpath(source,build)).as_posix()]))
    commands=['export PATH=/ucrt64/bin:/usr/bin:/c/Windows/System32',
        'export TMP='+shlex.quote(scratch)+' TEMP='+shlex.quote(scratch)+' TMPDIR='+shlex.quote(scratch),
        'cd '+shlex.quote(reference.upstream.msys_path(build)),
        shlex.quote(reference.upstream.msys_path(source/'configure'))+' '+shlex.join(reference.CONFIGURE),
        f'ninja -j {jobs} qemu-system-arm.exe']
    command=[str(msys/'usr/bin/bash.exe'),'--noprofile','--norc','-c',' && '.join(commands)]
    log=build.parent/('native-build-'+str(len(list(build.parent.glob('native-build-*.log')))+1)+'.log')
    print('Configure/Ninja stdout and stderr:',log,flush=True)
    with log.open('xb') as handle: result=subprocess.run(command,env=env,stdout=handle,stderr=subprocess.STDOUT)
    if result.returncode:
        print('\n'.join(log.read_text(encoding='utf-8',errors='replace').splitlines()[-35:]),flush=True)
        raise subprocess.CalledProcessError(result.returncode,command)
    return build/'qemu-system-arm.exe'


def build(jobs,resume=False,resume_copy=False,refresh=False):
    prior=parent.verify_build(); old_root=parent.DEFAULT_QEMU.parent.parent
    old=json.loads((old_root/'reference-build-manifest.json').read_text(encoding='utf-8'))
    if resume or refresh:
        work=device.WORK.resolve()
        prepared=json.loads((work/'prepared-capturework.json').read_text(encoding='utf-8'))
        if (work/'runtime').exists() or (work/'capturework-build-manifest.json').exists():
            raise ValueError('Completed output is immutable')
    elif resume_copy:
        work=device.WORK.resolve()
        if {p.name for p in work.iterdir()}!={reference.MARKER,'source'} or \
            json.loads((work/reference.MARKER).read_text())!=reference.identity('z62',True):
            raise ValueError('Only an untouched pre-adapter source-copy failure may resume')
        for path in (work,*work.parents):
            if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
                raise ValueError('Linked source-copy recovery directory')
    else:
        work=reference.guard_workspace(device.WORK,'z62',updates=True)
    if not work.is_relative_to(reference.ROOT/'.build') or shutil.disk_usage(work.parent).free<12*1024**3:
        raise ValueError('Need a new workspace build directory and 12 GiB free')
    work=paths.WorkspacePath(work); source=work/'source/qemu-10.2.4'
    ident=device.identity()
    if resume or refresh:
        hashes=prepared['source_hashes']
        for name,expected in hashes.items():
            if reference.upstream.digest(source/name)!=expected: raise ValueError('Prepared source changed: '+name)
        if refresh:
            archive=work/'prepared-attempts'/str(len(list((work/'prepared-attempts').glob('*')))+1)
            archive.mkdir(parents=True,exist_ok=False)
            with (archive/'prepared-capturework.json').open('xb') as handle:
                handle.write((work/'prepared-capturework.json').read_bytes())
            for name in prepared['changed']:
                target=archive/name; target.parent.mkdir(parents=True,exist_ok=True)
                with target.open('xb') as handle: handle.write((source/name).read_bytes())
            changed=device.render({name:(Path(old['source'])/name).read_bytes() for name in device.INPUTS})
            hashes=dict(old['prepared_source_file_sha256'])
            for name,data in changed.items():
                (source/name).write_bytes(data); hashes[name]=hashlib.sha256(data).hexdigest()
            record={'capturework_device':ident,'source_hashes':hashes,'changed':list(changed),
                'complete_build':False,'previous_preparation_preserved':str(archive)}
            (work/'prepared-capturework.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
        else:
            if prepared['capturework_device']!=ident: raise ValueError('Prepared device source changed')
            changed={name:(source/name).read_bytes() for name in prepared['changed']}
    else:
        if not resume_copy:
            work.mkdir(parents=True,exist_ok=False)
            (work/reference.MARKER).write_text(json.dumps(reference.identity('z62',True)),encoding='utf-8')
        print('Copying verified r69 into an independent r89 source tree',flush=True)
        physical_source=Path(str(source)).resolve()
        if resume_copy:
            for path in physical_source.rglob('*'):
                if path.is_file() and path.relative_to(physical_source).as_posix() not in old['prepared_source_file_sha256']:
                    raise ValueError('Unknown file in partial snapshot')
        copy_verified_source(Path(old['source']),physical_source,old['prepared_source_file_sha256'],resume=resume_copy)
        changed=device.apply_source(source); hashes=dict(old['prepared_source_file_sha256'])
        for name in changed: hashes[name]=reference.upstream.digest(source/name)
        (work/'prepared-capturework.json').write_text(json.dumps({'capturework_device':ident,
            'source_hashes':hashes,'changed':list(changed),'complete_build':False},indent=2),encoding='utf-8')
    lock_path=device.ROOT/'.runtime/relocated-toolchain-manifest-r73.json'
    lock=json.loads(lock_path.read_text(encoding='utf-8')); msys=paths.WorkspacePath(lock['root'])
    if not lock['complete'] or not Path(lock['root']).resolve().is_relative_to(device.ROOT):
        raise ValueError('Workspace toolchain lock required')
    queried=subprocess.run([str(msys/'usr/bin/bash.exe'),'--noprofile','--norc','-c',
        'export PATH=/usr/bin:/ucrt64/bin:/c/Windows/System32; pacman -Q'],capture_output=True,text=True,
        encoding='utf-8',timeout=30,check=True,env=dict(os.environ,MSYSTEM='UCRT64',
            PATH=str(msys/'usr/bin')+';'+os.environ.get('SystemRoot','C:/Windows')+'/System32'))
    if queried.stdout.splitlines()!=lock['package_versions']: raise ValueError('Toolchain package inventory differs')
    with patch.object(reference.upstream,'Path',paths.WorkspacePath):
        binary=compile_native(source,work/'build',msys,jobs)
        reference.verify_devices(work/'build'); runtime=work/'runtime'; runtime.mkdir()
        dlls=reference.upstream.stage_windows(binary,msys,runtime)
    binary=runtime/binary.name; checks=reference.smoke_checks(binary,'z62')
    if ident!=device.identity(): raise ValueError('CaptureWork source changed during build')
    common={'binary':str(binary),'binary_sha256':reference.upstream.digest(binary),
        'capturework_device':ident,'builder_sha256':reference.upstream.digest(Path(__file__)),
        'toolchain_manifest_sha256':reference.upstream.digest(lock_path)}
    for previous in sorted(old_root.glob('*-build-manifest.json')):
        record=json.loads(previous.read_text(encoding='utf-8')); record.update(common)
        record['parent_manifest_sha256']=reference.upstream.digest(previous)
        if 'msys2_dir' in record: record['msys2_dir']=str(msys)
        if 'generated_source_sha256' in record:
            record['capturework_parent_generated_source_sha256']=dict(record['generated_source_sha256'])
            for name in record['generated_source_sha256']:
                key=name if name in hashes else 'hw/arm/'+name
                if key in changed: record['generated_source_sha256'][name]=hashes[key]
        if previous.name=='reference-build-manifest.json':
            record.update(source=str(source),build=str(work/'build'),runtime=str(runtime),
                prepared_source_file_sha256=hashes,runtime_dll_sha256=dlls,
                binary_bytes=binary.stat().st_size,jobs=jobs,checks=checks,
                inherited_from=str(old_root),firmware_run=False)
        with (work/previous.name).open('x',encoding='utf-8') as handle: json.dump(record,handle,indent=2)
    result={**common,'schema':1,'version':device.VERSION,'parent_binary_sha256':prior['binary_sha256'],
        'generated_source_sha256':{name:hashes[name] for name in changed},'checks':checks,
        'firmware_run':False,'camera_accessed':False}
    with (work/'capturework-build-manifest.json').open('x',encoding='utf-8') as handle: json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2),flush=True); return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--jobs',type=int,default=4)
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--resume',action='store_true'); modes.add_argument('--resume-copy',action='store_true')
    modes.add_argument('--refresh-prepared-source',action='store_true')
    args=parser.parse_args()
    if not 1<=args.jobs<=32: parser.error('jobs must be 1..32')
    build(args.jobs,args.resume,args.resume_copy,args.refresh_prepared_source)
