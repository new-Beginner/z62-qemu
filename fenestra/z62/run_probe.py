"""Execute no-firmware loader probe on the user's pinned native Z62 QEMU.

This is a synthetic ARM instruction test, not a Nikon firmware integration or
hardware/flash qualification. It cannot generate or install a camera update.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import time

from pack import VERSION, digest
from build_probe import ROOT, require

sys.path.insert(0, str(ROOT / 'tools'))
from probe_reference_devices import free_port, connect
from probe_z62_functional_raw import Session

QEMU_REL = '.build/z62-output-lineage-2026.11.03-r69/runtime/qemu-system-arm.exe'
QEMU_SHA = '37603d1f8c55f819c0e1d3808e670d2de562b954152f2d8b847d1068359296f9'


def run(build, output):
    root = Path('Q:/')
    require(root.is_dir() and root.samefile(ROOT), 'Verified ASCII Q: workspace alias required')
    build = build.resolve()
    output = output.resolve()
    require(build.is_relative_to(ROOT / '.build'), 'Build must be in project .build')
    require(output.is_relative_to(ROOT / 'analysis') and not output.exists(), 'Evidence must be a new project analysis file')
    manifest_path = build / 'build.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    require(manifest.get('completed') is True and manifest['version'] == VERSION, 'Incomplete or incompatible build')
    for name, sha in manifest['source_sha256'].items():
        path = (ROOT / name).resolve()
        require(path.is_relative_to(ROOT), 'Source manifest escaped project')
        require(digest(path.read_bytes()).hex() == sha, 'Source identity changed: ' + name)
    for name, sha in manifest['artifact_sha256'].items():
        path = (build / name).resolve()
        require(path.is_relative_to(build), 'Artifact manifest escaped build')
        require(digest(path.read_bytes()).hex() == sha, 'Artifact identity changed: ' + name)
    binary = root / QEMU_REL
    require(digest(binary.read_bytes()).hex() == QEMU_SHA, 'Current QEMU binary identity mismatch')
    image = root / build.relative_to(ROOT) / 'probe.bin'
    qmp_port, wire_port = free_port(), free_port()
    command = [str(binary), '-M', 'nikon-z62-dual-lab', '-smp', '4,maxcpus=5', '-S',
               '-display', 'none', '-serial', 'none', '-monitor', 'none', '-nic', 'none',
               '-qmp', f'tcp:127.0.0.1:{qmp_port},server=on,wait=off',
               '-qtest', f'tcp:127.0.0.1:{wire_port},server=on,wait=off', '-qtest-log', 'NUL']
    for cpu in (1, 2, 3):
        command += ['-device', f'loader,addr=0x13d00000,data=0xeafffffe,data-len=4,cpu-num={cpu}',
                    '-device', f'loader,addr=0x13d00000,cpu-num={cpu}']
    command += ['-device', f'loader,file={image},addr=0x10020000,force-raw=on,cpu-num=0']
    output.parent.mkdir(parents=True, exist_ok=True)
    log_path = output.with_suffix('.qemu.log')
    require(not log_path.exists(), 'QEMU log already exists')
    record = dict(version=VERSION, completed=False, command=command, qemu_sha256=QEMU_SHA,
                  build_manifest_sha256=digest(manifest_path.read_bytes()).hex(),
                  build_directory=str(build), firmware_loaded=False, camera_accessed=False,
                  firmware_integrated=False, module_execution_verified=False, flash_safety_verified=False)
    streams, sockets = [], []
    process, session = None, None
    with output.open('x', encoding='utf-8') as evidence:
        try:
            env = dict(os.environ, TEMP=os.environ['PI_SCRATCH_DIR'], TMP=os.environ['PI_SCRATCH_DIR'])
            with log_path.open('xb') as log:
                process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log, env=env)
            record['owned_pid'] = process.pid
            session = Session()
            sock = connect(qmp_port, process); sockets.append(sock); sock.settimeout(5)
            session.qmp = sock.makefile('rwb'); streams.append(session.qmp)
            json.loads(session.qmp.readline()); session.query('qmp_capabilities')
            sock = connect(wire_port, process); sockets.append(sock); sock.settimeout(5)
            session.wire = sock.makefile('rwb'); streams.append(session.wire); session.irqs = []
            session.query('cont')
            deadline = time.monotonic() + 30
            raw = bytes(40)
            while time.monotonic() < deadline:
                raw = session.read(0x13e00000, 40)
                words = struct.unpack('<10I', raw)
                if words[0] == 0x46583632 and words[1] in (2, 0xbad):
                    break
                require(process.poll() is None, 'Owned QEMU exited before probe completion')
                time.sleep(.02)
            session.query('stop')
            record['registers'] = session.query('human-monitor-command', {'command-line': 'info registers'})
            names = ('magic','phase','passed','failed_case','actual','expected','logs','pointer_bytes','entry0','entry1')
            result = dict(zip(names, struct.unpack('<10I', raw)))
            record['probe'] = result
            record['fixture_names'] = manifest['fixture_names']
            require(result['magic'] == 0x46583632 and result['phase'] == 2, 'Guest probe failed or timed out: ' + repr(result))
            require(result['passed'] == 2 * len(manifest['fixture_names']), 'Incomplete guest checks')
            require(result['logs'] == 2 and result['pointer_bytes'] == 4, 'Callback/word-size check failed')
            require(result['entry0'] != result['entry1'] and result['entry0'] % 4 == result['entry1'] % 4 == 2,
                    'Relocated Thumb entries were not independently exercised')
            record['module_execution_verified'] = True
            session.query('quit')
            process.wait(timeout=15)
            require(process.returncode == 0, 'Owned QEMU did not exit normally')
            record['completed'] = True
        except Exception as exc:
            record['failure'] = dict(type=type(exc).__name__, message=str(exc))
            raise
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=10)
            record['owned_process_closed'] = process is not None and process.poll() is not None
            record['exit_code'] = None if process is None else process.returncode
            for handle in (*streams, *sockets):
                handle.close()
            if log_path.exists():
                record['log_sha256'] = digest(log_path.read_bytes()).hex()
            json.dump(record, evidence, indent=2)
            evidence.write('\n')
    print(json.dumps({k: record[k] for k in ('completed','probe','owned_process_closed','firmware_loaded','flash_safety_verified')}, indent=2))
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.build, args.output)
