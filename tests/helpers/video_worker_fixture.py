"""A faulty external worker used to exercise the real parent job boundary."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', type=Path, required=True)
    args = parser.parse_args()
    mode = os.environ['Z62_ASYNC_TEST_MODE']
    if mode in ('block', 'error-but-live', 'descendant'):
        if mode == 'error-but-live':
            from z62_async_video_job import atomic_json
            job = json.loads((args.job / 'descriptor.json').read_bytes())
            atomic_json(args.job / 'progress.json', {
                'job_id': job['job_id'], 'phase': 'error', 'prepared_frames': 0})
        if mode == 'descendant':
            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            (args.job / 'descendant.pid').write_text(str(child.pid), encoding='ascii')
        (args.job / 'fixture-entered').write_bytes(b'worker is alive')
        while True:
            time.sleep(.05)
    import z62_async_video_worker as worker
    status = worker.run(args.job)
    if status:
        return status
    if mode == 'exit-nonzero':
        return 7
    if mode == 'corrupt-source':
        path = args.job / 'output/media.json'
        data = json.loads(path.read_bytes())
        data['source_map_sha256'] = '0' * 64
        path.write_text(json.dumps(data), encoding='utf-8')
        result_path = args.job / 'result.json'
        result = json.loads(result_path.read_bytes())
        result['files']['metadata']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        result['files']['metadata']['bytes'] = path.stat().st_size
        result_path.write_text(json.dumps(result), encoding='utf-8')
    if mode == 'corrupt-file':
        path = args.job / 'output/movie.mp4'
        data = bytearray(path.read_bytes())
        data[-1] ^= 1
        path.write_bytes(data)
    if mode == 'ready-but-live':
        (args.job / 'fixture-entered').write_bytes(b'result exists but worker is still alive')
        while True:
            time.sleep(.05)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
