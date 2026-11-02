"""Compile format-transition behavior against an explicit C profile header."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(output, headers):
    output.mkdir(parents=True, exist_ok=False)
    m = json.loads((ROOT/'.build/z62-scene-file-2026.11.01-r24/reference-build-manifest.json').read_text())
    binary = Path(m['msys2_dir'])/'ucrt64/bin'
    env = {**os.environ, 'PATH': str(binary)+os.pathsep+os.environ['PATH']}
    target = output.resolve()/'format-test.exe'
    command = [str(binary/'gcc.exe'), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
               '-I', headers.resolve().relative_to(ROOT).as_posix(),
               'tests/native/z62_preview_results_format_test.c', '-o', target.relative_to(ROOT).as_posix()]
    built = subprocess.run(command, cwd=ROOT, env=env, capture_output=True)
    (output/'compiler.log').write_bytes(built.stdout+built.stderr)
    if built.returncode:
        raise RuntimeError('Format test compile failed: '+built.stderr.decode('utf-8', errors='replace'))
    tested = subprocess.run([str(target)], env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    result = {'schema': 1, 'completed': tested.returncode == 0, 'exit_code': tested.returncode,
              'command': command, 'profile_header_sha256': hashlib.sha256((headers/'nikon-z62-preview-results-profile.h').read_bytes()).hexdigest(),
              'test_output': tested.stdout+tested.stderr, 'firmware_executed': False, 'camera_accessed': False}
    (output/'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)
    return tested.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--headers', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.output, args.headers))
