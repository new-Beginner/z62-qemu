"""Compare native capture GPIO routing with/without contact fanout on r13.

Only external inputs change. The original firmware handles interrupts, queues
and state transitions; no software event or completion is injected.
"""
import argparse
from pathlib import Path
from unittest.mock import patch

import trace_z62_shutter_route as route
import run_z62_capture_contacts as host

POINTS = {
    0x10239734: 'raw-buffer-descriptor',
    0x104E97AC: 'mode-action-entry',
    0x1022A92A: 'capture-contact-isr-callback',
    0x1022A8FE: 'capture-contact-half-worker',
    0x1022A8D8: 'capture-contact-full-worker',
    0x1022A8A0: 'capture-contact-full-release-worker',
    0x1022A868: 'capture-contact-half-release-worker',
}


def fanout(machine, pin, level):
    # Verify the same original resource bindings used to derive this device.
    descriptors = [machine._words(address, 14) for address in (0xC18037DC, 0xC1803814)]
    for row, resource, bit, ext, irq in zip(descriptors, (0x58, 0x59), (11, 12), (4, 5), (69, 70)):
        if (row[0], row[1], row[2], row[8], row[9], row[10], row[12], row[13]) != (
                resource, bit, 0x04282014, 1, ext, irq, 0x1022A92B, 2):
            raise ValueError('Original capture-contact binding changed')
    entries = machine.qmp.command('qom-list', {'path': '/machine/unattached'})
    paths = ['/machine/unattached/' + e['name'] for e in entries
             if e['type'] == 'child<nikon-z72-boot-config>']
    masters = [p for p in paths if machine.qmp.command('qom-get', {'path': p, 'property': 'master-role'})]
    if len(masters) != 1 or pin not in (1, 13) or level not in (0, 1):
        raise ValueError('Ambiguous capture contact target')
    path = masters[0]
    line = 0 if pin == 1 else 1
    machine._qtest(f'set_irq_in {path} capture-contact {line} {1-level}')
    values = {p: machine.qmp.command('qom-get', {'path': path, 'property': p}) for p in
              ('capture-contact-levels', 'capture-contact-edges', 'capture-contact-irq-events')}
    return {'device': path, 'line': line, 'asserted': 1-level, 'diagnostics': values}


def run(output, card, enabled):
    host.verify_build(host.DEFAULT_QEMU)
    configure = route.host.configure_command
    def configured(command, *args, **kwargs):
        return host.configure_command(configure(command, *args, **kwargs), enabled)
    with patch.object(route.host, 'DEFAULT_QEMU', host.DEFAULT_QEMU), \
         patch.object(route.host, 'configure_command', configured):
        return route.run(output, card, only_points=POINTS,
                         extra_state={0xC1821EB8: 1, 0xC1868AE8: 1, 0xC18697DC: 14,
                                      0xC23E3F64: 8, 0x04282014: 1, 0x0426F000: 7},
                         wait_for_ready=True, duration=40, max_stops=300,
                         extra_contact_hook=fanout if enabled else None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--contacts', action=argparse.BooleanOptionalAction, default=False)
    args = parser.parse_args()
    result = run(args.output, args.card, args.contacts)
    print(result['summary'])
    raise SystemExit(0 if result['shutter_route_observation_completed'] else 1)
