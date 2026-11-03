"""Task-local, pinned-base MSYS2 restoration without a global installer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANAGED = ROOT.parent/'z62-qemu-tools'
URL = 'https://repo.msys2.org/distrib/x86_64/msys2-base-x86_64-20260927.tar.xz'
ARCHIVE = ROOT/'.build/downloads/msys2-base-x86_64-20260927.tar.xz'
EXPECTED = 'ea2f31a0b6ade63914ce441ffb022f0f6aa96982bfefa2326460a26d5fb01322'
PACKAGES = ('mingw-w64-ucrt-x86_64-gcc', 'mingw-w64-ucrt-x86_64-python',
    'mingw-w64-ucrt-x86_64-ninja', 'mingw-w64-ucrt-x86_64-pkgconf',
    'mingw-w64-ucrt-x86_64-glib2', 'mingw-w64-ucrt-x86_64-pixman',
    'mingw-w64-ucrt-x86_64-zlib', 'mingw-w64-ucrt-x86_64-zstd',
    'mingw-w64-ucrt-x86_64-python-pip')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def setup(public_keyring=False):
    if os.name != 'nt' or not str(MANAGED).isascii():
        raise ValueError('This managed UCRT64 root requires Windows and an ASCII parent')
    root = MANAGED/'msys64'; owner = MANAGED/'z62-toolchain-owner.json'
    if MANAGED.is_symlink() or root.is_symlink():
        raise ValueError('Refusing a linked managed toolchain root')
    if MANAGED.exists() and not owner.is_file():
        raise ValueError('Existing directory has no task ownership marker')
    if not MANAGED.exists():
        MANAGED.mkdir()
        with owner.open('x', encoding='utf-8') as handle:
            json.dump({'schema': 1, 'workspace': str(ROOT), 'base_url': URL, 'base_sha256': EXPECTED,
                       'extracted': False, 'remote_base_verified': False}, handle, indent=2)
    record = json.loads(owner.read_text(encoding='utf-8'))
    if (record['workspace'] != str(ROOT) or record['base_sha256'] != EXPECTED or record['base_url'] != URL):
        raise ValueError('Toolchain owner differs')
    def save():
        owner.write_text(json.dumps(record, indent=2), encoding='utf-8')
    if digest(ARCHIVE) != EXPECTED:
        raise ValueError('Cached MSYS2 base checksum differs')
    if not record['remote_base_verified']:
        print('Checking cached base against complete official HTTPS archive', flush=True)
        remote = hashlib.sha256(); total = 0
        with urllib.request.urlopen(URL, timeout=30) as response:
            while data := response.read(1024*1024):
                remote.update(data); total += len(data)
        if remote.hexdigest() != EXPECTED or total != ARCHIVE.stat().st_size:
            raise ValueError('Official archive differs from the pinned cached base')
        record.update(remote_base_verified=True, base_bytes=total); save()
    if not record['extracted']:
        print('Extracting verified base into '+str(root), flush=True)
        with tarfile.open(ARCHIVE) as archive:
            members = archive.getmembers()
            for member in members:
                parts = Path(member.name).parts
                if (not parts or parts[0] != 'msys64' or member.name.startswith('/') or
                    '..' in parts or member.issym() or member.islnk() or
                    not (member.isfile() or member.isdir())):
                    raise ValueError('Unsafe or unsupported archive member: '+member.name)
            archive.extractall(MANAGED, members=members, filter='data')
        record['extracted'] = True; save()
    bash = root/'usr/bin/bash.exe'
    env = dict(os.environ, MSYSTEM='UCRT64', CHERE_INVOKING='1', LANG='C.UTF-8', LC_ALL='C.UTF-8',
               PATH=str(root/'usr/bin')+';'+os.environ.get('SystemRoot', 'C:/Windows')+'/System32')
    active = MANAGED/'active-process.json'
    def run(script, *, capture=False, input_bytes=None):
        command = [str(bash), '--noprofile', '--norc', '-c',
                   'export PATH=/usr/bin:/ucrt64/bin:/c/Windows/System32; '+script]
        child = subprocess.Popen(command, env=env, stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture else None, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        active.write_text(json.dumps({'pid': child.pid, 'owner_pid': os.getpid(),
            'command': command, 'binary_sha256': digest(bash), 'started_at': time.time()}, indent=2), encoding='utf-8')
        output = child.communicate(input=input_bytes)[0]
        active.write_text(json.dumps({'pid': child.pid, 'returncode': child.returncode, 'terminal': True}, indent=2), encoding='utf-8')
        if child.returncode:
            raise subprocess.CalledProcessError(child.returncode, command, output=output)
        return output.decode('utf-8') if output is not None else ''
    public_dir='/etc/pacman.d/gnupg-vendor'
    def refresh_public_roots():
        directory=root/public_dir.lstrip('/')
        if directory.is_symlink():
            raise ValueError('Refusing linked public keyring')
        directory.mkdir(exist_ok=True)
        (directory/'gpg.conf').write_text('no-autostart\nno-auto-key-retrieve\nno-tty\nlock-never\n',encoding='ascii')
        anchors=[]
        trusted=root/'usr/share/pacman/keyrings/msys2-trusted'
        for line in trusted.read_text(encoding='ascii').splitlines():
            if not line or line.startswith('#'):
                continue
            if not re.fullmatch(r'[A-Fa-f0-9]{40}:4:',line):
                raise ValueError('Unexpected vendor trust-anchor format')
            anchors.append(line.split(':')[0].upper()+':6:')
        if not anchors:
            raise ValueError('No authenticated vendor master keys')
        (directory/'vendor-ownertrust.txt').write_text('\n'.join(anchors)+'\n',encoding='ascii')
        run('gpg --batch --no-autostart --homedir '+public_dir+
            ' --import /usr/share/pacman/keyrings/msys2.gpg')
        run('gpg --batch --no-autostart --homedir '+public_dir+' --import-ownertrust '+public_dir+'/vendor-ownertrust.txt')
        revoked=[]
        for line in (root/'usr/share/pacman/keyrings/msys2-revoked').read_text(encoding='ascii').splitlines():
            if not line or line.startswith('#'):
                continue
            if not re.fullmatch(r'[A-Fa-f0-9]{40}',line):
                raise ValueError('Unexpected vendor revoked fingerprint')
            run('gpg --batch --yes --no-autostart --homedir '+public_dir+' --command-fd 0 --edit-key '+line,
                input_bytes=b'disable\nquit\n')
            revoked.append(line.upper())
        run('gpg --batch --yes --no-autostart --homedir '+public_dir+' --output '+public_dir+'/pubring.gpg --export')
        config=root/'etc/pacman.conf'
        lines=config.read_text(encoding='utf-8').splitlines()
        active_lines=[line.strip() for line in lines if line.strip() and not line.lstrip().startswith('#')]
        policies=[line for line in active_lines if line.startswith('SigLevel')]
        if (not policies or not any('Required' in line for line in policies) or
            any('Never' in line or 'TrustAll' in line for line in policies)):
            raise ValueError('Refusing a weakened package-signature policy')
        indices=[i for i,line in enumerate(lines) if line.lstrip().startswith(('GPGDir','#GPGDir'))]
        if len(indices)!=1:
            raise ValueError('Unexpected private pacman GPGDir configuration')
        lines[indices[0]]='GPGDir = '+public_dir
        config.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        record.update(keys_initialized=True,keyring_mode='authenticated-vendor-public-roots',
                      vendor_master_fingerprints=[a.split(':')[0] for a in anchors],
                      vendor_revoked_fingerprints=revoked,signature_policy=policies)
        save()
    if public_keyring:
        print('Importing authenticated vendor master roots without a private signing agent',flush=True)
        refresh_public_roots()
    elif record.get('keyring_mode')=='authenticated-vendor-public-roots':
        raise ValueError('Resume this toolchain with --public-keyring')
    elif not record.get('keys_initialized'):
        print('Initializing private MSYS2 signing keyring', flush=True)
        run('pacman-key --init && pacman-key --populate msys2')
        record['keys_initialized'] = True; save()
    if not record.get('core_updated'):
        print('Updating private MSYS2 core packages', flush=True)
        run('pacman -Syu --noconfirm')
        record['core_updated'] = True; save()
        if public_keyring:
            refresh_public_roots()
    if not record.get('dependencies_installed'):
        print('Installing UCRT64 build dependencies in the private root', flush=True)
        run('pacman -S --needed --noconfirm '+' '.join(PACKAGES))
        record['dependencies_installed'] = True; save()
        if public_keyring:
            refresh_public_roots()
    versions = run('pacman -Q', capture=True)
    compiler = run('/ucrt64/bin/gcc --version', capture=True)
    required = ('gcc.exe', 'python.exe', 'ninja.exe', 'pkgconf.exe', 'objdump.exe', 'windres.exe')
    if not all((root/'ucrt64/bin'/name).is_file() for name in required):
        raise ValueError('Installed UCRT64 toolchain is incomplete')
    packages = {p.name: digest(p) for p in (root/'var/cache/pacman/pkg').glob('*.pkg.tar.*')
                if p.is_file() and not p.name.endswith('.sig')}
    manifest = {'schema': 1, 'complete': True, 'root': str(root), 'base_url': URL,
        'base_sha256': EXPECTED, 'package_versions': versions.splitlines(), 'compiler': compiler,
        'package_archive_sha256': packages, 'setup_source_sha256': digest(__file__),
        'keyring_mode':record.get('keyring_mode','local-signing-key'),
        'signature_policy':record.get('signature_policy'),
        'global_environment_changed': False, 'camera_accessed': False}
    target = MANAGED/'z62-toolchain-manifest.json'
    if target.exists():
        previous = json.loads(target.read_text(encoding='utf-8'))
        if previous != manifest:
            raise ValueError('Existing toolchain lock differs; preserve and inspect it')
    else:
        with target.open('x', encoding='utf-8') as handle:
            json.dump(manifest, handle, indent=2)
    return manifest


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--public-keyring',action='store_true')
    args=parser.parse_args()
    result = setup(args.public_keyring)
    print(json.dumps({'complete': True, 'root': result['root'], 'compiler': result['compiler'],
                      'packages': len(result['package_versions'])}, indent=2), flush=True)
