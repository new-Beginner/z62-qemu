"""Compile the bank0 functional numerical tests with the recorded toolchain."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def run(output):
    output.mkdir(parents=True,exist_ok=False)
    r=json.loads((ROOT/'.build/z62-preview-results-format-2026.11.02-r47b/reference-build-manifest.json').read_text())
    tools=Path(r['msys2_dir'])/'ucrt64/bin'
    env={**os.environ,'PATH':str(tools)+os.pathsep+os.environ['PATH']}
    target=output.resolve()/'grid-pixels-test.exe'
    command=[str(tools/'gcc.exe'),'-std=c11','-O2','-Wall','-Wextra','-Werror',
             'tests/native/z62_grid_pixels_test.c','-o',target.relative_to(ROOT).as_posix()]
    build=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,timeout=60)
    (output/'compiler.log').write_bytes(build.stdout+build.stderr)
    if build.returncode:
        raise RuntimeError('Grid C test compile failed: '+build.stderr.decode('utf-8',errors='replace'))
    tested=subprocess.run([str(target)],env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
    result={'schema':1,'completed':tested.returncode==0,'exit_code':tested.returncode,'command':command,
            'test_output':tested.stdout+tested.stderr,'binary_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'firmware_executed':False,'camera_accessed':False,'algorithm_level':'C'}
    (output/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
    return tested.returncode


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    raise SystemExit(run(parser.parse_args().output))
