"""Compile the real C result profile tests with the recorded MSYS2 compiler."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    parent = ROOT/'.build/z62-scene-file-2026.11.01-r24/reference-build-manifest.json'
    record = json.loads(parent.read_text(encoding='utf-8'))
    binary = Path(record['msys2_dir'])/'ucrt64/bin'
    env = {**os.environ, 'PATH': str(binary)+os.pathsep+os.environ['PATH']}
    source = ROOT/'tests/native/z62_preview_results_profile_test.c'
    target = output.resolve()/'results-profile-test.exe'
    command = [str(binary/'gcc.exe'), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
               source.relative_to(ROOT).as_posix(), '-o', target.relative_to(ROOT).as_posix()]
    built = subprocess.run(command, cwd=ROOT, env=env, capture_output=True)
    (output/'compiler.log').write_bytes(built.stdout+built.stderr)
    if built.returncode:
        raise RuntimeError('C profile test compilation failed: '+built.stderr.decode('utf-8', errors='replace'))
    tested = subprocess.run([str(target)], env=env, capture_output=True, text=True, encoding='utf-8')
    result = {'completed': tested.returncode == 0, 'command': command, 'exit_code': tested.returncode,
              'test_output': tested.stdout+tested.stderr, 'binary_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
              'firmware_executed': False, 'camera_accessed': False}
    (output/'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)
    if tested.returncode:
        raise RuntimeError('C result profile behavior test failed')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
