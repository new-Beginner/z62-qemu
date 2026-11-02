# SPDX-License-Identifier: GPL-2.0-or-later
"""Native no-firmware CAPCOM GPIO, timer, interrupt and reset checks."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

import probe_z62_transaction as base
import z62_capcom_device as device


@contextmanager
def session(binary, enabled=True):
    original = subprocess.Popen
    effective = []
    def launch(command, *a, **kw):
        command = list(command)
        if enabled:
            command += ['-global', 'nikon-z72-boot-config.z62-capcom-sync=on']
        # Synthetic ARM loops advance virtual time without camera software.
        command += ['-device', 'loader,addr=0x10020000,data=0xeafffffe,data-len=4']
        for cpu in range(4):
            command += ['-device', f'loader,addr=0x10020000,cpu-num={cpu}']
        effective[:] = command
        return original(command, *a, **kw)
    with patch.object(subprocess, 'Popen', launch), base.session(
            binary, enabled=False, dma=False, intercept=None) as s:
        s.command = effective
        paths = ['/machine/unattached/' + item['name'] for item in
                 s.query('qom-list', {'path': '/machine/unattached'})
                 if item['type'] == 'child<nikon-z72-boot-config>']
        s.master = next(p for p in paths if s.get('master-role', p))
        s.slave = next(p for p in paths if not s.get('master-role', p))
        gic = s.get('intc', s.master)
        s.access('irq_intercept_in ' + gic)
        yield s


def read(s, address):
    return int(s.access(f'readl {address:#x}').split()[1], 16)


def count(s, name):
    return s.get('capcom-' + name, s.master)


def advance(s, expected):
    s.query('cont')
    deadline = time.monotonic() + 5
    try:
        while count(s, 'completions') < expected and time.monotonic() < deadline:
            time.sleep(.01)
        assert count(s, 'completions') == expected
    finally:
        s.query('stop')
    read(s, 0x0426f008)  # collect pending qtest IRQ notifications


def check(binary):
    result = {}
    with session(binary, False) as s:
        assert not s.get('z62-capcom-sync', s.master)
        s.write(0x0426f014, 1)
        s.write(0x04282018, 0x01000100)
        assert count(s, 'requests') == 0
        assert count(s, 'completions') == 0
        result['default_off'] = True
    with session(binary) as s:
        assert count(s, 'requests') == count(s, 'completions') == 0
        s.write(0x0426f014, 1)  # rising-edge IRQ0
        s.write(0x0426f000, 0)  # unmask
        s.write(0x04282018, 0x100)  # missing output update mask
        assert count(s, 'requests') == 0
        s.write(0x04282018, 0x01000100)
        s.write(0x04282018, 0x01000100)  # repeated high is not another request
        assert count(s, 'requests') == 1 and count(s, 'completions') == 0
        assert read(s, 0x04282018) & 0x100
        advance(s, 1)
        assert read(s, 0x04282014) & 0x80
        assert read(s, 0x0426f008) & 1
        assert 'IRQ raise 33' in s.irqs, s.irqs
        s.write(0x0426f008, 0)  # cannot forge/erase the pending hardware status
        assert read(s, 0x0426f008) & 1
        s.write(0x0426f010, 1)
        assert not read(s, 0x0426f008) & 1
        assert 'IRQ lower 33' in s.irqs, s.irqs
        s.write(0x04282018, 0x01000000)
        s.write(0x04282018, 0x01000100)
        advance(s, 2)
        assert count(s, 'requests') == 2
        assert s.get('capcom-requests', s.slave) == 0
        s.query('qom-set', {'path': s.master, 'property': 'capcom-completions', 'value': 0}, error=True)
        assert count(s, 'completions') == 2
        # A request while the previous completion remains pending is coalesced.
        s.write(0x04282018, 0x01000000)
        s.write(0x04282018, 0x01000100)
        assert count(s, 'coalesced') == 1
        s.write(0x0426f010, 1)
        s.write(0x0426f000, 1)
        s.write(0x04282018, 0x01000000)
        s.write(0x04282018, 0x01000100)
        s.irqs.clear()
        advance(s, 3)
        assert read(s, 0x0426f008) & 1 and 'IRQ raise 33' not in s.irqs
        s.write(0x0426f000, 0)
        assert 'IRQ raise 33' in s.irqs
        # Reset must cancel a queued timer and clear counters/status/line.
        s.write(0x0426f010, 1)
        s.write(0x04282018, 0x01000000)
        s.write(0x04282018, 0x01000100)
        s.query('system_reset')
        assert count(s, 'requests') == count(s, 'completions') == 0
        assert not read(s, 0x0426f008) & 1
        assert not read(s, 0x04282014) & 0x80
        s.query('cont')
        time.sleep(.03)
        s.query('stop')
        assert count(s, 'completions') == 0
        result.update(request_edge=True, actual_irq65=True, w1c=True, repeated=True,
            coalescing=True, masking=True, reset_cancels=True, readonly_counters=True,
            slave_isolation=True, no_firmware=True, command=s.command)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, default=device.WORK / 'runtime/qemu-system-arm.exe')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # Claim the evidence file before execution; never overwrite an earlier run.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        result = {'completed': False}
        try:
            result.update(check(args.qemu), completed=True)
        except Exception as exc:
            result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
            raise
        finally:
            json.dump(result, stream, indent=2)
    print(json.dumps(result))
