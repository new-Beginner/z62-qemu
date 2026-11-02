# SPDX-License-Identifier: GPL-2.0-or-later
"""Native QEMU qtest RAW DMA checks, no firmware and no CPU execution."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import socket
import time
from probe_reference_devices import free_port, connect
import z62_functional_device as functional

WIDTH, HEIGHT, STRIDE = 1514, 1006, 2272
SIZE = HEIGHT * STRIDE
SLOTS = (0x82C00000, 0x8448DC00, 0x85D1B800, 0x875A9400)
MASTER, SLAVE = '/machine/master-input', '/machine/slave-input'


def pattern():
    result = bytearray(SIZE)
    for y in range(HEIGHT):
        for x in range(0, WIDTH, 2):
            a, b = ((x * 3 + y * 5 + 0x100) & 4095,
                    ((x + 1) * 3 + y * 5 + 0x100) & 4095)
            p = y * STRIDE + x // 2 * 3
            result[p:p + 3] = bytes((a & 255, (a >> 8) | ((b & 15) << 4), b >> 4))
    return bytes(result)


def descriptors():
    return {0x20069514: 6, 0x20069518: 0x05EA0000, 0x2006951C: 0x03EE0000,
            0x20069A08: STRIDE, 0x20069A3C: 0,
            **{0x20069A50 + i * 4: addr for i, addr in enumerate(SLOTS)}}


class Session:
    def query(self, command, arguments=None, error=False):
        self.qmp.write(json.dumps({'execute': command, 'arguments': arguments or {}}).encode() + b'\n')
        self.qmp.flush()
        while True:
            result = json.loads(self.qmp.readline())
            if 'event' not in result:
                break
        assert ('error' if error else 'return') in result, result
        return result.get('error' if error else 'return')

    def access(self, command):
        self.wire.write(command.encode() + b'\n')
        self.wire.flush()
        while True:
            result = self.wire.readline().decode().strip()
            if not result.startswith('IRQ '):
                break
            self.irqs.append(result)
        assert result.startswith('OK'), (command, result)
        return result

    def write(self, addr, value):
        self.access(f'writel {addr:#x} {value:#x}')

    def read(self, addr, size):
        data = bytearray()
        for offset in range(0, size, 65536):
            length = min(65536, size - offset)
            data.extend(bytes.fromhex(self.access(f'read {addr + offset:#x} {length:#x}').split()[1][2:]))
        return bytes(data)

    def get(self, name, path=MASTER):
        return self.query('qom-get', {'path': path, 'property': name})

    def configure(self):
        for addr, value in descriptors().items():
            self.write(addr, value)

    def submit(self):
        self.write(0x20068104, 1)

    def fill(self, value=0xA5):
        for addr in SLOTS:
            before = 0 if addr == SLOTS[0] else 4
            self.access(f'memset {addr - before:#x} {SIZE + before + 4:#x} {value:#x}')

    def verify_slots(self, expected, guards=False):
        for addr in SLOTS:
            actual = self.read(addr, SIZE)
            assert actual == expected, (hex(addr), hashlib.sha256(actual).hexdigest())
            if guards:
                assert self.read(addr + SIZE, 4) == b'\xa5' * 4
                if addr != SLOTS[0]:  # first pool byte has no writable predecessor
                    assert self.read(addr - 4, 4) == b'\xa5' * 4


@contextmanager
def session(binary, enabled):
    with tempfile.TemporaryDirectory(dir=os.environ.get('PI_SCRATCH_DIR'), prefix='functional-raw-') as folder:
        qmp_port, wire_port = free_port(), free_port()
        command = [str(binary.resolve()), '-M', 'nikon-z62-dual-lab', '-smp', '4,maxcpus=5',
                   '-display', 'none', '-serial', 'none', '-monitor', 'none', '-nic', 'none', '-S',
                   '-qmp', f'tcp:127.0.0.1:{qmp_port},server=on,wait=off',
                   '-qtest', f'tcp:127.0.0.1:{wire_port},server=on,wait=off',
                   '-qtest-log', 'NUL' if os.name == 'nt' else '/dev/null']
        # Default-off test intentionally does not supply a functional-raw property.
        if enabled:
            command += ['-global', 'nikon-z72-input-config.functional-raw=on']
        with (Path(folder) / 'qemu.log').open('wb') as log:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log)
        sockets, streams = [], []
        try:
            s = Session()
            sock = connect(qmp_port, process)
            sockets.append(sock)
            s.qmp = sock.makefile('rwb')
            streams.append(s.qmp)
            json.loads(s.qmp.readline())
            s.query('qmp_capabilities')
            sock = connect(wire_port, process)
            sockets.append(sock)
            s.wire = sock.makefile('rwb')
            streams.append(s.wire)
            s.command = command
            s.irqs = []
            s.access(f'irq_intercept_out {MASTER} raw-complete')
            yield s
        except Exception:
            print((Path(folder) / 'qemu.log').read_text(errors='replace'))
            raise
        finally:
            for stream in streams:
                stream.close()
            for sock in sockets:
                sock.close()
            if process.poll() is None:
                process.terminate()  # only this probe's own child
            process.wait(timeout=10)


def check_default(binary):
    with session(binary, False) as s:
        s.configure()
        s.fill()
        s.submit()
        s.verify_slots(b'\xa5' * SIZE)
        assert s.get('raw-accepted') == s.get('raw-bytes') == 0
        assert s.get('raw-rejected') == 1 and s.get('raw-last-reason') == 'disabled'
        assert not s.irqs
        return {'default_off_no_write': True, 'command': s.command}


def check_enabled(binary):
    expected = pattern()
    with session(binary, True) as s:
        s.configure()
        s.fill()
        # Configuration alone, and non-submit values, cannot trigger DMA.
        s.write(0x20068104, 0)
        s.write(0x20068104, 2)
        assert s.get('raw-accepted') == s.get('raw-rejected') == 0
        s.verify_slots(b'\xa5' * SIZE)
        s.submit()
        s.verify_slots(expected, guards=True)
        assert s.get('raw-accepted') == 1 and s.get('raw-bytes') == 4 * SIZE
        assert s.get('raw-last-reason') == 'success'
        assert s.irqs == ['IRQ raise 0', 'IRQ lower 0']
        s.submit()
        assert s.get('raw-accepted') == 2 and s.get('raw-bytes') == 8 * SIZE
        assert s.get('raw-accepted', SLAVE) == s.get('raw-rejected', SLAVE) == 0
        assert s.irqs == ['IRQ raise 0', 'IRQ lower 0'] * 2
        cases = [
            ('stride', 0x20069A08, STRIDE + 1, 'stride'),
            ('zero-last-slot', 0x20069A5C, 0, 'address'),
            ('out-of-pool-last-slot', 0x20069A5C, 0x8AEBC400 - SIZE + 4, 'address'),
            ('overlap-last-slot', 0x20069A5C, SLOTS[0] + 4, 'overlap'),
            ('unaligned-last-slot', 0x20069A5C, SLOTS[3] + 1, 'address'),
            ('mmio-last-slot', 0x20069A5C, 0x20068104, 'address'),
            ('code-last-slot', 0x20069A5C, 0xCC200000, 'address'),
            ('width-lowhalf', 0x20069518, 0x05EA0001, 'geometry'),
            ('height-lowhalf', 0x2006951C, 0x03EE0001, 'geometry'),
            ('width-other', 0x20069518, 0x05EC0000, 'geometry'),
            ('config-gate', 0x20069514, 0, 'config'),
            ('selected-empty-bank-no-fallback', 0x20069A3C, 1, 'address'),
        ]
        checks = []
        for number, (name, addr, value, reason) in enumerate(cases, 1):
            s.configure()
            s.fill()
            s.write(addr, value)
            s.submit()
            assert s.get('raw-accepted') == 2 and s.get('raw-bytes') == 8 * SIZE
            assert s.get('raw-rejected') == number
            assert s.get('raw-last-reason') == reason, name
            s.verify_slots(b'\xa5' * SIZE, guards=True)
            checks.append(name)
            assert s.irqs == ['IRQ raise 0', 'IRQ lower 0'] * 2
        # Bank 1 valid, bank 0 invalid: selected descriptors only, no fallback.
        s.configure()
        for i, addr in enumerate(SLOTS):
            s.write(0x20069A60 + 4 * i, addr)
            s.write(0x20069A50 + 4 * i, 0)
        s.write(0x20069A3C, 1)
        s.submit()
        s.verify_slots(expected, guards=True)
        assert s.get('raw-accepted') == 3
        for name in ('raw-accepted', 'raw-rejected', 'raw-bytes', 'raw-last-reason'):
            s.query('qom-set', {'path': MASTER, 'property': name,
                              'value': 'reset' if name.endswith('reason') else 0}, error=True)
        s.query('system_reset')
        deadline = time.monotonic() + 5
        while s.get('raw-accepted') and time.monotonic() < deadline:
            time.sleep(0.01)
        assert all(s.get(name) == 0 for name in ('raw-accepted', 'raw-rejected', 'raw-bytes'))
        assert s.get('raw-last-reason') == 'reset'
        s.submit()
        assert s.get('raw-last-reason') == 'config'  # descriptors reset too
        s.configure()
        s.submit()
        assert s.get('raw-accepted') == 1
        return {'four_slots_full_readback': True, 'row_padding_and_guards': True,
                'bytes_per_slot': SIZE, 'pattern_sha256': hashlib.sha256(expected).hexdigest(),
                'reject_without_any_slot_write': checks, 'selected_bank1': True,
                'repeated_submit': True, 'reset': True, 'qom_read_only': True,
                'peer_counters_isolated': True, 'raw_complete_success_only': True,
                'command': s.command}


def configure_slave(s):
    # qtest accesses first_cpu only. GDB selects paused CPU2 solely to write
    # slave MMIO descriptors; no firmware, PC writes or CPU execution. Initial
    # generic-loader MMIO writes are erased by the board's reset ordering.
    port = free_port()
    s.query('human-monitor-command', {'command-line': f'gdbserver tcp:127.0.0.1:{port}'})
    assert not s.query('query-status')['running']
    with socket.create_connection(('127.0.0.1', port), timeout=10) as sock:
        def request(text):
            data = text.encode()
            sock.sendall(b'$' + data + b'#' + f'{sum(data) & 255:02x}'.encode())
            def byte():
                result = sock.recv(1)
                if not result:
                    raise RuntimeError('GDB socket closed')
                return result
            while byte() != b'$':
                pass
            response = bytearray()
            current = byte()
            while current != b'#':
                response.extend(current)
                current = byte()
            checksum = byte() + byte()
            assert int(checksum, 16) == sum(response) & 255
            sock.sendall(b'+')
            return response.decode()
        assert request('Hg3') == 'OK'  # GDB thread3 = CPU index2 = slave core0
        for addr, value in descriptors().items():
            data = value.to_bytes(4, 'little').hex()
            assert request(f'M{addr:x},4:{data}') == 'OK'
            assert request(f'm{addr:x},4') == data
    assert not s.query('query-status')['running']


def check_engine_root(binary):
    # Valid pool descriptors MUST reject: slave has no processing-pool RAM.
    with session(binary, True) as s:
        configure_slave(s)
        s.configure()
        s.fill()
        s.access(f'set_irq_in {SLAVE} raw-submit 0 1')
        s.access(f'set_irq_in {SLAVE} raw-submit 0 0')
        assert s.get('raw-rejected', SLAVE) == 1
        assert s.get('raw-last-reason', SLAVE) == 'not-writable-ram'
        assert s.get('raw-root', SLAVE) != s.get('raw-root')
        assert s.get('raw-accepted') == s.get('raw-rejected') == 0
        s.verify_slots(b'\xa5' * SIZE)
        s.submit()
        assert s.get('raw-accepted') == 1 and s.get('raw-accepted', SLAVE) == 0
        return {'engine_local_root_verified': True, 'slave_unmapped_ram_rejected': True,
                'slave_setup': 'paused-GDB-CPU2-MMIO-only; trigger/readback via qtest',
                'command': s.command}


def run(binary):
    manifest = json.loads((binary.parent.parent / 'functional-build-manifest.json').read_text(encoding='utf-8'))
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    assert manifest['binary_sha256'] == digest
    assert manifest['functional_device'] == functional.identity()
    return {'schema': 1, 'version': functional.VERSION, 'binary_sha256': digest,
            'firmware_loaded': False, 'guest_executed': False,
            'packing_hardware_verified': False, 'sensor_irq_completion_added': False,
            'checks': [check_default(binary), check_enabled(binary), check_engine_root(binary)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.qemu)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
