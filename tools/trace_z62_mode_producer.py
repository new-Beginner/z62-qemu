# SPDX-License-Identifier: GPL-2.0-or-later
"""Trace the original C1.70 mode-request producer on verified r5 hardware.

Extends the prior read-only trace with the immediate-notification predicate,
lower request dispatch, indirect callback and callback return. Does not write
guest instructions, software flags or return values. Breakpoints affect timing.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import run_z62_transaction as host
import trace_z62_upper_waits as trace


POINTS = {
    0x10397EAC: 'immediate-notification-predicate',
    0x10397EB2: 'immediate-notification-producer',
    0x1026E9A6: 'lower-mode-request',
    0x1026E9AC: 'lower-mode-request-return',
    0x102EC834: 'lower-mode-state-update',
    0x10241E80: 'mode-callback-dispatch',
    0x10241E88: 'mode-callback-target',
    0x10241E8A: 'mode-callback-return',
    0x102DD964: 'sensor-mode2-request',
}
ASYNC_POINTS = {
    0x10241C8C: 'mode-event-dispatch',
    0x10241CDE: 'async-notification-producer',
    0x10241D66: 'mode-low-event',
    0x102420A0: 'mode-ack-callback',
    0x102420EE: 'mode-done-callback-target',
    0x102420D8: 'mode-done-callback-send',
    0x102EC8AC: 'lower-state-branch',
    0x102EBD08: 'lower-substate-branch',
    0x10241ED8: 'mode-pulse-timer',
}


def run(args):
    if args.output.exists():
        raise FileExistsError('Existing evidence is immutable')
    build = host.verify_build(args.qemu.resolve())
    capcom_enabled = getattr(args, 'capcom_sync', False)
    capcom_manifest = None
    if capcom_enabled:
        import run_z62_capcom as capcom
        capcom_manifest = capcom.verify_build(args.qemu.resolve())
    saved = (trace.R1_SHA, dict(trace.POINTS), trace.stage,
             trace.install_native_process_adapter, subprocess.Popen, list(sys.path),
             dict(trace.EXTRA_WORDS), set(trace.NOTIFICATIONS))
    old_stage, old_install = trace.stage, trace.install_native_process_adapter
    def stage(*a, **kw):
        work, record = old_stage(*a, **kw)
        host.apply_console(work / 'source')
        record.update(producer_trace_version='0.2.0', host_version=host.VERSION,
                      async_observations=getattr(args, 'async_path', False),
                      capcom_sync=capcom_enabled, capcom_device=capcom_manifest,
                      transaction_device=build, functional_raw=True, raw_completion=True)
        return work, record
    def install(work):
        previous = old_install(work)
        parent = subprocess.Popen
        class ProducerPopen(parent):
            def __init__(self, command, *a, **kw):
                if isinstance(command, (list, tuple)) and 'qemu-system-arm' in str(command[0]):
                    command = host.configure_command(command, True, True)
                    if capcom_enabled:
                        command = capcom.configure_command(command, True)
                super().__init__(command, *a, **kw)
        subprocess.Popen = ProducerPopen
        return previous
    trace.R1_SHA = build['binary_sha256']
    trace.POINTS.update(POINTS)
    if getattr(args, 'async_path', False):
        trace.POINTS.update(ASYNC_POINTS)
        trace.EXTRA_WORDS.update({0xC18A790C: 20, 0xC18685A8: 24, 0xC2B2352C: 36})
        # Handles observed in r5-async-run1, read-only; retain their addresses
        # alongside parent state so allocation changes cannot go unnoticed.
        trace.EXTRA_WORDS.update({0xC1803AB4: 14, 0xC18036FC: 14})
        trace.NOTIFICATIONS.update(range(0x03030001, 0x03030026))
    trace.stage, trace.install_native_process_adapter = stage, install
    try:
        return trace.run(args)
    finally:
        trace.R1_SHA, original_points, trace.stage, trace.install_native_process_adapter, \
            subprocess.Popen, old_path, extra_words, notifications = saved
        trace.POINTS.clear()
        trace.POINTS.update(original_points)
        trace.EXTRA_WORDS.clear()
        trace.EXTRA_WORDS.update(extra_words)
        trace.NOTIFICATIONS.clear()
        trace.NOTIFICATIONS.update(notifications)
        sys.path[:] = old_path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--qemu', type=Path)
    p.add_argument('--menu-at', type=float, default=3)
    p.add_argument('--poll', type=float, default=2)
    p.add_argument('--wall-limit', type=float, default=900)
    p.add_argument('--virtual-limit', type=float, default=45)
    p.add_argument('--max-stops', type=int, default=2000)
    p.add_argument('--async-path', action='store_true')
    p.add_argument('--capcom-sync', action='store_true')
    args = p.parse_args()
    if args.qemu is None:
        if args.capcom_sync:
            from run_z62_capcom import DEFAULT_QEMU
            args.qemu = DEFAULT_QEMU
        else:
            args.qemu = host.DEFAULT_QEMU
    if min(args.poll, args.wall_limit, args.virtual_limit, args.max_stops) <= 0 or args.menu_at < 3:
        p.error('positive limits and menu-at >=3 required')
    result = run(args)
    print(json.dumps(result['summary']), flush=True)
    raise SystemExit(0 if trace.trace_complete(result) else 1)


if __name__ == '__main__':
    main()
