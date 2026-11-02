"""Read-only continuous-statistics diagnostics; never a firmware-health verdict."""
def continuous_stats_status(machine):
    counters = ('functional-continuous-stats','continuous-attempts','continuous-frames',
                'continuous-batches','continuous-rejected','continuous-bytes','continuous-blocked',
                'continuous-index','continuous-source','continuous-reason')
    values, errors = {}, []
    for role in ('master','slave'):
        row = {}
        for name in counters:
            try:
                value = machine.qmp.command('qom-get', {'path':'/machine/'+role+'-input','property':name})
                valid = (isinstance(value,bool) if name.startswith('functional-') else
                         isinstance(value,str) if name.endswith('-reason') else
                         isinstance(value,int) and not isinstance(value,bool) and value >= 0)
                if not valid:
                    raise ValueError('Unexpected property type')
                row[name] = value
            except (RuntimeError,ValueError,OSError) as exc:
                errors.append({'role':role,'property':name,'error':str(exc)})
        values[role] = row
    return {'continuous_statistics_version':'2026.10.29-r18','continuous_statistics_status':{
        'known':not errors,'engines':values,'errors':errors,'silicon_calibration_verified':False,
        'photo_capture_verified':False}}
