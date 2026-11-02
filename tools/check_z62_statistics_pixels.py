"""Compile and run portable statistics arithmetic checks with the recorded compiler."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    old = json.loads((ROOT / '.build/z62-raw-boundary-2026.10.29-r17/reference-build-manifest.json').read_text())
    binary = Path(old['msys2_dir']) / 'ucrt64/bin'
    env = {**os.environ, 'PATH': str(binary) + os.pathsep + os.environ['PATH']}
    source = ROOT / 'tests/native/z62_statistics_pixels_test.c'
    header = ROOT / 'qemu/z62-continuous-stats/nikon-z62-statistics-pixels.h'
    target = output.resolve() / 'pixels-test.exe'
    command = [str(binary / 'gcc.exe'), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
               source.relative_to(ROOT).as_posix(), '-o', target.relative_to(ROOT).as_posix()]
    result = {'completed': False, 'command': command, 'camera_accessed': False, 'firmware_executed': False}
    try:
        built = subprocess.run(command, cwd=ROOT, env=env, capture_output=True)
        (output / 'compiler.log').write_bytes(built.stdout + built.stderr)
        if built.returncode:
            raise RuntimeError('Native compiler failed: ' + (built.stdout + built.stderr).decode('utf-8', errors='replace'))
        tested = subprocess.run([str(target)], cwd=ROOT, env=env, capture_output=True, text=True,
                                encoding='utf-8', errors='replace')
        (output / 'test.log').write_text(tested.stdout+tested.stderr, encoding='utf-8')
        if tested.returncode:
            raise RuntimeError(f'Native pixel test failed ({tested.returncode}): '+tested.stdout+tested.stderr)
        result.update(completed=True, test_output=tested.stdout+tested.stderr,
                      header_sha256=hashlib.sha256(header.read_bytes()).hexdigest(),
                      test_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                      binary_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        print(tested.stdout)
    except Exception as exc:
        result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        with (output / 'report.json').open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
