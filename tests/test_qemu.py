"""Unit tests and optional real-QEMU integration tests for the current lab."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_qemu as build
import run_qemu as run

PLATFORM = 'windows-x64' if os.name == 'nt' else 'linux'
PACKAGE = ROOT / 'dist' / f'z6ii-qemu-v{run.VERSION}-{PLATFORM}'


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def connect(number, process):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            return socket.create_connection(('127.0.0.1', number), timeout=2)
        except OSError:
            if process.poll() is not None:
                raise AssertionError(f'QEMU exited before opening debug socket: {process.returncode}')
            time.sleep(0.05)
    raise AssertionError('Debug socket did not become ready')


def rsp(sock, text):
    data = text.encode('ascii')
    sock.sendall(b'$' + data + b'#' + f'{sum(data) & 255:02x}'.encode())
    while True:
        value = sock.recv(1)
        if value == b'$':
            break
        if not value:
            raise AssertionError('GDB socket closed')
    response = bytearray()
    while True:
        value = sock.recv(1)
        if not value:
            raise AssertionError('GDB packet interrupted')
        if value == b'#':
            break
        response.extend(value)
    checksum = bytearray()
    while len(checksum) < 2:
        checksum.extend(sock.recv(2 - len(checksum)))
    if int(checksum, 16) != sum(response) & 255:
        raise AssertionError('GDB response checksum mismatch')
    sock.sendall(b'+')
    return response.decode('ascii')


class QemuToolTests(unittest.TestCase):
    def test_versions_match_board_and_launcher(self):
        self.assertEqual(build.LAB_VERSION, run.VERSION)
        source = (ROOT / 'qemu/nikon-z6ii.c').read_text()
        self.assertIn(f'#define Z6II_VERSION "{run.VERSION}"', source)
        self.assertNotIn('Z6_ASSISTED_UNKNOWN', source)

    def test_archive_filter_rejects_traversal_and_windows_paths(self):
        for name in ['../escape', '/absolute', 'qemu-10.2.4/../../escape',
                     'qemu-10.2.4/C:/escape', 'wrong-root/file',
                     'qemu-10.2.4/' + chr(92) + 'escape']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                build.archive_filter(tarfile.TarInfo(name), '.')
        regular = tarfile.TarInfo('qemu-10.2.4/VERSION')
        self.assertIs(build.archive_filter(regular, '.'), regular)
        link = tarfile.TarInfo('qemu-10.2.4/link')
        link.type, link.linkname = tarfile.SYMTYPE, '/outside'
        self.assertIsNone(build.archive_filter(link, '.'))

    def test_raw_qemu_arguments_use_one_engine_and_local_debug_endpoints(self):
        args = run.command(Path('qemu.exe'), Path('firmware.bin'), 'slave', 2, True, 1234, 4444)
        self.assertIn('nikon-z6ii,engine=slave', args)
        self.assertIn('tcp:127.0.0.1:1234', args)
        self.assertIn('tcp:127.0.0.1:4444,server=on,wait=off', args)
        self.assertIn('-S', args)
        self.assertEqual(args[args.index('-smp') + 1], '2')
        for role, cores in [('both', 1), ('master', 4)]:
            with self.assertRaises(ValueError):
                run.command(Path('qemu.exe'), Path('firmware.bin'), role, cores)

    def test_manifest_rejects_changed_executable_and_unsafe_names(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            binary = directory / 'qemu.exe'
            binary.write_bytes(b'original')
            overlay = directory / 'source-overlay'
            overlay.mkdir()
            (overlay / 'nikon-z6ii.c').write_bytes(b'board')
            manifest = {'lab_version': run.VERSION, 'machine': 'nikon-z6ii',
                        'binary': binary.name, 'binary_sha256': run.digest(binary),
                        'board_sha256': run.digest(overlay / 'nikon-z6ii.c')}
            target = directory / 'build-manifest.json'
            target.write_text(json.dumps(manifest))
            self.assertEqual(run.verify_binary(directory)[0], binary.resolve())
            binary.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'binary SHA-256'):
                run.verify_binary(directory)
            manifest['binary'] = '../outside.exe'
            target.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                run.verify_binary(directory)

    def test_output_parser_preserves_real_fault_fields(self):
        output = 'noise\nZ6II_BOOT {"engine":"master"}\nZ6II_EVENT {"pc":268615076,"value":33}\n'
        boot, events = run.parse_output(output)
        self.assertEqual(boot, {'engine': 'master'})
        self.assertEqual(events, [{'pc': 268615076, 'value': 33}])


class QemuRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (PACKAGE / 'build-manifest.json').is_file():
            if os.environ.get('Z6II_QEMU_REQUIRED') == '1':
                raise AssertionError('Required native QEMU package is absent')
            raise unittest.SkipTest('Build native QEMU first; runtime tests not verified')
        cls.binary, cls.manifest = run.verify_binary(PACKAGE)
        cls.payload_dir = ROOT / 'artifacts/z6ii-1.70'

    def test_machine_is_registered_in_real_qemu(self):
        result = subprocess.run([str(self.binary), '-machine', 'help'], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b'nikon-z6ii', result.stdout)

    def test_original_master_and_slave_reach_first_unmodeled_status_read(self):
        with tempfile.TemporaryDirectory() as folder:
            report = run.run(PACKAGE, self.payload_dir, ['master', 'slave'],
                             report_dir=Path(folder), platform_config=False)
        self.assertFalse(report['inter_chip_transport_connected'])
        for row in report['results']:
            with self.subTest(engine=row['engine']):
                self.assertEqual(row['status'], 'unmodeled_hardware')
                self.assertEqual(row['qemu_exit_code'], 2)
                fault = row['events'][0]
                self.assertEqual(fault['address'], 0x20022300)
                self.assertEqual(fault['pc'], 0x100208E0)
                self.assertEqual(fault['access'], 'read')
                self.assertEqual(fault['registers'][:3], [0x20022300, 1, 40000000])
                self.assertFalse(fault['response_fabricated'])
                self.assertFalse(row['menu_reached'])

    def test_native_board_rejects_wrong_engine_payload(self):
        payload = self.payload_dir / run.PAYLOADS['slave'][0]
        args = run.command(self.binary, payload, 'master')
        result = subprocess.run(args, cwd=payload.parent, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b'SHA-256/length mismatch', result.stderr)

    def test_gdb_reads_original_rom_and_single_steps_reset_branch(self):
        number = port()
        payload = self.payload_dir / run.PAYLOADS['master'][0]
        args = run.command(self.binary, payload, 'master', paused=True, gdb_port=number)
        process = subprocess.Popen(args, cwd=payload.parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            with connect(number, process) as sock:
                first = rsp(sock, 'g')
                pc = int.from_bytes(bytes.fromhex(first[15 * 8:16 * 8]), 'little')
                self.assertEqual(pc, 0x10020000)
                self.assertEqual(bytes.fromhex(rsp(sock, 'm10020000,4')), payload.read_bytes()[:4])
                self.assertTrue(rsp(sock, 's').startswith(('T05', 'S05')))
                second = rsp(sock, 'g')
                pc = int.from_bytes(bytes.fromhex(second[15 * 8:16 * 8]), 'little')
                self.assertEqual(pc, 0x1002BC88)
        finally:
            process.kill()
            process.communicate()

    def test_qmp_reports_stopped_guest_and_two_cores_within_one_engine(self):
        number = port()
        payload = self.payload_dir / run.PAYLOADS['slave'][0]
        args = run.command(self.binary, payload, 'slave', cores=2, paused=True, qmp_port=number)
        process = subprocess.Popen(args, cwd=payload.parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            with connect(number, process) as sock:
                with sock.makefile('rwb') as stream:
                    self.assertIn('QMP', json.loads(stream.readline()))
                    def query(name):
                        stream.write(json.dumps({'execute': name}).encode() + b'\n')
                        stream.flush()
                        while True:
                            response = json.loads(stream.readline())
                            if 'return' in response:
                                return response['return']
                            if 'error' in response:
                                self.fail(response)
                    query('qmp_capabilities')
                    self.assertFalse(query('query-status')['running'])
                    self.assertEqual(len(query('query-cpus-fast')), 2)
        finally:
            process.kill()
            process.communicate()


if __name__ == '__main__':
    unittest.main()
