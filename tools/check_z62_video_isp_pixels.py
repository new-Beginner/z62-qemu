"""Strict native C numerical/recipe verification before video device wiring."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
FILES=('qemu/z62-video-isp/nikon-z62-video-pixels.h','qemu/z62-video-isp/nikon-z62-video-profile.h',
       'qemu/z62-video-source/nikon-z62-video-source-pixels.h',
       'qemu/z62-preview-results/nikon-z62-preview-results-profile.h','tests/native/z62_video_isp_pixels_test.c')


def run(output):
    output.mkdir(parents=True,exist_ok=False)
    old=json.loads((ROOT/'.build/z62-grid-2026.11.02-r48/reference-build-manifest.json').read_text())
    compiler=Path(old['msys2_dir'])/'ucrt64/bin'
    env={**os.environ,'PATH':str(compiler)+os.pathsep+os.environ['PATH']}
    sources={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in FILES}
    target=output.resolve()/'video-isp-test.exe'
    command=[str(compiler/'gcc.exe'),'-std=c11','-O2','-Wall','-Wextra','-Werror',
             '-I','qemu/z62-video-source','-I','qemu/z62-preview-results',FILES[-1],'-lm',
             '-o',str(target.relative_to(ROOT))]
    built=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,timeout=60)
    (output/'compiler.log').write_bytes(built.stdout+built.stderr)
    record={'schema':1,'source_sha256':sources,'command':command,'compile_exit_code':built.returncode,
            'completed':False,'algorithm_level':'C','qemu_executed':False,'camera_accessed':False,
            'physical_work_format_verified':False,'original_isp_equivalent':False}
    if built.returncode==0:
        tested=subprocess.run([str(target)],cwd=ROOT,env=env,capture_output=True,text=True,
                              encoding='utf-8',errors='replace',timeout=60)
        record.update(test_exit_code=tested.returncode,completed=tested.returncode==0,
                      output=tested.stdout+tested.stderr,binary_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    record['sources_unchanged_during_test']=all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in sources.items())
    record['completed'] &= record['sources_unchanged_during_test']
    with (output/'report.json').open('x',encoding='utf-8') as handle: json.dump(record,handle,indent=2)
    print(json.dumps(record),flush=True)
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();raise SystemExit(0 if run(a.output)['completed'] else 1)
