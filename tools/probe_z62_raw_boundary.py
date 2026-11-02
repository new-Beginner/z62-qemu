"""Native data/IRQ/lifecycle checks for the r17 RAW-ingress boundary."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import probe_z62_raw_stream as raw
import run_z62_raw_boundary as host


@contextmanager
def session(binary, enabled=True):
    original = subprocess.Popen
    def launch(command, *a, **kw):
        return original(host.configure_command(command, enabled), *a, **kw)
    with patch.object(subprocess, 'Popen', launch), raw.session(binary) as s:
        yield s


def count(s, prop='events', path=None):
    return s.get('raw-boundary-' + prop, path or s.master)


def check(binary):
    with session(binary, False) as s:
        raw.start(s)
        raw.frame(s)
        assert raw.get(s, 'frames') == 1
        assert count(s) == 0 and raw.read(s, 0x20068210) & 1 == 0
    with session(binary) as s:
        raw.frame(s)
        assert count(s) == 0
        raw.start(s)
        s.fill()
        raw.frame(s, level=1)
        assert raw.get(s, 'frames') == count(s) == 1
        assert raw.read(s, 0x20068210) & 1 and raw.read(s, 0x20068290) == 0x100
        assert 'IRQ raise 62' in s.irqs and 'IRQ raise 64' in s.irqs
        s.verify_slots(raw.raw.raw.pattern(), guards=True)
        raw.frame(s, level=1)
        assert count(s) == 1
        raw.frame(s, level=0)
        s.write(0x20068210, 1)
        assert raw.read(s, 0x20068210) & 1 == 0 and raw.read(s, 0x20068290) == 0x100
        assert 'IRQ lower 62' in s.irqs
        raw.frame(s)
        assert count(s) == 1 and raw.get(s, 'blocked') == 1
        s.write(0x20068290, 0x100)
        raw.frame(s)
        assert count(s) == 2 and count(s, 'coalesced') == 0
        s.write(0x20068290, 0x100)
        raw.frame(s)
        assert count(s) == 3 and count(s, 'coalesced') == 1
        s.write(0x20068200, 0)
        s.write(0x20068210, 1)
        s.write(0x20068290, 0x100)
        s.irqs.clear()
        raw.frame(s)
        assert count(s) == 4 and raw.read(s, 0x20068210) & 1
        assert 'IRQ raise 62' not in s.irqs
        s.write(0x20068200, 1)
        assert 'IRQ raise 62' in s.irqs
        s.write(0x20068210, 1)
        s.write(0x20068290, 0x100)
        s.write(0x20068018, 0x200)
        raw.frame(s)
        assert count(s) == 4
        raw.start(s)
        s.write(0x20069A08, 1)
        raw.frame(s)
        assert raw.get(s, 'failed') == 1 and count(s) == 4
        assert raw.read(s, 0x20068210) & 1 == 0
        s.configure()
        for level in (0, 1, 0):
            s.access(f'set_irq_in /machine/master-input raw-submit 0 {level}')
        assert count(s) == 4
        raw.frame(s, path=s.slave)
        assert count(s, path=s.slave) == 0
        s.query('qom-set', {'path': s.master, 'property': 'raw-boundary-events', 'value': 0}, error=True)
        s.query('system_reset')
        assert count(s) == count(s, 'coalesced') == 0
        assert raw.read(s, 0x20068210) & 1 == 0
        raw.frame(s)
        assert count(s) == 0
    return {'default_off': True, 'actual_raw_dma_verified': True, 'irq94_and_irq96': True,
            'independent_w1c': True, 'backpressure': True, 'coalescing': True,
            'mask_latching': True, 'stop': True, 'failed_dma_no_event': True,
            'unrelated_dma_no_event': True, 'slave_isolation': True, 'readonly': True, 'reset': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    parser.add_argument('--unextended-parent', action='store_true', help='run the negative control on frozen r13')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    verifier = host.parent.verify_build if args.unextended_parent else host.verify_build
    manifest = verifier(args.qemu.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = {'completed': False, 'binary_sha256': manifest['binary_sha256'],
              'firmware_loaded': False, 'guest_instructions_executed': False, 'camera_accessed': False}
    with args.output.open('x', encoding='utf-8') as handle:
        try:
            result.update(check(args.qemu), completed=True)
        except Exception as exc:
            result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
            raise
        finally:
            json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))
