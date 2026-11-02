"""Physical quadrature inputs recovered from original Z6II C1.70 samplers.

QOM GPIO paths are resolved through their memory-region address, never through
unstable device numbers. Positive means increasing the original raw counter;
it does not yet assert clockwise direction or an exposure-setting outcome.
"""
import hashlib
from pathlib import Path

VERSION = '2026.10.30-encoder-r20'
ENCODERS = {
    0: {'port': 'F', 'base': 0x40021400, 'a_pin': 11, 'b_pin': 14,
        'sampler': 0x0803E360, 'wire_offset': 0x0B,
        'positive': (1, 3, 2, 0), 'negative': (2, 3, 1, 0)},
    1: {'port': 'E', 'base': 0x40021000, 'a_pin': 7, 'b_pin': 13,
        'sampler': 0x0803E3B8, 'wire_offset': 0x0C,
        'positive': (1, 3, 2, 0), 'negative': (2, 3, 1, 0)},
}


def discover_gpio_ports(query):
    """Return unambiguous GPIO devices indexed by their controller MMIO base."""
    found = {}
    for entry in query('qom-list', {'path': '/machine/unattached'}):
        if entry['type'] != 'child<nikon-z72-controller-gpio>':
            continue
        path = '/machine/unattached/' + entry['name']
        regions = [item for item in query('qom-list', {'path': path})
                   if item['type'] == 'child<memory-region>']
        if len(regions) != 1:
            raise ValueError('Controller GPIO does not have one memory region')
        region = path + '/' + regions[0]['name']
        address = query('qom-get', {'path': region, 'property': 'addr'})
        size = query('qom-get', {'path': region, 'property': 'size'})
        if (type(address) is not int or address not in range(0x40020000, 0x40022000, 0x400)
                or size != 0x400 or address in found):
            raise ValueError('Ambiguous controller GPIO address or size')
        found[address] = {'path': path, 'memory_region': region, 'address': address, 'size': size}
    if len(found) != 8:
        raise ValueError('Expected all eight original controller GPIO ports')
    return found


def initialize(machine):
    machine._encoder_ports = discover_gpio_ports(machine.qmp.command)
    machine._encoder_phases = {0: 0, 1: 0}
    # The controller has not executed yet. Establish the resting external levels
    # before its first sample, so initialization cannot create a synthetic step.
    for config in ENCODERS.values():
        path = machine._encoder_ports[config['base']]['path']
        for pin in (config['a_pin'], config['b_pin']):
            machine._qtest(f'set_irq_in {path} unnamed-gpio-in {pin} 0')


def drive_phase(machine, encoder, phase):
    if type(encoder) is not int or encoder not in ENCODERS or type(phase) is not int or not 0 <= phase <= 3:
        raise ValueError('Invalid physical encoder input')
    previous = machine._encoder_phases[encoder]
    changed = previous ^ phase
    if changed not in (0, 1, 2):
        raise ValueError('Quadrature inputs must change one wire at a time')
    config = ENCODERS[encoder]
    path = machine._encoder_ports[config['base']]['path']
    if changed:
        bit = 1 if changed == 2 else 0
        pin = config['a_pin'] if bit else config['b_pin']
        machine._qtest(f'set_irq_in {path} unnamed-gpio-in {pin} {(phase >> bit) & 1}')
        machine._encoder_phases[encoder] = phase


def identity():
    return {'version': VERSION, 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'encoders': ENCODERS, 'resting_phase': 0, 'guest_software_patched': False,
            'main_sub_identity_verified': False, 'clockwise_direction_verified': False}


def apply_console(source):
    from reference_updates import replace_once
    path = source / 'tools/z62_console.py'
    content = path.read_text(encoding='utf-8')
    content = replace_once(content, "        self.qmp = shared.QmpClient(qmp_port)",
        "        self.qmp = shared.QmpClient(qmp_port)\n"
        + "        from tools.z62_encoder_input import initialize as initialize_encoders\n"
        + "        initialize_encoders(self)")
    path.write_text(content, encoding='utf-8', newline='\n')
    (source / 'tools/z62_encoder_input.py').write_bytes(Path(__file__).read_bytes())
