"""Native data proof for an explicit software input, never a hardware claim."""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import shutil
from unittest.mock import patch

import probe_z62_video_isp as video

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT/'.build/z62-paired-ingress-2026.11.03-r65/runtime/qemu-system-arm.exe'
preview = video.results.preview
stream = preview.stream


def require(condition, message):
    if not condition:
        raise ValueError(message)


@contextmanager
def session(binary, enabled=True):
    prior = preview.host.configure_command
    def configure(command, *args, **kwargs):
        result = prior(command, *args, **kwargs)
        result += ['-global', 'nikon-z72-input-config.scene-source=on',
                   '-global', 'nikon-z72-boot-config.z62-raw-stop-control=on']
        if enabled:
            result += ['-global', 'nikon-z72-boot-config.z62-paired-ingress=on']
        return result
    with patch.object(preview.host, 'configure_command', configure), video.session(binary) as s:
        yield s


def packet(identifier=1):
    # The existing independent oracle expects this actual packed12 ramp.
    data = ((b'\xff'*2271+b'\x00')*1006 if identifier == 2 else stream.raw.raw.pattern())
    return (struct.pack('<4sIQQQQIIII', b'Z62S', 1, 0x65, identifier, 3, 100_000_000,
                        1514, 1006, 2272, len(data)) + hashlib.sha256(data).digest() + data)


def upload(s, identifier=1):
    s.query('qom-set', {'path': '/machine/master-input', 'property': 'scene-packet',
                       'value': base64.b64encode(packet(identifier)).decode('ascii')})


def get(s, name, path=None):
    return s.get('paired-ingress-'+name, path or s.master)


def configure(s):
    video.configure_video(s)
    s.write(0x20380010, 1)
    s.write(0x2006800c, 0x200)
    require(not stream.get(s, 'active'), 'Old RAW source did not remain stopped')
    video.fill_guards(s)
    # The first slot starts at the RAM pool boundary. Reuse the qualified
    # fixture: suffix guards for all slots, predecessor guards for slots 1..3.
    s.fill()


def check(binary):
    available = subprocess.run([str(binary), '-device', 'nikon-z72-boot-config,help'],
                               capture_output=True, text=True, timeout=20)
    require(available.returncode == 0 and 'z62-paired-ingress' in available.stdout+available.stderr,
            'Missing independent paired software input property')
    import run_z62_paired_ingress as host
    build = host.verify_build(binary)
    proof = {'default_off': False, 'physical_protocol_equivalent': False,
             'firmware_executed': False, 'camera_accessed': False,
             'build_identity_verified': build['binary_sha256']}
    with session(binary, False) as s:
        configure(s); upload(s); preview.advance(s)
        require(get(s, 'frames') == 0 and video.get(s, 'batches') == 0,
                'Default-off configuration produced data')
        proof['default_off'] = True
    with session(binary) as s:
        configure(s); preview.advance(s)
        require(get(s, 'frames') == 0 and video.get(s, 'batches') == 0,
                'Missing external scene manufactured pixels')
        video.guards(s, unchanged=True, full=True)
        upload(s); preview.advance(s)
        require(get(s, 'frames') == 1 and get(s, 'bytes') == 4*stream.raw.raw.SIZE,
                'New input did not DMA exactly one owned four-slot cohort')
        require(stream.get(s, 'frames') == 0 and not stream.get(s, 'active') and
                s.get('raw-accepted') == 0 and preview.read(s, 0x20068290) == 0,
                'Software paired input restarted or completed the old RAW port')
        expected = packet()[88:]
        s.verify_slots(expected, guards=True)
        require(video.get(s, 'batches') == 1, 'Fresh source did not reach actual video DMA')
        video.pixels(s)
        require(s.get('scene-used-publish-id') == 1 and get(s, 'publish-id') == 1,
                'Source acknowledgement does not match actual DMA')
        preview.advance(s)
        require(get(s, 'frames') == 1 and video.get(s, 'batches') == 1,
                'Pending output was overwritten')
        proof.update(actual_source_bytes=True, actual_main_work_preview_oracle=True,
                     raw_port_remained_stopped=True, source_tags_verified=True, backpressure=True,
                     command=s.command)
        s.write(0x20102608, 0)
        video.results.acknowledge(s); upload(s, 2); preview.advance(s)
        require(get(s, 'frames') == 1 and video.get(s, 'batches') == 1,
                'Cleared request continued producing data')
        s.write(0x20102608, 3); preview.advance(s)
        require(get(s, 'frames') == 1, 'Reconfiguring flags silently rearmed the software source')
        s.write(0x20380008, 1); preview.advance(s)
        require(get(s, 'frames') == 2 and video.get(s, 'batches') == 2 and get(s, 'publish-id') == 2,
                'Explicit new paired request did not consume the new scene')
        s.verify_slots(packet(2)[88:], guards=True)
        for row in video.geometry():
            require(s.read(row['main'], 32) == b'\xeb'*32 and
                    s.read(row['main']+video.MAIN_Y, 32) == b'\x80'*32,
                    'Changed white source did not change MAIN pixels')
            require(s.read(row['work'], 32) == b'\xff\x0f'*16 and
                    s.read(row['work']+video.WORK_BYTES, 32) == bytes(32),
                    'Changed white source did not change WORK pixels')
            for address, _, _, _, uv in row['preview']:
                require(s.read(address, 32) == b'\xeb'*32 and s.read(address+uv, 32) == b'\x80'*32,
                        'Changed white source did not reach preview output')
        proof['second_distinct_scene_raw_main_work_preview_verified'] = True
        require(get(s, 'frames', s.slave) == 0, 'Paired source leaked into slave address space')
        proof.update(stop=True, explicit_paired_restart=True, slave_isolation=True)
        s.query('system_reset')
        require(get(s, 'frames') == 0 and not get(s, 'active'), 'Reset retained software source work')
        proof['reset'] = True
    with session(binary) as s:
        configure(s); upload(s)
        sources = [preview.read(s, 0x20380310+i*4) for i in range(4)]
        # A late invalid destination must reject before *any* RAW/output write.
        s.write(0x2038031c, 0x20100000); preview.advance(s)
        require(get(s, 'frames') == 0 and get(s, 'reason') == 'address',
                'Late MMIO source address was accepted')
        for address in stream.raw.raw.SLOTS:
            require(s.read(address, stream.raw.raw.SIZE) == b'\xa5'*stream.raw.raw.SIZE,
                    'Rejected source partially overwrote an earlier RAW slot')
        video.guards(s, unchanged=True, full=True)
        s.write(0x2038031c, sources[0]); preview.advance(s)
        require(get(s, 'frames') == 0 and get(s, 'reason') == 'alias',
                'Aliased RAW slots were accepted')
        s.write(0x2038031c, sources[3])
        s.write(0x20068008, 0x200); preview.advance(s)
        require(stream.get(s, 'active') and get(s, 'frames') == 0 and
                get(s, 'reason') == 'legacy-raw-active', 'Software source competed with old RAW')
        preview.new_raw(s); preview.advance(s)
        require(stream.get(s, 'frames') == 1 and get(s, 'frames') == 0 and
                video.get(s, 'batches') == 1, 'Enabled software option broke the active legacy source')
        video.pixels(s)
        proof.update(late_invalid_no_partial_dma=True, alias_rejected=True,
                     active_legacy_raw_excludes_software_source=True, legacy_actual_dma_with_option_on=True)
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, default=DEFAULT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Native evidence is immutable')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = {'schema': 1, 'completed': False, 'qemu_sha256': hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
              'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    logs = args.output.with_name(args.output.stem+'-logs')
    logs.mkdir(exist_ok=False)
    launches = []
    native = subprocess.Popen
    class RecordedPopen(native):
        def __init__(self, command, *a, **kw):
            self.record = None
            if '-M' in command and Path(command[0]).name.lower() == 'qemu-system-arm.exe':
                self.record = {'command': list(command), 'console': getattr(kw.get('stderr'), 'name', None)}
                launches.append(self.record)
            super().__init__(command, *a, **kw)
        def wait(self, *a, **kw):
            code = super().wait(*a, **kw)
            if self.record is not None and not self.record.get('archived'):
                self.record.update(exit_code=code, process_closed=self.poll() is not None)
                console = self.record['console']
                if console and Path(console).is_file():
                    destination = logs/(str(launches.index(self.record))+'.log')
                    shutil.copyfile(console, destination)
                    self.record.update(log=str(destination), log_sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
                self.record['archived'] = True
            return code
    try:
        with patch.object(subprocess, 'Popen', RecordedPopen):
            result.update(check(args.qemu.resolve()), completed=True)
    except Exception as exc:
        result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    result['launches'] = launches
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result), flush=True)
    raise SystemExit(0 if result['completed'] else 1)
