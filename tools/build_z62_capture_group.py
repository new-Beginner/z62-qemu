"""Build r93 independently from frozen r92, using the verified native route."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from unittest.mock import patch
import build_reference_qemu as reference
from build_z62_raw_stream import copy_verified_source
from build_z62_capturework import compile_native
import run_z62_capturework_statistics as parent
import z62_capture_group_device as device
import z62_workspace_paths as paths


def build(jobs,resume=False,refresh=False):
    prior=parent.verify_build(); old_root=parent.DEFAULT_QEMU.parent.parent
    old=json.loads((old_root/'reference-build-manifest.json').read_text(encoding='utf-8'))
    work=device.WORK.resolve() if resume or refresh else reference.guard_workspace(device.WORK,'z62',updates=True)
    if work!=device.WORK.resolve() or not work.is_relative_to(device.ROOT/'.build'):
        raise ValueError('Use independent group workspace')
    if (work/'runtime').exists() or (work/'capture-group-build-manifest.json').exists():
        raise ValueError('Completed group output is immutable')
    if shutil.disk_usage(work.parent).free<12*1024**3: raise ValueError('Need 12 GiB for group build')
    physical=Path(work);work=paths.WorkspacePath(work);source=work/'source/qemu-10.2.4';ident=device.identity()
    prepared_path=work/'prepared-capture-group.json'
    if resume or refresh:
        prepared=json.loads(prepared_path.read_text(encoding='utf-8'))
        if not refresh and prepared['group_device']!=ident: raise ValueError('Prepared group source changed')
        hashes=prepared['source_hashes'];changed=prepared['changed']
        for name,expected in hashes.items():
            if reference.upstream.digest(Path(str(source))/name)!=expected: raise ValueError('Prepared source changed: '+name)
        if refresh:
            archive=work/'prepared-attempts'/str(len(list((work/'prepared-attempts').glob('*')))+1)
            archive.mkdir(parents=True,exist_ok=False)
            with (archive/prepared_path.name).open('xb') as handle:handle.write(prepared_path.read_bytes())
            for name in changed:
                target=archive/name;target.parent.mkdir(parents=True,exist_ok=True)
                with target.open('xb') as handle:handle.write((source/name).read_bytes())
            rendered=device.render({name:(Path(old['source'])/name).read_bytes() for name in device.INPUTS})
            hashes=dict(old['prepared_source_file_sha256']);changed=list(rendered)
            for name,data in rendered.items():
                (source/name).write_bytes(data);hashes[name]=hashlib.sha256(data).hexdigest()
            prepared_path.write_text(json.dumps({'group_device':ident,'source_hashes':hashes,
                'changed':changed,'complete_build':False,'previous_preparation_preserved':str(archive)},indent=2),encoding='utf-8')
    else:
        work.mkdir(parents=True,exist_ok=False)
        (work/reference.MARKER).write_text(json.dumps(reference.identity('z62',True)),encoding='utf-8')
        print('Copying verified r92 into independent r93 group tree',flush=True)
        copy_verified_source(Path(old['source']),physical/'source/qemu-10.2.4',old['prepared_source_file_sha256'])
        rendered=device.render({name:(Path(old['source'])/name).read_bytes() for name in device.INPUTS})
        hashes=dict(old['prepared_source_file_sha256']);changed=list(rendered)
        for name,data in rendered.items():
            (source/name).write_bytes(data);hashes[name]=hashlib.sha256(data).hexdigest()
        prepared_path.write_text(json.dumps({'group_device':ident,'source_hashes':hashes,
            'changed':changed,'complete_build':False},indent=2),encoding='utf-8')
    lock_path=device.ROOT/'.runtime/relocated-toolchain-manifest-r73.json'
    lock=json.loads(lock_path.read_text(encoding='utf-8'));msys=paths.WorkspacePath(lock['root'])
    if not lock['complete'] or not Path(lock['root']).resolve().is_relative_to(device.ROOT):
        raise ValueError('Workspace locked compiler required')
    with patch.object(reference.upstream,'Path',paths.WorkspacePath):
        binary=compile_native(source,work/'build',msys,jobs)
        reference.verify_devices(work/'build');runtime=work/'runtime';runtime.mkdir()
        dlls=reference.upstream.stage_windows(binary,msys,runtime)
    binary=runtime/binary.name;checks=reference.smoke_checks(binary,'z62')
    if ident!=device.identity(): raise ValueError('Group adapter changed during build')
    common={'binary':str(binary),'binary_sha256':reference.upstream.digest(binary),
        'capture_group_device':ident,'builder_sha256':reference.upstream.digest(Path(__file__)),
        'toolchain_manifest_sha256':reference.upstream.digest(lock_path)}
    for previous in sorted(old_root.glob('*-build-manifest.json')):
        record=json.loads(previous.read_text(encoding='utf-8'));record.update(common)
        record['group_parent_manifest_sha256']=reference.upstream.digest(previous)
        if 'msys2_dir' in record:record['msys2_dir']=str(msys)
        if 'generated_source_sha256' in record:
            record['group_parent_generated_source_sha256']=dict(record['generated_source_sha256'])
            for name in record['generated_source_sha256']:
                key=name if name in hashes else 'hw/arm/'+name
                if key in changed:record['generated_source_sha256'][name]=hashes[key]
        if previous.name=='reference-build-manifest.json':
            record.update(source=str(source),build=str(work/'build'),runtime=str(runtime),
                prepared_source_file_sha256=hashes,runtime_dll_sha256=dlls,
                binary_bytes=binary.stat().st_size,jobs=jobs,checks=checks,
                inherited_from=str(old_root),firmware_run=False)
        with (work/previous.name).open('x',encoding='utf-8') as handle:json.dump(record,handle,indent=2)
    result={**common,'schema':1,'version':device.VERSION,'parent_binary_sha256':prior['binary_sha256'],
        'generated_source_sha256':{name:hashes[name] for name in changed},'checks':checks,
        'firmware_run':False,'camera_accessed':False}
    with (work/'capture-group-build-manifest.json').open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2)
    print(json.dumps({'version':device.VERSION,'binary_sha256':common['binary_sha256'],'built':True}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--jobs',type=int,default=4)
    parser.add_argument('--resume',action='store_true');parser.add_argument('--refresh',action='store_true');args=parser.parse_args()
    if not 1<=args.jobs<=32:parser.error('jobs must be 1..32')
    build(args.jobs,args.resume,args.refresh)
