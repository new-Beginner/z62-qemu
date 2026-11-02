"""Read-only device counters, not a firmware health verdict."""
def finite_stats_status(machine):
    counters = ('finite-attempts','finite-frames','finite-batches','finite-rejected','finite-bytes','finite-reason')
    values, errors = {}, []
    for role in ('master', 'slave'):
        row = {}
        for name in counters:
            try:
                row[name] = machine.qmp.command('qom-get', {'path': '/machine/'+role+'-input', 'property': name})
            except (RuntimeError, ValueError, OSError) as exc:
                errors.append({'role': role, 'property': name, 'error': str(exc)})
        values[role] = row
    return {'hardware_version': '2026.10.29-r8', 'finite_stats_status': {
        'known': not errors, 'engines': values, 'errors': errors,
        'algorithm_hypothesis': 'stationary last-RAW regional box means',
        'silicon_metering_verified': False, 'live_view_verified': False}}
