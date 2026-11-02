# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only capture observations and explicit existing lab-source presets.
Not a pixel producer, device repair, or physical-camera transport.
"""
COUNTERS = ('init-submissions', 'init-completions', 'mode-completions',
            'mode2-completions', 'frame-completions')
PRESETS = {
    'baseline': (),
    'mode-only': ('nikon-z62-sensor-config.laboratory-mode-completion=on',),
    'init-mode': ('nikon-z62-sensor-config.laboratory-init-completion=on',
                  'nikon-z62-sensor-config.laboratory-mode-completion=on'),
}
# Addresses are existing Z62 configuration storage, not Z6 hardcoded buffers.
REGIONS = ((0x20068000, 7), (0x20068060, 1), (0x20068100, 2),
           (0x20069500, 13), (0x20069F00, 1)) + tuple(
               region for channel in range(4)
               for region in ((0x20069808 + channel * 0x100, 1),
                              (0x20069850 + channel * 0x100, 8)))

def preset_arguments(name):
    if name not in PRESETS:
        raise ValueError('unknown diagnostic preset')
    return [arg for prop in PRESETS[name] for arg in ('-global', prop)]


def install_preset(popen, name):
    extra = preset_arguments(name)
    class DiagnosticPopen(popen):
        def __init__(self, command, *args, **kwargs):
            if extra and isinstance(command, (list, tuple)) and 'qemu-system-arm' in str(command[0]):
                command = list(command) + extra
            super().__init__(command, *args, **kwargs)
    return DiagnosticPopen


def observe_capture(machine):
    """Caller must hold machine.io. No writes; snapshots are non-atomic."""
    result = {'sensors': {}, 'configuration': {}, 'errors': []}
    for role in ('master', 'slave'):
        values = {}
        for prop in COUNTERS:
            try:
                values[prop] = machine.qmp.command('qom-get', {
                    'path': '/machine/' + role + '-sensor', 'property': prop})
            except (RuntimeError, ValueError, OSError) as exc:
                result['errors'].append({'role': role, 'property': prop,
                                         'type': type(exc).__name__})
        result['sensors'][role] = values
    for address, count in REGIONS:
        try:
            words = machine._words(address, count)
            result['configuration'].update({hex(address+4*i): hex(v) for i,v in enumerate(words)})
        except (RuntimeError, ValueError, OSError) as exc:
            result['errors'].append({'address': hex(address), 'type': type(exc).__name__})
    return result
