"""Read-only experimental preview counters, never a complete-firmware verdict."""
def preview_status(machine):
    result={'known':False,'engines':{},'errors':[], 'statistics_bank0_completed':False,
            'silicon_pixel_math_verified':False,'arbitrary_node_graphs_supported':False}
    try:
        entries=machine.qmp.command('qom-list',{'path':'/machine/unattached'})
        paths=['/machine/unattached/'+e['name'] for e in entries if e['type']=='child<nikon-z72-boot-config>']
        for path in paths:
            def get(prop): return machine.qmp.command('qom-get',{'path':path,'property':prop})
            master=get('master-role')
            if type(master) is not bool: raise ValueError('Invalid engine role')
            values={p:get(p) for p in ('z62-preview','preview-attempts','preview-batches','preview-outputs',
                'preview-bytes','preview-rejected','preview-blocked','preview-cancelled','preview-drains','preview-flushes','preview-reason')}
            for key,value in values.items():
                valid=(type(value) is bool if key=='z62-preview' else
                       isinstance(value,str) if key=='preview-reason' else type(value) is int and value>=0)
                if not valid: raise ValueError('Malformed preview counter')
            result['engines']['master' if master else 'slave']=values
        result['known']=set(result['engines'])=={'master','slave'} and len(paths)==2
    except (OSError,RuntimeError,ValueError) as exc:
        result['errors'].append(type(exc).__name__+': '+str(exc))
    return {'preview_status':result,'hardware_version':'2026.10.29-r9'}
