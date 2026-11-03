"""Add the explicit QEMU FDT dependency and write a new immutable toolchain lock."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import setup_qemu_toolchain as setup


def extend():
    root=setup.MANAGED/'msys64'
    previous=setup.MANAGED/'z62-toolchain-manifest.json'
    target=setup.MANAGED/'z62-toolchain-manifest-r69-2.json'
    old=json.loads(previous.read_text(encoding='utf-8'))
    if old['complete'] is not True or Path(old['root']).resolve()!=root.resolve():
        raise ValueError('Previous toolchain identity differs')
    env=dict(os.environ,MSYSTEM='UCRT64',CHERE_INVOKING='1',LANG='C.UTF-8',LC_ALL='C.UTF-8',
        PATH=str(root/'usr/bin')+';'+os.environ.get('SystemRoot','C:/Windows')+'/System32')
    def run(script,capture=False):
        args=[str(root/'usr/bin/bash.exe'),'--noprofile','--norc','-c',
              'export PATH=/ucrt64/bin:/usr/bin:/c/Windows/System32; '+script]
        child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.STDOUT,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        journal=setup.MANAGED/'extension-active-process.json'
        journal.write_text(json.dumps({'pid':child.pid,'owner_pid':os.getpid(),'command':args},indent=2),encoding='utf-8')
        data=child.communicate()[0]
        journal.write_text(json.dumps({'pid':child.pid,'terminal':True,'returncode':child.returncode},indent=2),encoding='utf-8')
        if child.returncode:
            raise subprocess.CalledProcessError(child.returncode,args,output=data)
        return data.decode('utf-8') if data is not None else ''
    current=run('pacman -Q',True).splitlines()
    if target.exists():
        saved=json.loads(target.read_text(encoding='utf-8'))
        if current!=saved['package_versions']:
            raise ValueError('Locked extended toolchain has changed')
        return saved
    if current!=old['package_versions']:
        raise ValueError('Unrecorded package changes; inspect before extending')
    config=(root/'etc/pacman.conf').read_text(encoding='utf-8')
    policies=[l.strip() for l in config.splitlines() if l.strip().startswith('SigLevel')]
    if policies!=['SigLevel    = Required'] or 'GPGDir = /etc/pacman.d/gnupg-vendor' not in config:
        raise ValueError('Private package signature policy differs')
    run('pacman -S --needed --noconfirm mingw-w64-ucrt-x86_64-dtc')
    if not (root/'ucrt64/include/libfdt.h').is_file() or not any((root/'ucrt64/lib').glob('libfdt.*')):
        raise ValueError('DTC installation did not provide FDT headers/library')
    record={**old,'parent_manifest_sha256':setup.digest(previous),'extension_source_sha256':setup.digest(__file__),
        'added_package':'mingw-w64-ucrt-x86_64-dtc','package_versions':run('pacman -Q',True).splitlines(),
        'package_archive_sha256':{p.name:setup.digest(p) for p in (root/'var/cache/pacman/pkg').glob('*.pkg.tar.*')
            if p.is_file() and not p.name.endswith('.sig')}}
    with target.open('x',encoding='utf-8') as handle:
        json.dump(record,handle,indent=2)
    return record


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    result=extend()
    print(json.dumps({'complete':True,'root':result['root'],'packages':len(result['package_versions']),
                      'added':result['added_package']},indent=2),flush=True)
