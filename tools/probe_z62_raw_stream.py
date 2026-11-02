# SPDX-License-Identifier: GPL-2.0-or-later
"""Firmware-free native RAW stream frame/IRQ/bounds/lifecycle checks."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import probe_z62_transaction as raw
import run_z62_raw_stream as host


@contextmanager
def session(binary, enabled=True):
    original = subprocess.Popen
    effective = []
    def launch(command, *a, **kw):
        command = host.configure_command(command, enabled)
        effective[:] = command
        return original(command, *a, **kw)
    with patch.object(subprocess, 'Popen', launch), raw.session(
            binary, enabled=False, dma=True, intercept=None) as s:
        s.command = effective
        configs = s.query('qom-list', {'path': '/machine/unattached'})
        paths = ['/machine/unattached/'+e['name'] for e in configs
                 if e['type'] == 'child<nikon-z72-boot-config>']
        s.master = next(p for p in paths if s.get('master-role', p))
        s.slave = next(p for p in paths if not s.get('master-role', p))
        s.access('irq_intercept_in '+s.get('intc', s.master))
        yield s


def read(s, address):
    return int(s.access(f'readl {address:#x}').split()[1], 16)


def frame(s, path=None, level=None):
    for value in ((1, 0) if level is None else (level,)):
        s.access(f'set_irq_in {path or s.master} raw-stream-frame 0 {value}')


def start(s):
    s.configure()
    s.write(0x20068010, 0x200)
    s.write(0x20068018, 0)
    s.write(0x20068280, 0x100)
    s.write(0x20068008, 0x200)


def get(s, name, path=None):
    return s.get('raw-stream-'+name, path or s.master)


def check(binary):
    result = {}
    with session(binary, False) as s:
        start(s)
        frame(s)
        assert get(s, 'attempts') == get(s, 'frames') == 0
        assert not get(s, 'active') and s.get('raw-accepted') == 0
        result['default_off'] = True
    with session(binary) as s:
        frame(s)
        assert get(s, 'attempts') == 0
        start(s)
        assert get(s, 'active')
        s.fill()
        frame(s, level=1)
        assert get(s, 'attempts') == get(s, 'frames') == 1
        assert get(s, 'failed') == 0
        assert read(s, 0x20068290) == 0x100
        assert 'IRQ raise 64' in s.irqs, s.irqs
        s.verify_slots(raw.raw.pattern(), guards=True)
        frame(s, level=1)
        assert get(s, 'attempts') == 1  # repeated high is no new frame
        frame(s, level=0)
        frame(s)
        assert get(s, 'blocked') == 1 and get(s, 'frames') == 1
        s.write(0x20068290, 0x100)
        assert 'IRQ lower 64' in s.irqs
        frame(s)
        assert get(s, 'frames') == 2
        s.write(0x20068290, 0x100)
        s.write(0x20068280, 0)
        s.irqs.clear()
        frame(s)
        assert get(s, 'frames') == 3 and read(s, 0x20068290) == 0x100
        assert 'IRQ raise 64' not in s.irqs
        s.write(0x20068280, 0x100)
        assert 'IRQ raise 64' in s.irqs
        s.write(0x20068290, 0x100)
        s.write(0x20068018, 0x200)
        assert not get(s, 'active')
        frame(s)
        assert get(s, 'frames') == 3
        s.write(0x20068018, 0)
        frame(s)
        assert get(s, 'frames') == 3  # clearing stop alone does not rearm
        s.write(0x20068008, 0x200)
        s.write(0x20069A08, 1)
        frame(s)
        assert get(s, 'failed') == 1 and read(s, 0x20068290) == 0
        assert get(s, 'frames') == 3
        s.configure()
        # Legacy direct RAW completion is not mislabelled as a stream frame.
        for level in (0, 1, 0):
            s.access(f'set_irq_in /machine/master-input raw-submit 0 {level}')
        assert get(s, 'frames') == 3 and get(s, 'unrelated') == 1
        assert read(s, 0x20068290) == 0
        frame(s, path=s.slave)
        assert get(s, 'attempts', s.slave) == 0
        s.query('qom-set', {'path': s.master, 'property': 'raw-stream-frames', 'value': 0}, error=True)
        s.query('system_reset')
        assert not get(s, 'active')
        assert all(get(s, p) == 0 for p in ('attempts','frames','failed','blocked','unrelated'))
        assert read(s, 0x20068290) == 0
        frame(s)
        assert get(s, 'frames') == 0
        result.update(actual_four_slot_dma=True, irq96_raise_lower=True, w1c=True,
            repeated_high=True, backpressure=True, masking=True, stop_requires_new_start=True,
            rejected_dma_no_completion=True, unrelated_completion_ignored=True,
            slave_isolation=True, readonly=True, reset=True, command=s.command)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = host.verify_build(args.qemu.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        result = {'completed': False, 'binary_sha256': manifest['binary_sha256'],
                  'firmware_loaded': False, 'guest_instructions_executed': False}
        try:
            result.update(check(args.qemu), completed=True)
        except Exception as exc:
            result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
            raise
        finally:
            json.dump(result, handle, indent=2)
    print(json.dumps(result))
