# SPDX-License-Identifier: GPL-2.0-or-later
"""Original Z62 capture setup chronology on verified r6/r7 baselines.

Records raw control/descriptor setters and the first forwarded frame phases.
No MENU or software/firmware patches. Optional diagnostic device events are
explicit, data-linked and recorded separately from passive observations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import run_z62_capcom as host
import trace_z62_upper_waits as trace

POINTS = {
    0x1020AB20: 'input-submit-word',
    0x1020AB28: 'input-control-word',
    0x1020AAFC: 'input-enable-word',
    0x102090A0: 'raw-format-descriptor',
    0x10239734: 'raw-buffer-descriptor',
    0x102D7EEC: 'first-frame-start-forward',
    0x102D7F0E: 'first-frame-end-forward',
}
STATE = {
    0xC269FA0C: 8, 0xC1888084: 1, 0xC1868490: 8, 0xC26A0AC4: 18,
    0x20068200: 1, 0x20068210: 1, 0x20068260: 1, 0x20068270: 1,
    0x20068280: 1, 0x20068290: 1, 0x2006A580: 1,
}
IRQ_CALLBACKS = (0x1020A472, 0x1020A480, 0x1020A490, 0x1020A49E,
                 0x1020A4AC, 0x1020A4BA, 0x1020A4C8, 0x1020A4D6,
                 0x1020A4E4, 0x1020A4F2)
WAIT_CALLS = (0x102386DE, 0x10238804, 0x1023C276)
LIFECYCLE_POINTS = {
    0x10239734: 'raw-buffer-descriptor',
    0x102383D4: 'prepare-channel-drain', 0x102384CA: 'stop-selected-channels',
    0x10239148: 'raw-drain-callback', 0x102392D6: 'statistics-drain-callback',
    0x10239288: 'engine20-drain-callback', 0x10239368: 'engine1-drain-callback',
    0x1023933E: 'engine2-drain-callback',
    0x10238BF0: 'upper-drain-041a0006', 0x10238C2E: 'upper-drain-041a0004',
    0x1023C4FC: 'common-end-consumer',
    0x1020AE7C: 'stop-command-submit', 0x1020C462: 'engine1-stop-submit',
    0x1020C3E2: 'paired-channel-stop-submit',
}
FRAME_OBJECT_POINTS = {
    0x10239734: 'raw-buffer-descriptor',
    0x1022F17A: 'capture-source-callback', 0x1022E15C: 'capture-result-callback',
    0x1023123E: 'capture-frame-worker', 0x10238A80: 'metadata-consumer',
    0x1022F25A: 'capture-frame-object-return', 0x1023AD0C: 'input-parameter-submit',
}
OWNERSHIP_POINTS = {
    0x10239734: 'raw-buffer-descriptor', 0x1022F25A: 'capture-frame-object-return',
    0x1022D864: 'frame-acquire-mask', 0x1022DF2A: 'frame-release-mask',
    0x1022DFD0: 'frame-release-stored', 0x1023594E: 'frame-processing-submit',
    0x10238A80: 'metadata-consumer', 0x1022E474: 'metadata-release-call',
}


def _raw_backed_event_diagnostic(machine, lines):
    """Supply a bounded IRQ route experiment, never claim statistic completion.

    The caller holds machine.io. No guest/software writes occur here. The whole
    set deliberately contains unmodeled engine results; keep it out of launchers.
    """
    from probe_z62_liveview import master_event_path, qtest_read, expected_raw_prefix
    path = master_event_path(machine)
    frames = machine.qmp.command('qom-get', {'path': path, 'property': 'raw-stream-frames'})
    if not isinstance(frames, int) or isinstance(frames, bool) or frames <= 0:
        return None
    masks = {bank: machine._words(0x20068200 + bank*0x20, 1)[0]
             for bank in sorted({irq//32 for irq in lines})}
    if any(not masks[irq//32] & (1 << (irq%32)) for irq in lines):
        return None
    data = qtest_read(machine, 0x82C00000, 32)
    if data != expected_raw_prefix():
        raise ValueError('RAW readback mismatch before ready event')
    for irq in lines:
        for level in (1, 0):
            machine._qtest(f'set_irq_in {path} input-event {irq} {level}')
    return {'lines': list(lines),
            'diagnostic_only': True, 'statistics_data_verified': False,
            'native_raw_batches': frames, 'raw_prefix': data.hex(),
            'observed_masks': {str(k): hex(v) for k, v in masks.items()}}


def ready_route_diagnostic(machine, *, entire_set=False):
    result = _raw_backed_event_diagnostic(machine, (3, 4, 96, 101, 135) if entire_set else (135,))
    return dict(result, ready_event_supplied=True, line=135) if result else None


def metadata_route_diagnostic(machine):
    control = machine._words(0x20069F00, 1)[0]
    if control & 0x11 != 0x11:
        return None
    result = _raw_backed_event_diagnostic(machine, (6,))
    return dict(result, metadata_event_supplied=True, control=hex(control)) if result else None


def run(args, *, extra_hit_hook=None, extra_observation_hook=None):
    if args.output.exists():
        raise FileExistsError('Existing trace evidence is protected')
    if args.native_source:
        import run_z62_raw_stream as native
        manifest = native.verify_build(args.qemu.resolve())
    else:
        manifest = host.verify_build(args.qemu.resolve())
    original = (trace.R1_SHA, dict(trace.POINTS), set(trace.POINT_ONCE),
                dict(trace.EXTRA_WORDS), trace.stage, trace.install_native_process_adapter,
                subprocess.Popen, list(sys.path))
    old_stage, old_install = trace.stage, trace.install_native_process_adapter
    def stage(*a, **kw):
        work, record = old_stage(*a, **kw)
        host.host.apply_console(work/'source')
        record.update(capcom_device=manifest, capture_setup_trace='0.2.0',
                      capture_trace_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      capcom_sync=True, functional_raw=True, raw_completion=True,
                      frame_start_phase=args.frame_start,
                      raw_boundary_experiment=args.boundary_experiment,
                      raw_boundary_line=args.boundary_line,
                      native_raw_stream=args.native_source, input_drain=args.input_drain,
                      startup_waits=args.startup_waits, ready_bit_experiment=args.ready_bit_experiment,
                      lifecycle_trace=args.lifecycle, ready_set_experiment=args.ready_set_experiment,
                      frame_objects_trace=args.frame_objects, metadata_event_experiment=args.metadata_event_experiment,
                      ownership_trace=args.ownership)
        return work, record
    def install(work):
        previous = old_install(work)
        parent = subprocess.Popen
        class CapturePopen(parent):
            def __init__(self, command, *a, **kw):
                if isinstance(command, (list, tuple)) and 'qemu-system-arm' in str(command[0]):
                    command = host.configure_command(host.host.configure_command(command, True, True), True)
                    if args.native_source:
                        command = native.configure_command(command, True, drain=args.input_drain)
                    if args.frame_start:
                        command += ['-global', 'nikon-z72-boot-config.frame-start=on']
                super().__init__(command, *a, **kw)
        subprocess.Popen = CapturePopen
        return previous
    trace.R1_SHA = manifest['binary_sha256']
    trace.POINTS.clear()
    trace.POINTS.update(POINTS)
    if args.lifecycle:
        trace.POINTS.clear()
        trace.POINTS.update(LIFECYCLE_POINTS)
        trace.POINT_ONCE.add(0x10239734)
        trace.EXTRA_WORDS.update({0xC269F9F4: 12, 0xC1888080: 20,
                                 0x20068008: 5, 0x20068060: 1,
                                 0x20068200: 64})
    if args.frame_objects:
        trace.POINTS.clear()
        trace.POINTS.update(FRAME_OBJECT_POINTS)
        trace.POINT_ONCE.add(0x10239734)
        trace.EXTRA_WORDS.update({0xC1887CB0: 48, 0xC25DACE4: 32,
                                 0xC269FA44: 40, 0xC1888080: 20})
    if args.ownership:
        trace.POINTS.clear()
        trace.POINTS.update(OWNERSHIP_POINTS)
        trace.POINT_ONCE.add(0x10239734)
        trace.EXTRA_WORDS.update({0xC1887CB0: 48, 0xC25DACE4: 32,
                                 0xC269FA44: 40, 0xC1888080: 20})
    if args.startup_waits:
        for pc in (0x1020AB20, 0x1020AB28, 0x1020AAFC):
            trace.POINTS.pop(pc, None)
        trace.POINTS.update({pc: 'wait-call' for pc in WAIT_CALLS})
        trace.POINTS.update({pc+4: 'wait-return' for pc in WAIT_CALLS})
        trace.EXTRA_WORDS.update({0xC269F9C8: 18, 0xC1888080: 16})
    if args.boundary_experiment:
        trace.POINTS.update({0x1020A8FA: 'input-IRQ96', 0x1020A454: 'input-dispatch',
                             0x1020A462: 'input-domain-mask'})
        trace.POINTS.update({pc: 'input-indirect-callback' for pc in IRQ_CALLBACKS})
        trace.POINTS.update({0x10239184: 'channel2-completion-bit',
                            0x10238B8A: 'input-worker',
                            0x1023831E: 'input-descriptor-consumer',
                            0x1023C38A: 'other-mode-consumer'})
        trace.EXTRA_WORDS.update({0xC269F9C8: 18})
    trace.POINT_ONCE.update((0x102D7EEC, 0x102D7F0E))
    trace.EXTRA_WORDS.update(STATE)
    trace.stage, trace.install_native_process_adapter = stage, install
    result = None
    injected = False
    def observe(machine, row):
        nonlocal injected
        if extra_observation_hook is not None:
            observation = extra_observation_hook(machine, row)
            if observation is not None:
                return observation
        if args.metadata_event_experiment and not injected:
            with machine.io:
                experiment = metadata_route_diagnostic(machine)
                if experiment:
                    injected = True
                    return dict(experiment, virtual_seconds_before=row['virtual_seconds'])
        if (args.ready_bit_experiment or args.ready_set_experiment) and not injected:
            with machine.io:
                experiment = ready_route_diagnostic(machine, entire_set=args.ready_set_experiment)
                if experiment:
                    injected = True
                    return dict(experiment, virtual_seconds_before=row['virtual_seconds'])
        if not args.boundary_experiment or injected or row['virtual_seconds'] < 2.5:
            return None
        from probe_z62_liveview import raw_boundary_transaction
        with machine.io:
            item = raw_boundary_transaction(machine, args.boundary_line)
        item['virtual_seconds_before'] = row['virtual_seconds']
        injected = True
        return item
    def observe_hit(remote, registers):
        if extra_hit_hook is not None:
            return extra_hit_hook(remote, registers)
        if args.ownership and registers['pc'] in OWNERSHIP_POINTS and registers['pc'] not in (0x10239734, 0x10238A80):
            pointer = registers['r4'] if registers['pc'] == 0x1022DFD0 else registers['r0']
            if 0xC0000000 <= pointer < 0xD0000000:
                data = remote.read(pointer, 0x154)
                context = int.from_bytes(data[0x144:0x148], 'little')
                result = {'frame_object': hex(pointer), 'header_64': data[:64].hex(),
                          'context': hex(context), 'pending_mask': hex(int.from_bytes(data[0x14c:0x150], 'little'))}
                if 0xC0000000 <= context < 0xD0000000:
                    result['context_64'] = remote.read(context, 64).hex()
                return result
        if registers['pc'] in (0x1022F17A, 0x1022E15C) and 0xC0000000 <= registers['r1'] < 0xD0000000:
            return {'callback_payload_64': remote.read(registers['r1'], 64).hex()}
        if registers['pc'] == 0x1022F25A and 0xC0000000 <= registers['r0'] < 0xD0000000:
            return {'frame_object_64': remote.read(registers['r0'], 64).hex()}
        if registers['pc'] == 0x1020A454 or registers['pc'] in IRQ_CALLBACKS:
            return {'masked_status_array': remote.read(registers['r1'], 32).hex()}
        if registers['pc'] == 0x102090A0:
            return {'format_descriptor': remote.read(registers['r1'], 28).hex()}
        return {}
    try:
        result = trace.run(args, observation_hook=observe, hit_hook=observe_hit)
        result['capture_setup_observed'] = bool(result.get('live_anchors_verified') and
            result.get('process_closed') and result.get('detach') == 'OK' and
            not result.get('failure') and not result.get('cleanup_error') and
            any(h['label'] == 'raw-buffer-descriptor' for h in result['hits']))
        if args.boundary_experiment:
            result['capture_setup_observed'] &= any(
                e.get('boundary_supplied') for e in result.get('device_experiments', []))
        if args.ready_bit_experiment or args.ready_set_experiment:
            result['capture_setup_observed'] &= any(
                e.get('ready_event_supplied') for e in result.get('device_experiments', []))
        if args.metadata_event_experiment:
            result['capture_setup_observed'] &= any(
                e.get('metadata_event_supplied') for e in result.get('device_experiments', []))
        (args.output/'trace.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        return result
    finally:
        trace.R1_SHA, points, once, state, trace.stage, trace.install_native_process_adapter, \
            subprocess.Popen, old_path = original
        trace.POINTS.clear()
        trace.POINTS.update(points)
        trace.POINT_ONCE.clear()
        trace.POINT_ONCE.update(once)
        trace.EXTRA_WORDS.clear()
        trace.EXTRA_WORDS.update(state)
        sys.path[:] = old_path


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qemu', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--frame-start', action='store_true')
    p.add_argument('--boundary-experiment', action='store_true',
                   help='One verified actual RAW write plus a decoded completion for route tracing')
    p.add_argument('--boundary-line', type=int, choices=(103,136), default=103)
    p.add_argument('--native-source', action='store_true')
    p.add_argument('--input-drain', action='store_true')
    p.add_argument('--startup-waits', action='store_true')
    p.add_argument('--ready-bit-experiment', action='store_true')
    p.add_argument('--ready-set-experiment', action='store_true',
                   help='DIAGNOSTIC ONLY: entire ready mask; statistics processing is not modeled')
    p.add_argument('--lifecycle', action='store_true', help='Trace stop/drain paths without per-frame stops')
    p.add_argument('--frame-objects', action='store_true', help='Trace original frame object producer/consumer')
    p.add_argument('--ownership', action='store_true', help='Trace original frame object ownership masks and processing submit')
    p.add_argument('--metadata-event-experiment', action='store_true',
                   help='DIAGNOSTIC ONLY: one metadata IRQ after native RAW, no statistics validity claim')
    p.add_argument('--menu-at', type=float, default=1000)
    p.add_argument('--virtual-limit', type=float, default=4)
    p.add_argument('--wall-limit', type=float, default=300)
    args = p.parse_args()
    if args.qemu is None:
        if args.native_source:
            from run_z62_raw_stream import DEFAULT_QEMU
            args.qemu = DEFAULT_QEMU
        else:
            args.qemu = host.DEFAULT_QEMU
    if args.native_source and args.boundary_experiment:
        p.error('Native source trace cannot also inject RAW transactions')
    if (args.ready_bit_experiment or args.ready_set_experiment or args.metadata_event_experiment) and not args.native_source:
        p.error('Ready-event diagnostic requires actual native RAW source')
    if sum((args.ready_bit_experiment, args.ready_set_experiment, args.metadata_event_experiment)) > 1:
        p.error('Select one event-route experiment')
    if not 2 <= args.virtual_limit <= 60 or not 30 <= args.wall_limit <= 900 or args.menu_at < 3:
        p.error('virtual-limit 2..60, wall-limit 30..900, menu-at >=3 required')
    args.poll, args.max_stops = 2, (1000 if args.startup_waits or args.lifecycle else 200)
    result = run(args)
    print(json.dumps({'capture_setup_observed': result['capture_setup_observed'],
                      'hits': len(result['hits']), 'stop_reason': result.get('stop_reason')}))
    raise SystemExit(0 if result['capture_setup_observed'] else 1)
