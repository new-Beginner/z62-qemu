# SPDX-License-Identifier: GPL-2.0-or-later
"""No-firmware QEMU integration checks for the optional input access ring."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def connect(port, process):
    deadline = time.monotonic() + 20
    while True:
        try:
            return socket.create_connection(('127.0.0.1', port), timeout=10)
        except ConnectionRefusedError:
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError('Device-test QEMU startup failed')
            time.sleep(0.05)


def check(binary, enabled):
    with tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR'), prefix='trace-test-') as folder:
        qmp_port, wire_port = free_port(), free_port()
        command = [str(binary.resolve()), '-M', 'nikon-z62-dual-lab', '-smp', '4,maxcpus=5',
                   '-display', 'none', '-serial', 'none', '-monitor', 'none', '-nic', 'none', '-S',
                   '-global', 'nikon-z72-boot-config.input-trace=' + ('on' if enabled else 'off'),
                   '-qmp', f'tcp:127.0.0.1:{qmp_port},server=on,wait=off',
                   '-qtest', f'tcp:127.0.0.1:{wire_port},server=on,wait=off',
                   '-qtest-log', 'NUL' if os.name == 'nt' else '/dev/null']
        with (Path(folder) / 'qemu.log').open('wb') as log:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log)
        sockets = []
        streams = []
        try:
            qmp_sock = connect(qmp_port, process)
            sockets.append(qmp_sock)
            qmp = qmp_sock.makefile('rwb')
            streams.append(qmp)
            json.loads(qmp.readline())
            def query(name, arguments=None, error=False):
                qmp.write(json.dumps({'execute': name, 'arguments': arguments or {}}).encode() + b'\n')
                qmp.flush()
                while True:
                    data = json.loads(qmp.readline())
                    if 'event' not in data:
                        break
                if error:
                    assert 'error' in data, data
                    return data['error']
                assert 'return' in data, data
                return data['return']
            query('qmp_capabilities')
            entries = query('qom-list', {'path': '/machine/unattached'})
            paths = ['/machine/unattached/' + item['name'] for item in entries
                     if item['type'] == 'child<nikon-z72-boot-config>']
            assert len(paths) == 2, paths
            def get(path, name):
                return query('qom-get', {'path': path, 'property': name})
            for path in paths:
                assert get(path, 'input-trace-count') == 0
                assert get(path, 'input-trace-log') == ''
            wire_sock = connect(wire_port, process)
            sockets.append(wire_sock)
            wire = wire_sock.makefile('rwb')
            streams.append(wire)
            def access(command):
                wire.write(command.encode() + b'\n')
                wire.flush()
                result = wire.readline().decode().strip()
                assert result.startswith('OK'), result
                return result
            access('writel 0x20063020 0x1234')
            active = [path for path in paths if get(path, 'input-trace-count')]
            if not enabled:
                assert not active
                return {'enabled': False, 'default_off_verified': True}
            assert len(active) == 1, active
            path = active[0]
            assert get(path, 'input-trace-log') == '20063020:00001234w'
            assert access('readl 0x20063020') == 'OK 0x0000000000001234'
            assert get(path, 'input-trace-log') == '20063020:00001234w,20063020:00001234r'
            access('readl 0x04282014')
            assert get(path, 'input-trace-count') == 2
            for value in range(300):
                access(f'writel 0x20063020 {value:#x}')
            expected = ','.join(f'20063020:{value:08x}w' for value in range(44, 300))
            assert get(path, 'input-trace-count') == 302
            assert get(path, 'input-trace-log') == expected
            query('qom-set', {'path': path, 'property': 'input-trace-count', 'value': 0}, error=True)
            assert get(path, 'input-trace-count') == 302
            query('system_reset')
            assert get(path, 'input-trace-count') == 0
            assert get(path, 'input-trace-log') == ''
            access('writel 0x20063020 0xabcd')
            assert get(path, 'input-trace-log') == '20063020:0000abcdw'
            peer = next(item for item in paths if item != path)
            assert get(peer, 'input-trace-count') == 0
            return {'enabled': True, 'short_ring': True, 'read_write_order': True,
                    'range_filter': True, 'wrap_256': True, 'reset': True,
                    'qom_read_only': True, 'engine_isolation': True,
                    'firmware_loaded': False}
        finally:
            for stream in streams:
                stream.close()
            for sock in sockets:
                sock.close()
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'schema': 1, 'checks': [check(args.qemu, False), check(args.qemu, True)]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
