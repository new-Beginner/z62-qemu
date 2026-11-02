# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only original-firmware health. Caller holds the console I/O lock."""


def firmware_health(machine):
    try:
        words = machine._words(0xC253E0C0, 69)
        count = words[68] if len(words) == 69 else None
        valid = type(count) is int and 0 <= count <= 68
        codes = words[:count] if valid else None
        valid = valid and all(type(code) is int and 0 <= code <= 0xffffffff for code in codes)
        return {'firmware_status_count': count, 'firmware_status_codes': codes if valid else None,
                'firmware_health_known': valid, 'firmware_status_empty': valid and count == 0,
                'live_view_verified': False}
    except (OSError, RuntimeError, ValueError) as error:
        return {'firmware_health_known': False, 'firmware_status_empty': False,
                'firmware_status_codes': None, 'firmware_observation_error': type(error).__name__,
                'live_view_verified': False}


def functional_raw_status(machine):
    """Read-only QOM counters. Missing devices/properties remain unknown, not zero."""
    result = {'engines': {}, 'errors': [], 'live_view_verified': False,
              'packing_verified': False, 'snapshot_atomic': False}
    for role in ('master', 'slave'):
        values = {}
        for prop in ('functional-raw', 'raw-accepted', 'raw-rejected', 'raw-bytes', 'raw-last-reason'):
            try:
                value = machine.qmp.command('qom-get', {
                    'path': '/machine/' + role + '-input', 'property': prop})
                valid = (type(value) is bool if prop == 'functional-raw' else
                         isinstance(value, str) if prop == 'raw-last-reason' else
                         type(value) is int and value >= 0)
                if not valid:
                    raise ValueError('Invalid QOM value')
                values[prop] = value
            except (OSError, RuntimeError, ValueError) as error:
                result['errors'].append({'role': role, 'property': prop,
                                         'type': type(error).__name__})
        result['engines'][role] = values
    result['known'] = not result['errors']
    return {'functional_raw_status': result}
