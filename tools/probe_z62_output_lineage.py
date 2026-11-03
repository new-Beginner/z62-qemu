"""Read-only output provenance must follow actual ISP DMA, never just RAW use."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess
from unittest.mock import patch
import probe_z62_paired_ingress as native

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT/'.build/z62-output-lineage-2026.11.03-r69/runtime/qemu-system-arm.exe'


def require(value, message):
    if not value:
        raise ValueError(message)


@contextmanager
def session(binary, enabled=True):
    prior = native.preview.host.configure_command
    def configure(command, *args, **kwargs):
        result = prior(command, *args, **kwargs)
        if enabled:
            result += ['-global', 'nikon-z72-boot-config.z62-output-lineage=on']
        return result
    with patch.object(native.preview.host, 'configure_command', configure), native.session(binary) as s:
        yield s


def lineage(s):
    return json.loads(s.get('paired-output-lineage', s.master))


def check(binary):
    available = subprocess.run([str(binary), '-device', 'nikon-z72-boot-config,help'],
                              capture_output=True, text=True, timeout=20)
    require(available.returncode == 0 and 'z62-output-lineage' in available.stdout+available.stderr,
            'Missing read-only committed-output lineage feature')
    import run_z62_output_lineage as host
    build = host.verify_build(binary)
    proof = {'qemu_sha256': build['binary_sha256'], 'guest_firmware_executed': False,
             'camera_accessed': False, 'physical_protocol_equivalent': False}
    with session(binary, False) as s:
        native.configure(s); native.upload(s); native.preview.advance(s)
        require(native.video.get(s, 'batches') == 1, 'Default-off observer changed actual ISP work')
        require(lineage(s)['enabled'] is False and lineage(s)['valid'] is False,
                'Default-off observer claimed provenance')
        proof['default_off_preserves_data'] = True
    with session(binary) as s:
        native.configure(s); native.upload(s)
        require(lineage(s)['valid'] is False and lineage(s)['commits'] == 0,
                'Publishing a scene forged committed output')
        native.preview.advance(s); row = lineage(s)
        require(row['valid'] is True and row['mode'] == 'video' and row['commits'] == 1 and
                row['source'] == 'software-paired' and row['publish_id'] == 1 and
                row['epoch'] == 0x65 and row['frame_id'] == 3 and row['time_ns'] == 100_000_000,
                'Actual video output has no matching immutable source tags')
        native.video.pixels(s)
        original = dict(row)
        native.upload(s, 2); native.preview.advance(s)
        require(lineage(s) == original, 'Pending output provenance was overwritten by a new publication')
        native.video.results.acknowledge(s); native.preview.advance(s)
        row = lineage(s)
        require(row['valid'] and row['publish_id'] == 2 and row['commits'] == 2,
                'Acknowledged new scene did not reach the committed record')
        s.write(0x20102600, 0x305)
        require(lineage(s)['mode'] == 'video', 'Current config was mistaken for the last committed mode')
        s.query('qom-set', {'path': s.master, 'property': 'paired-output-lineage', 'value': '{}'}, error=True)
        s.query('system_reset')
        require(lineage(s)['valid'] is False and lineage(s)['commits'] == 0, 'Reset retained committed provenance')
        proof.update(actual_video_provenance=True, publication_not_completion=True,
                     backpressure_preserves_record=True, mode_is_commit_mode=True, readonly=True, reset=True)
    with session(binary) as s:
        native.configure(s); native.upload(s)
        s.write(0x203804a8, 0x1234)
        native.preview.advance(s)
        require(native.get(s, 'frames') > 0 and native.video.get(s, 'batches') == 0 and
                lineage(s)['valid'] is False and lineage(s)['commits'] == 0,
                'Successful RAW followed by rejected ISP became a committed output')
        proof['rejected_isp_has_no_committed_tags'] = True
    with session(binary) as s:
        native.configure(s); native.upload(s)
        s.write(0x20068008, 0x200); native.preview.new_raw(s); native.preview.advance(s)
        row = lineage(s)
        require(row['valid'] is True and row['source'] == 'legacy-raw-stream' and
                row['publish_id'] == 1 and native.stream.get(s, 'frames') == 1,
                'Legacy actual RAW output lineage differs')
        native.video.pixels(s)
        proof['legacy_stream_provenance'] = True
    with session(binary) as s:
        native.preview.configure(s); native.video.results.configure_units(s)
        s.write(0x20100010, 0x61); s.write(0x20380010, 1); s.write(0x2006800c, 0x200)
        native.preview.fill_guards(s); s.fill(); native.upload(s); native.preview.advance(s)
        row = lineage(s)
        require(row['valid'] is True and row['mode'] == 'photo' and row['publish_id'] == 1 and
                row['source'] == 'software-paired', 'Actual photo output has no source provenance')
        native.video.results.pixels_and_guards(s)
        proof['actual_photo_provenance'] = True
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, default=DEFAULT); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Native lineage evidence is immutable')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = {'schema': 1, 'completed': False, 'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        result.update(check(args.qemu.resolve()), completed=True)
    except Exception as exc:
        result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result), flush=True)
    raise SystemExit(0 if result['completed'] else 1)
