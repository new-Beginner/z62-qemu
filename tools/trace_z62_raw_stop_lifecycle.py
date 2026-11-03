"""Original r61 control scenario with only the r62 RAW stop option enabled."""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import trace_z62_statistics_control_lifecycle as control
import run_z62_raw_stop_control as host

VERSION = '2026.11.03-raw-stop-lifecycle-r62'


def run(output, card, group23, qemu, duration=55):
    build = host.verify_build(qemu)
    facade = SimpleNamespace(DEFAULT_QEMU=host.DEFAULT_QEMU, verify_build=host.verify_build,
        configure_command=lambda *args, **kwargs: host.configure_command(*args, **kwargs, stop_control=True))
    sources = {str(Path(p)): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
               (__file__, control.__file__, host.__file__)}
    with patch.object(control.parent, 'host', facade):
        observed = control.run(output, card, group23, qemu, duration)
    pixels = json.loads((output/'video-isp-lifecycle.json').read_text(encoding='utf-8'))
    unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in sources.items())
    result = {'schema': 1, 'version': VERSION, 'build': build, 'source_sha256': sources,
        'sources_unchanged_during_run': unchanged,
        'completed_observation': bool(observed['completed_observation'] and unchanged),
        'process_closed': observed['process_closed'], 'raw_stop_control_enabled': True,
        'strict_mode_recovery_verified': observed['strict_mode_recovery_verified'],
        'video_new_pixels_reached_factory_lcd': pixels['video_new_pixels_reached_factory_lcd'],
        'photo_return_new_pixels_reached_factory_lcd': pixels['photo_return_new_pixels_reached_factory_lcd'],
        'final_sample': observed['final_sample'], 'sequence_gaps': observed['sequence_gaps'],
        'errors': observed['errors'], 'control_history_covers_requested_window': observed['control_history_covers_requested_window'],
        'only_new_device_option': 'nikon-z72-boot-config.z62-raw-stop-control=on',
        'model_control_semantics_changed': True, 'new_completion_injected': False,
        'guest_algorithm_changed': False, 'physical_protocol_equivalent': False, 'camera_accessed': False}
    with (output/'raw-stop-lifecycle.json').open('x', encoding='utf-8') as handle: json.dump(result, handle, indent=2)
    print(json.dumps({k: result[k] for k in ('completed_observation', 'strict_mode_recovery_verified',
        'video_new_pixels_reached_factory_lcd', 'photo_return_new_pixels_reached_factory_lcd',
        'sequence_gaps', 'errors')}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True); parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    parser.add_argument('--duration', type=float, default=55); args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x', encoding='utf-8') as log:
        with redirect_stdout(control.parent.video.lifecycle.Tee(sys.stdout, log)):
            record = run(args.output, args.card, args.group23, args.qemu.resolve(), args.duration)
    raise SystemExit(0 if record['completed_observation'] else 1)
