# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only r5 transaction bridge observations; no firmware or device writes."""
PROPERTIES = ('functional-raw-completion', 'raw-source-events',
              'raw-completions', 'raw-ignored', 'raw-coalesced', 'raw-completion-last-reason')


def transaction_status(machine):
    result = {'engines': {}, 'errors': [], 'snapshot_atomic': False,
              'hardware_timing_verified': False, 'live_view_verified': False}
    for role in ('master', 'slave'):
        values = {}
        for prop in PROPERTIES:
            try:
                value = machine.qmp.command('qom-get', {
                    'path': '/machine/' + role + '-sensor', 'property': prop})
                valid = (type(value) is bool if prop == PROPERTIES[0] else
                         isinstance(value, str) if prop == 'raw-completion-last-reason' else
                         type(value) is int and value >= 0)
                if not valid:
                    raise ValueError('Malformed QOM property')
                values[prop] = value
            except (OSError, RuntimeError, ValueError) as exc:
                result['errors'].append({'role': role, 'property': prop,
                                         'type': type(exc).__name__})
        result['engines'][role] = values
    result['known'] = not result['errors']
    return {'transaction_bridge': result}
