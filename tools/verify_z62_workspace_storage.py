"""Verify physical workspace storage after the user's explicit relocation request."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
import run_z62_output_lineage as hardware


def digest(path):
    sha=hashlib.sha256()
    with path.open('rb') as handle:
        while data:=handle.read(4*1024*1024):
            sha.update(data)
    return sha.hexdigest()


def require(value,message):
    if not value:
        raise ValueError(message)


if __name__=='__main__':
    destination=ROOT/'analysis/z62-workspace-storage-r73/verified-storage.json'
    if destination.exists():
        raise FileExistsError('Storage receipt is immutable')
    moved={}
    for line in (ROOT/'.runtime/migrated/files.jsonl').read_text(encoding='utf-8').splitlines():
        row=json.loads(line)
        if row['state']=='moved':
            moved[row['source']]=row
    count=0; last=0
    for row in moved.values():
        target=Path(row['target'])
        require(target.resolve().is_relative_to(ROOT),'Relocated file escaped workspace')
        require(not Path(row['source']).exists(),'An old C project source was recreated')
        require(target.stat().st_size==row['bytes'] and digest(target)==row['sha256'],'Relocated C bytes changed')
        count+=1
        if time.monotonic()-last>=15:
            print(json.dumps({'verified_c_files':count,'total':len(moved)}),flush=True); last=time.monotonic()
    remaining=[p for p in Path('<USERPROFILE>/AppData/Local/Temp').iterdir() if p.name.startswith('z62-') and p.is_dir()]
    require(not remaining and not Path('<USERPROFILE>/Documents/Z62-QEMU-runtime').exists(),'C project runtime remains')
    before=json.loads((ROOT/'.runtime/tools-relocation.json').read_text(encoding='utf-8'))
    after=json.loads((ROOT/'.runtime/tools-relocation-verified.json').read_text(encoding='utf-8'))
    require(after['verified'] and before['files']==after['files'] and not Path(before['source']).exists(),
            'Tool relocation comparison differs')
    toolchain=ROOT/'.runtime/tools/z62-toolchain-manifest-r69-3.json'
    locked=json.loads(toolchain.read_text(encoding='utf-8'))
    msys=Path('Q:/.runtime/tools/msys64')
    require(msys.samefile(ROOT/'.runtime/tools/msys64'),'MSYS alias resolves elsewhere')
    queried=subprocess.run([str(msys/'usr/bin/bash.exe'),'--noprofile','--norc','-c',
        'export PATH=/ucrt64/bin:/usr/bin:/c/Windows/System32; pacman -Q'],capture_output=True,
        env=dict(os.environ,MSYSTEM='UCRT64'),timeout=30,check=True)
    versions=queried.stdout.decode('utf-8').splitlines()
    require(versions==locked['package_versions'],'Relocated toolchain versions differ')
    relocated={**locked,'root':str(ROOT/'.runtime/tools/msys64'),'relocated_from_root':locked['root'],
               'parent_manifest_sha256':digest(toolchain),'workspace_storage':True}
    with (ROOT/'.runtime/relocated-toolchain-manifest-r73.json').open('x',encoding='utf-8') as handle:
        json.dump(relocated,handle,indent=2)
    native=json.loads((ROOT/'analysis/z62-workspace-storage-r73/native-host-2/workspace-host-check.json').read_text(encoding='utf-8'))
    require(native['completed'] and native['process_closed'] and native['qmp_still_responds_after_detach'],
            'Workspace native host test failed')
    build=hardware.verify_build()
    require(build['binary_sha256']==native['capture']['owner']['binary_sha256'],'Native binary identity differs')
    commands=list(ROOT.glob('start-*.cmd'))
    require(all('set "TEMP=%CD%\\.runtime\\tmp"' in p.read_text(encoding='utf-8') for p in commands),
            'A startup script still has an implicit system TEMP')
    image=ROOT/'artifacts/z62-workspace-storage-check-r73/DCIM/100Z62EM'
    require(digest(image/'Z62_0001.JPG')=='ed3b252e7775df2a16349d526aee08ab4ecda0d76179614a3f0ab9e4b38c5f68',
            'Workspace JPEG changed')
    require(digest(image/'Z62_0001.NEF')=='c4bf8dfb6c3be7189f0139c8ecb4359788421ed110729cc48f61b0d3af6db6c6',
            'Workspace NEF changed')
    result={'schema':1,'verified':True,'scope':'project storage relocation, not whole camera validation',
        'workspace':str(ROOT),'ascii_alias':'Q:/','alias_same_physical_workspace':Path('Q:/').samefile(ROOT),
        'moved_c_files':len(moved),'moved_c_bytes':sum(r['bytes'] for r in moved.values()),
        'moved_tools_files':len(after['files']),'moved_tools_bytes':sum(r['bytes'] for r in after['files'].values()),
        'c_project_roots_remaining':0,'startup_scripts_with_workspace_temp':len(commands),
        'toolchain_packages':len(versions),'native_host_and_qmp_verified':True,'workspace_photo_files_verified':True,
        'qemu_sha256':build['binary_sha256'],'camera_accessed':False}
    with destination.open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    print(json.dumps(result,ensure_ascii=False),flush=True)
