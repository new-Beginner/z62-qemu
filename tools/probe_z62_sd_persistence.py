# SPDX-License-Identifier: GPL-2.0-or-later
"""No-firmware SDHCI PIO write/read and reopen acceptance on synthetic media."""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

from probe_reference_devices import free_port, connect
from z62_virtual_sd import CardSession, digest


def transfer(binary, image, snapshot, write_data=None):
    qmp_port, port = free_port(), free_port()
    command = [str(binary.resolve()), '-M', 'nikon-z62-dual-lab', '-smp', '4,maxcpus=5',
               '-S', '-display', 'none', '-monitor', 'none', '-serial', 'none', '-nic', 'none',
               '-global', 'nikon-z72-boot-config.sd-host=on',
               '-drive', f'if=none,id=card,file={image.as_posix()},format=raw,snapshot={"on" if snapshot else "off"}',
               '-device', 'sd-card,drive=card,bus=/z72-sd-master/sd-bus',
               '-qmp', f'tcp:127.0.0.1:{qmp_port},server=on,wait=off',
               '-qtest', f'tcp:127.0.0.1:{port},server=on,wait=off',
               '-qtest-log', 'NUL' if os.name == 'nt' else '/dev/null']
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log)
        sockets, streams = [], []
        try:
            for p in (qmp_port, port):
                sock = connect(p, process)
                sockets.append(sock)
                streams.append(sock.makefile('rwb'))
            qmp, wire = streams
            if 'QMP' not in json.loads(qmp.readline()):
                raise RuntimeError('No QMP greeting')
            def monitor(name):
                qmp.write(json.dumps({'execute': name}).encode() + b'\n')
                qmp.flush()
                while True:
                    reply = json.loads(qmp.readline())
                    if 'event' not in reply:
                        if 'return' not in reply:
                            raise RuntimeError(str(reply))
                        return reply['return']
            monitor('qmp_capabilities')
            def access(text):
                wire.write(text.encode() + b'\n')
                wire.flush()
                reply = wire.readline().decode().split()
                if not reply or reply[0] != 'OK':
                    raise RuntimeError(str(reply))
                return int(reply[1], 0) if len(reply) > 1 else None
            def read(off, width='l'):
                return access(f'read{width} {0x2a810000 + off:#x}')
            def write(off, value, width='l'):
                access(f'write{width} {0x2a810000 + off:#x} {value:#x}')
            def cmd(index, argument=0, flags=0, direction=None):
                block = direction is not None
                write(4, 512 if block else 0, 'w')
                write(6, 1 if block else 0, 'w')
                write(8, argument)
                write(0xc, (0x12 if direction == 'read' else 2) if block else 0, 'w')
                write(0xe, index << 8 | flags, 'w')
            write(0x2f, 1, 'b')
            write(0x29, 0xf, 'b')
            write(0x2c, 7, 'w')
            write(0x34, 0xffffffff)
            cmd(55)
            cmd(41, 0x41200000)
            cmd(2)
            cmd(3, flags=3)
            rca = read(0x10) & 0xffff0000
            if not rca:
                raise RuntimeError('No RCA')
            cmd(7, rca)
            if write_data is not None:
                if len(write_data) != 512:
                    raise ValueError('Expected one sector')
                write(0x30, 0xffffffff)
                cmd(24, flags=0x20, direction='write')
                if not read(0x24) & 0x400:
                    raise RuntimeError('SDHCI is not ready for PIO write')
                for value, in struct.iter_unpack('<I', write_data):
                    write(0x20, value)
                if not read(0x30) & 2:
                    raise RuntimeError('Write did not complete')
            write(0x30, 0xffffffff)
            cmd(17, flags=0x20, direction='read')
            if not read(0x24) & 0x800:
                raise RuntimeError('SDHCI is not ready for PIO read')
            data = b''.join(struct.pack('<I', read(0x20)) for _ in range(128))
            monitor('quit')
            process.wait(timeout=10)
            if process.returncode != 0:
                raise RuntimeError(f'QEMU exit {process.returncode}')
            return data
        except BaseException as exc:
            log.seek(0)
            raise RuntimeError(str(exc) + '\n' + log.read().decode(errors='replace')) from exc
        finally:
            for stream in streams:
                stream.close()
            for sock in sockets:
                sock.close()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


def check(binary):
    with tempfile.TemporaryDirectory(prefix='sd-persist-', dir=os.environ.get('PI_SCRATCH_DIR')) as folder:
        root = Path(folder)
        original = root / 'card.raw'
        with original.open('wb') as out:
            out.write(b'A' * 512)
            out.truncate(1024 * 1024)
        results = []
        for mode in ('snapshot', 'persistent'):
            work = root / mode
            work.mkdir()
            before = digest(original)
            card = CardSession(original, work, mode)
            try:
                marker = bytes((index * 17 + 3) & 255 for index in range(512))
                observed = transfer(binary, card.staged, mode == 'snapshot', marker)
                if observed != marker:
                    raise RuntimeError('Same-session SD readback mismatch')
                if digest(original) != before:
                    raise RuntimeError('QEMU modified the original instead of the staged card')
                saved = card.commit()
                reopened = transfer(binary, original, True)
                expected = marker if mode == 'persistent' else b'A' * 512
                if reopened != expected:
                    raise RuntimeError('Reopened SD readback mismatch')
                results.append({'mode': mode, 'pio_write_read': True, 'reopened_expected': True,
                                'saved': saved, 'original_untouched_while_running': True})
            finally:
                card.close()
        return {'checks': results, 'firmware_loaded': False, 'physical_media_accessed': False,
                'qemu_sha256': digest(binary), 'camera_photo_save_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = check(args.qemu)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
