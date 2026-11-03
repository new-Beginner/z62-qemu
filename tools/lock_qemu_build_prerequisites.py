"""Complete standard MSYS build prerequisites and preserve each dependency lock."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import setup_qemu_toolchain as setup


def complete():
    root=setup.MANAGED/'msys64'
    previous=setup.MANAGED/'z62-toolchain-manifest-r69-2.json'
    target=setup.MANAGED/'z62-toolchain-manifest-r69-3.json'
    old=json.loads(previous.read_text(encoding='utf-8'))
    if old['complete'] is not True or Path(old['root']).resolve()!=root.resolve():
        raise ValueError('Previous toolchain identity differs')
    env=dict(os.environ,MSYSTEM='UCRT64',CHERE_INVOKING='1',LANG='C.UTF-8',LC_ALL='C.UTF-8',
        PATH=str(root/'usr/bin')+';'+os.environ.get('SystemRoot','C:/Windows')+'/System32')
    def run(script,capture=False):
        command=[str(root/'usr/bin/bash.exe'),'--noprofile','--norc','-c',
                 'export PATH=/ucrt64/bin:/usr/bin:/c/Windows/System32; '+script]
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.STDOUT,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        journal=setup.MANAGED/'prerequisites-active-process.json'
        journal.write_text(json.dumps({'pid':process.pid,'owner_pid':os.getpid(),'command':command},indent=2),encoding='utf-8')
        output=process.communicate()[0]
        journal.write_text(json.dumps({'pid':process.pid,'terminal':True,'returncode':process.returncode},indent=2),encoding='utf-8')
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode,command,output=output)
        return output.decode('utf-8') if output is not None else ''
    versions=run('pacman -Q',True).splitlines()
    if target.exists():
        saved=json.loads(target.read_text(encoding='utf-8'))
        if saved['package_versions']!=versions:
            raise ValueError('Completed prerequisite lock differs')
        return saved
    if versions!=old['package_versions']:
        raise ValueError('Unexpected dependency changes before extension')
    config=(root/'etc/pacman.conf').read_text(encoding='utf-8')
    active=[line.strip() for line in config.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if 'SigLevel    = Required' not in active or any('TrustAll' in line or 'SigLevel' in line and 'Never' in line for line in active):
        raise ValueError('Required signature policy differs')
    run('pacman -S --needed --noconfirm base-devel')
    run('command -v diff && command -v make && command -v gcc && command -v ninja',True)
    record={**old,'parent_manifest_sha256':setup.digest(previous),'prerequisite_source_sha256':setup.digest(__file__),
        'added_group':'base-devel','package_versions':run('pacman -Q',True).splitlines(),
        'package_archive_sha256':{p.name:setup.digest(p) for p in (root/'var/cache/pacman/pkg').glob('*.pkg.tar.*')
            if p.is_file() and not p.name.endswith('.sig')}}
    with target.open('x',encoding='utf-8') as handle:
        json.dump(record,handle,indent=2)
    return record


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    result=complete()
    print(json.dumps({'complete':True,'root':result['root'],'packages':len(result['package_versions']),
                      'added':result['added_group']},indent=2),flush=True)
