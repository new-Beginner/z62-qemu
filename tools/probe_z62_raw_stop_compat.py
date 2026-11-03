"""Real existing statistics/video suites with the r62 stop option enabled."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import probe_z62_continuous_stats as stats
import probe_z62_video_isp as video
from probe_z62_raw_stop_control import stop_option
import run_z62_raw_stop_control as host


def check(binary):
    build = host.verify_build(binary)
    with stop_option():
        statistics = stats.check(binary)
        with patch.object(video, 'host', host):
            previews = video.check(binary)
    command = previews['command']
    if 'nikon-z72-boot-config.z62-raw-stop-control=on' not in command:
        raise ValueError('Video native command lost explicit RAW stop opt-in')
    return {'schema': 1, 'completed': True, 'qemu_sha256': build['binary_sha256'],
            'stop_option_requested': True, 'video_command_has_stop_option': True,
            'statistics': statistics, 'video': previews, 'guest_firmware_executed': False,
            'camera_accessed': False, 'whole_mode_recovery_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError('Existing native evidence is immutable')
    try: record = check(args.qemu.resolve())
    except Exception as exc: record = {'schema': 1, 'completed': False, 'failure': {'type': type(exc).__name__, 'message': str(exc)}}
    with args.output.open('x', encoding='utf-8') as handle: json.dump(record, handle, indent=2)
    print(json.dumps({'completed': record['completed'], 'failure': record.get('failure')}), flush=True)
    raise SystemExit(0 if record['completed'] else 1)
