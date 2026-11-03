"""Compare foreground task-owned GPG IPC without changing signature policy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time
import setup_qemu_toolchain as setup


def check(output):
    root=setup.MANAGED/'msys64'
    owner=json.loads((setup.MANAGED/'z62-toolchain-owner.json').read_text())
    if owner['workspace']!=str(setup.ROOT) or owner.get('remote_base_verified') is not True:
        raise ValueError('Toolchain ownership or base provenance differs')
    with tarfile.open(setup.ARCHIVE) as archive:
        for name in ('gpg-agent.exe','gpg.exe'):
            raw=archive.extractfile('msys64/usr/bin/'+name).read()
            if hashlib.sha256(raw).hexdigest()!=setup.digest(root/'usr/bin'/name):
                raise ValueError('Agent executable differs from verified base')
    keyring=root/'etc/pacman.d/gnupg-fg-probe'
    keyring.mkdir(exist_ok=False)
    for name in ('pubring.gpg','secring.gpg'):
        with (keyring/name).open('xb'):
            pass
    for name in ('gpg.conf','gpg-agent.conf'):
        (keyring/name).write_bytes((root/'etc/pacman.d/gnupg'/name).read_bytes())
    env=dict(os.environ,MSYSTEM='UCRT64',LANG='C.UTF-8',LC_ALL='C.UTF-8',
        PATH=str(root/'usr/bin')+';'+os.environ.get('SystemRoot','C:/Windows')+'/System32')
    directory='/etc/pacman.d/gnupg-fg-probe'
    command=[str(root/'usr/bin/gpg-agent.exe'),'--homedir',directory,'--daemon','--no-detach']
    record={'schema':1,'completed':False,'agent_command':command,'signature_checks_disabled':False,
            'camera_accessed':False,'probe_sha256':setup.digest(__file__)}
    with (output/'agent.log').open('xb') as log:
        agent=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
            env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        record['agent_pid']=agent.pid
        try:
            deadline=time.monotonic()+10
            while not (keyring/'S.gpg-agent').exists() and time.monotonic()<deadline and agent.poll() is None:
                time.sleep(.1)
            client=[str(root/'usr/bin/gpg.exe'),'--homedir',directory,'--no-autostart','-K','--with-colons']
            result=subprocess.run(client,stdin=subprocess.DEVNULL,capture_output=True,env=env,timeout=15,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            with (output/'client.log').open('xb') as stream:
                stream.write(result.stdout+result.stderr)
            record.update(client_returncode=result.returncode,agent_alive=agent.poll() is None,
                          completed=result.returncode==0 and agent.poll() is None)
        except Exception as exc:
            record['failure']={'type':type(exc).__name__,'message':str(exc)}
        finally:
            if agent.poll() is None:
                agent.terminate()
            record['agent_returncode']=agent.wait(timeout=10)
            record['agent_closed']=agent.poll() is not None
    record['logs_sha256']={p.name:setup.digest(p) for p in output.glob('*.log')}
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    result=check(args.output)
    with (args.output/'probe.json').open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2),flush=True)
    raise SystemExit(0 if result['completed'] else 1)
