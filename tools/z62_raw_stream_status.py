# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only RAW stream model counters; caller holds console I/O lock."""


def raw_stream_status(machine):
    result = {'known': False, 'engines': {}, 'errors': [],
              'isp_implemented': False, 'live_view_verified': False}
    try:
        entries = machine.qmp.command('qom-list', {'path': '/machine/unattached'})
        paths = ['/machine/unattached/'+e['name'] for e in entries
                 if e['type'] == 'child<nikon-z72-boot-config>']
        for path in paths:
            def get(prop):
                return machine.qmp.command('qom-get', {'path': path, 'property': prop})
            master = get('master-role')
            if type(master) is not bool:
                raise ValueError('Invalid engine role')
            values = {p: get(p) for p in ('z62-raw-stream', 'raw-stream-active',
                'raw-stream-attempts', 'raw-stream-frames', 'raw-stream-failed',
                'raw-stream-blocked', 'raw-stream-unrelated')}
            for key, value in values.items():
                if key in ('z62-raw-stream', 'raw-stream-active'):
                    valid = type(value) is bool
                else:
                    valid = type(value) is int and value >= 0
                if not valid:
                    raise ValueError('Malformed RAW stream counter')
            result['engines']['master' if master else 'slave'] = values
        result['known'] = set(result['engines']) == {'master', 'slave'} and len(paths) == 2
    except (OSError, RuntimeError, ValueError) as exc:
        result['errors'].append(type(exc).__name__ + ': ' + str(exc))
    return {'raw_stream_status': result, 'hardware_version': '2026.10.29-r7'}
