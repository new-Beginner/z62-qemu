"""Compile and exercise the explicit software RAW view using the pinned GCC."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT/'qemu/z62-video-source/nikon-z62-video-source-pixels.h'
TEST = ROOT/'tests/native/z62_video_source_pixels_test.c'


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    record = json.loads((ROOT/'.build/z62-grid-2026.11.02-r48/reference-build-manifest.json').read_text())
    compiler = Path(record['msys2_dir'])/'ucrt64/bin'
    env = {**os.environ, 'PATH': str(compiler)+os.pathsep+os.environ['PATH']}
    target = output.resolve()/'video-source-test.exe'
    sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (HEADER, TEST)}
    command = [str(compiler/'gcc.exe'), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
               TEST.relative_to(ROOT).as_posix(), '-o', target.relative_to(ROOT).as_posix()]
    built = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=60)
    (output/'compiler.log').write_bytes(built.stdout+built.stderr)
    result = {'schema': 1, 'version': '2026.11.03-video-source-pixels-r58',
              'source_sha256': sources, 'command': command, 'compile_exit_code': built.returncode,
              'completed': False, 'algorithm_level': 'C', 'qemu_executed': False,
              'completion_irq_injected': False, 'physical_roi_verified': False,
              'video_pipeline_verified': False, 'camera_accessed': False}
    if built.returncode == 0:
        tested = subprocess.run([str(target)], cwd=ROOT, env=env, capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=60)
        result.update(test_exit_code=tested.returncode, output=tested.stdout+tested.stderr,
                      completed=tested.returncode == 0,
                      binary_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    result['sources_unchanged_during_test'] = all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest
                                                for name, digest in sources.items())
    result['completed'] &= result['sources_unchanged_during_test']
    with (output/'report.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output)['completed'] else 1)
