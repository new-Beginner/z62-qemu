"""Native no-firmware tests for C1.70 capture-contact GPIO and IRQ69/70."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import probe_z62_capcom as base
import z62_capture_contacts_device as device


@contextmanager
def session(binary, enabled=True):
    original = subprocess.Popen
    def launch(command, *args, **kwargs):
        command = list(command)
        if enabled:
            command += ['-global', 'nikon-z72-boot-config.z62-capture-contacts=on']
        return original(command, *args, **kwargs)
    with patch.object(subprocess, 'Popen', launch), base.session(binary) as s:
        yield s


def contact(s, line, level, path=None):
    s.access(f'set_irq_in {path or s.master} capture-contact {line} {level}')


def check(binary):
    read = base.read
    result = {}
    with session(binary, False) as s:
        assert not s.get('z62-capture-contacts', s.master)
        contact(s, 0, 1)
        assert s.get('capture-contact-edges', s.master) == 0
        result['default_off'] = True
    with session(binary) as s:
        s.write(0x0426f000, 0)
        s.write(0x0426f014, 0x31)  # rising EXT4/5 and existing CAPCOM EXT0
        assert read(s, 0x04282014) & 0x1800 == 0
        contact(s, 0, 1)
        assert read(s, 0x04282014) & 0x1800 == 0x800
        assert read(s, 0x0426f008) & 0x30 == 0x10
        assert 'IRQ raise 37' in s.irqs
        contact(s, 0, 1)
        assert s.get('capture-contact-edges', s.master) == 1
        assert s.get('capture-contact-irq-events', s.master) == 1
        # Software cannot overwrite physical levels or pending contact causes.
        s.write(0x04282014, 0)
        s.write(0x0426f008, 0)
        assert read(s, 0x04282014) & 0x1800 == 0x800
        assert read(s, 0x0426f008) & 0x30 == 0x10
        contact(s, 1, 1)
        assert read(s, 0x0426f008) & 0x30 == 0x30
        assert 'IRQ raise 38' in s.irqs
        s.write(0x0426f010, 0x10)
        assert read(s, 0x0426f008) & 0x30 == 0x20
        assert 'IRQ lower 37' in s.irqs
        # Preserve the other modeled GPIO source when acknowledging contacts.
        s.write(0x04282018, 0x01000100)
        base.advance(s, 1)
        assert read(s, 0x0426f008) & 0x31 == 0x21
        s.write(0x0426f008, 0)
        assert read(s, 0x0426f008) & 0x31 == 0x21
        s.write(0x0426f010, 0x20)
        assert read(s, 0x0426f008) & 0x31 == 1
        s.write(0x0426f010, 1)
        # Falling level is visible, but does not latch a rising-only cause.
        contact(s, 0, 0)
        assert read(s, 0x0426f008) & 0x30 == 0
        # Masked transitions latch; unmask raises the original IRQ.
        s.write(0x0426f000, 0x30)
        contact(s, 0, 1)
        s.irqs.clear()
        assert read(s, 0x0426f008) & 0x10
        assert 'IRQ raise 37' not in s.irqs
        s.write(0x0426f000, 0)
        assert 'IRQ raise 37' in s.irqs
        s.write(0x0426f010, 0x10)
        s.write(0x0426f014, 1)  # opposite edges, as original mode2 ISR does
        contact(s, 0, 0)
        contact(s, 1, 0)
        assert read(s, 0x0426f008) & 0x30 == 0x30
        assert read(s, 0x04282014) & 0x1800 == 0
        contact(s, 0, 1, s.slave)
        assert s.get('capture-contact-levels', s.slave) == 0
        s.query('qom-set', {'path': s.master, 'property': 'capture-contact-levels', 'value': 3}, error=True)
        assert s.get('capture-contact-levels', s.master) == 0
        s.query('system_reset')
        assert s.get('capture-contact-levels', s.master) == 0
        assert s.get('capture-contact-edges', s.master) == 0
        assert s.get('capture-contact-irq-events', s.master) == 0
        assert read(s, 0x0426f008) & 0x30 == 0
        result.update(levels=True, rising=True, falling=True, repeated=True,
                      mask_pending=True, separate_w1c=True, capcom_coexistence=True,
                      readonly_inputs=True, slave_isolation=True, reset=True,
                      actual_irq69=True, actual_irq70=True, no_firmware=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, default=device.WORK / 'runtime/qemu-system-arm.exe')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = {'completed': False, 'qemu': str(args.qemu)}
    with args.output.open('x', encoding='utf-8') as stream:
        try:
            result.update(check(args.qemu), completed=True)
        except Exception as exc:
            result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
            raise
        finally:
            json.dump(result, stream, indent=2)
    print(json.dumps(result))
