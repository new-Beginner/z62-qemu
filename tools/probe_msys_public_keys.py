"""Verify official MSYS2 signatures using only its authenticated public keyring."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request
import setup_qemu_toolchain as setup


def check(output):
    root=setup.MANAGED/'msys64'; owner=json.loads((setup.MANAGED/'z62-toolchain-owner.json').read_text())
    if owner['workspace']!=str(setup.ROOT) or not owner.get('remote_base_verified'):
        raise ValueError('Toolchain base has not been authenticated')
    keyring=root/'usr/share/pacman/keyrings/msys2.gpg'
    signature=output/'base.sig'
    with urllib.request.urlopen(setup.URL+'.sig',timeout=20) as response:
        data=response.read(65537)
    if not 0<len(data)<=65536:
        raise ValueError('Unexpected release signature size')
    with signature.open('xb') as handle:
        handle.write(data)
    env=dict(os.environ,MSYSTEM='UCRT64',LANG='C.UTF-8',LC_ALL='C.UTF-8',
        PATH=str(root/'usr/bin')+';'+os.environ.get('SystemRoot','C:/Windows')+'/System32')
    def execute(name,args,log):
        command=[str(root/'usr/bin'/name),*args]
        result=subprocess.run(command,stdin=subprocess.DEVNULL,capture_output=True,env=env,timeout=30,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        with (output/log).open('xb') as handle:
            handle.write(result.stdout+result.stderr)
        return result.returncode
    directory='/etc/pacman.d/gnupg-'+output.name
    public=root/directory.lstrip('/'); public.mkdir(exist_ok=False)
    record={'schema':1,'completed':False,'probe_sha256':setup.digest(__file__),
        'release_signature_url':setup.URL+'.sig','signature_sha256':setup.digest(signature),
        'vendor_keyring_sha256':setup.digest(keyring),'signature_checks_disabled':False,'camera_accessed':False}
    primary='0EBF782C5D53F7E5FB02A66746BD761F7A49B0EC'
    signing='E0AA0F031DBD80FFBA57B06D5A62D0CAB6264964'
    docs_url='https://www.msys2.org/docs/installer/'
    docs=urllib.request.urlopen(docs_url,timeout=20).read(300000).decode()
    normalized=re.sub(r'\s+','',re.sub(r'<[^>]+>','',docs))
    if primary not in normalized or signing not in normalized:
        raise ValueError('Official installer signing fingerprints differ')
    key_url='https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x'+primary
    release=output/'release-public.asc'
    with urllib.request.urlopen(key_url,timeout=20) as response:
        key=response.read(1024*1024)
    with release.open('xb') as stream:
        stream.write(key)
    record.update(release_key_url=key_url,release_fingerprint_source=docs_url,
                  release_primary_fingerprint=primary,release_signing_subkey=signing)
    record['public_import_returncode']=execute('gpg.exe',['--batch','--no-autostart',
        '--homedir',directory,'--import',str(keyring)],'import.log')
    record['release_import_returncode']=execute('gpg.exe',['--batch','--no-autostart',
        '--homedir',directory,'--import',str(release)],'release-import.log')
    record['public_export_returncode']=execute('gpg.exe',['--batch','--no-autostart',
        '--homedir',directory,'--output',directory+'/vendor-binary.gpg','--export'],'export.log')
    record['verify_returncode']=execute('gpgv.exe',['--status-fd','1','--keyring',directory+'/vendor-binary.gpg',
        str(signature),str(setup.ARCHIVE)],'verify.log')
    status=(output/'verify.log').read_text(encoding='utf-8',errors='replace')
    valid=[line.split() for line in status.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
    record['expected_fingerprints_verified']=any(line[2]==signing and line[-1]==primary for line in valid)
    record['completed']=(record['verify_returncode']==record['public_import_returncode']==
                         record['public_export_returncode']==record['release_import_returncode']==0 and
                         record['expected_fingerprints_verified'])
    record['logs_sha256']={p.name:setup.digest(p) for p in output.glob('*.log')}
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    try:
        result=check(args.output)
    except Exception as exc:
        result={'schema':1,'completed':False,'failure':{'type':type(exc).__name__,'message':str(exc)}}
    with (args.output/'probe.json').open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2),flush=True)
    raise SystemExit(0 if result['completed'] else 1)
