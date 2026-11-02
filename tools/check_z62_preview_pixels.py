"""Compile and run the portable C pixel tests with the recorded native toolchain."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def run(output):
    output.mkdir(parents=True,exist_ok=False)
    record=json.loads((ROOT/'.build/z62-finite-stats-2026.10.29-r8/reference-build-manifest.json').read_text())
    binary=Path(record['msys2_dir'])/'ucrt64/bin'
    env={**os.environ,'PATH':str(binary)+os.pathsep+os.environ['PATH']}
    flags=subprocess.check_output([str(binary/'pkg-config.exe'),'--cflags','--libs','glib-2.0'],env=env,text=True)
    compiler=binary/'gcc.exe'
    source=ROOT/'tests/native/z62_preview_pixels_test.c'
    target=output.resolve()/'pixels-test.exe'
    command=[str(compiler),'-std=c11','-O2','-Wall','-Wextra','-Werror',
             source.relative_to(ROOT).as_posix(),'-o',target.relative_to(ROOT).as_posix(),*shlex.split(flags),'-lm']
    built=subprocess.run(command,cwd=ROOT,env=env,capture_output=True)
    (output/'compiler.log').write_bytes(built.stdout+built.stderr)
    if built.returncode:
        raise RuntimeError('Native compiler failed: '+(built.stdout+built.stderr).decode('utf-8',errors='replace'))
    tested=subprocess.run([str(target)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',check=True)
    result={'completed':True,'command':command,'compiler_output':(built.stdout+built.stderr).decode('utf-8',errors='replace'),
        'test_output':tested.stdout+tested.stderr,'camera_accessed':False,'firmware_executed':False,
        'binary_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    (output/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(tested.stdout)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run(args.output)
