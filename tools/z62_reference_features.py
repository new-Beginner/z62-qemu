# SPDX-License-Identifier: GPL-2.0-or-later
"""Host-only experimental source configuration and read-only QOM diagnostics."""
VERSION = '2026.10.27-r1'


def configure_command(command, args):
    command = list(command)
    if args.sampling_source:
        command += ['-global', 'nikon-z72-boot-config.sensor-sample=on',
                    '-global', 'nikon-z72-boot-config.sample-counter=on']
    if args.input_trace:
        command += ['-global', 'nikon-z72-boot-config.input-trace=on']
    return command


def diagnostics(machine):
    def get(path, name):
        return machine.qmp.command('qom-get', {'path': path, 'property': name})
    state = {'reference_update_version': VERSION,
             'sampling_source': machine.args.sampling_source,
             'sensor_pixels_modeled': False,
             'shoulder': {name: get('/machine/peripheral/shoulder', name)
                          for name in ('page', 'reads', 'writes', 'id-reads', 'page-writes', 'image')},
             'shoulder_physical_segments': False}
    if machine.args.input_trace:
        if not hasattr(machine, 'input_trace_paths'):
            entries = machine.qmp.command('qom-list', {'path': '/machine/unattached'})
            machine.input_trace_paths = ['/machine/unattached/' + item['name'] for item in entries
                                         if item['type'] == 'child<nikon-z72-boot-config>']
            if len(machine.input_trace_paths) != 2:
                raise RuntimeError('Expected two input-trace devices')
        state['input_trace'] = {path: {'count': get(path, 'input-trace-count'),
                                      'log': get(path, 'input-trace-log')}
                                for path in machine.input_trace_paths}
    return state
