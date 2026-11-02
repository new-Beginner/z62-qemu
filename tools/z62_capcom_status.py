# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only CAPCOM model observations; invoked under console I/O lock."""


def capcom_status(machine):
    result = {'known': False, 'engines': {}, 'errors': [],
              'mechanical_capture_verified': False, 'latency_ns_hypothesis': 100000}
    try:
        entries = machine.qmp.command('qom-list', {'path': '/machine/unattached'})
        paths = ['/machine/unattached/' + e['name'] for e in entries
                 if e['type'] == 'child<nikon-z72-boot-config>']
        if len(paths) != 2:
            raise ValueError('Expected two engine configurations')
        for path in paths:
            def get(prop):
                return machine.qmp.command('qom-get', {'path': path, 'property': prop})
            role = 'master' if get('master-role') else 'slave'
            values = {p: get(p) for p in ('z62-capcom-sync', 'capcom-requests',
                      'capcom-completions', 'capcom-coalesced')}
            if type(values['z62-capcom-sync']) is not bool or any(
                type(values[p]) is not int or values[p] < 0 for p in
                ('capcom-requests', 'capcom-completions', 'capcom-coalesced')):
                raise ValueError('Malformed CAPCOM diagnostics')
            result['engines'][role] = values
        result['known'] = set(result['engines']) == {'master', 'slave'}
    except (OSError, ValueError, RuntimeError) as exc:
        result['errors'].append(type(exc).__name__ + ': ' + str(exc))
    return {'capcom_sync_status': result, 'hardware_version': '2026.10.28-r6'}
