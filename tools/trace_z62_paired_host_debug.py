"""r66 scenario with the proven owned-process timeout capture; no model change."""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import trace_z62_raw_stop_host_debug as diagnostic
import trace_z62_paired_handoff_lifecycle as paired
import run_z62_paired_handoff as host

VERSION = '2026.11.03-paired-host-diagnostic-r68'


def run(output, card, group23, qemu, gdb, duration=55):
    build = host.verify_build(qemu)
    sources = {str(Path(p)): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
               (__file__, diagnostic.__file__, paired.__file__, host.__file__,
                Path(__file__).with_name('read_z62_owned_host.ps1'))}
    with patch.object(diagnostic, 'parent', paired):
        observed = diagnostic.run(output, card, group23, qemu, gdb, duration)
    unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == value for p, value in sources.items())
    result = {**observed, 'version': VERSION, 'build': build,
        'inherited_host_record_sha256': hashlib.sha256((output/'host-timeout-lifecycle.json').read_bytes()).hexdigest(),
        'inherited_model_record_sha256': hashlib.sha256((output/'paired-handoff-lifecycle.json').read_bytes()).hexdigest(),
        'source_sha256': {**observed['source_sha256'], **sources},
        'sources_unchanged_during_run': observed['sources_unchanged_during_run'] and unchanged,
        'completed_observation': observed['completed_observation'] and unchanged,
        'functional_acceptance_eligible': observed['functional_acceptance_eligible'] and unchanged,
        'hardware_or_guest_control_changed_by_diagnostic': False}
    with (output/'paired-host-lifecycle.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({key: result[key] for key in ('completed_observation', 'functional_acceptance_eligible',
        'host_debugger_attached', 'strict_mode_recovery_verified', 'host_capture_errors')}, indent=2), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--group23', type=Path, required=True)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    parser.add_argument('--gdb', type=Path, default=diagnostic.host_capture.DEFAULT_GDB)
    parser.add_argument('--duration', type=float, default=55)
    args = parser.parse_args()
    if not 55 <= args.duration <= 90:
        parser.error('Full scenario needs 55..90 seconds')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x', encoding='utf-8') as log:
        with redirect_stdout(paired.parent.control.parent.video.lifecycle.Tee(sys.stdout, log)):
            result = run(args.output, args.card, args.group23, args.qemu.resolve(), args.gdb.resolve(), args.duration)
    raise SystemExit(0 if result['completed_observation'] else 1)
