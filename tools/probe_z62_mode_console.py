"""HTTP mechanical-lock and eight-voltage checks, retaining older input tests."""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError

import probe_z62_extra_console as extra_probe
import z62_mode_console as mode
import z62_mode_selector as selector


def run(output,firmware=None):
    entry=extra_probe.parent.entry
    receipt={'schema':1,'completed':False,'positions':[],
             'adapter':json.loads(json.dumps(mode.identity())),'firmware_mode_functions_verified':False}
    def checks(http_request):
        def request(path, payload=None):
            return json.loads(http_request(path, payload is not None, payload))
        def rejected(path,payload):
            try: request(path,payload)
            except HTTPError as error:
                if error.code!=400: raise
            else: raise ValueError('Invalid/locked mode operation was accepted')
        initial=request('/status')
        if initial.get('mode_dial_adapter')!=receipt['adapter'] or initial['mode_dial']['lock_pressed']:
            raise ValueError('Mode input identity or initial lock differs')
        rejected('/mode',{'position':'M'})
        if request('/status')['mode_dial']['adc_sample']!=initial['mode_dial']['adc_sample']:
            raise ValueError('Locked operation changed the analogue input')
        request('/mode-lock',{'pressed':True})
        for name,code in mode.MODES.items():
            request('/mode',{'position':name})
            state=request('/status')['mode_dial']
            if not state['known'] or state['adc_sample']!=selector.SAMPLES[code] or state['code']!=code:
                raise ValueError('Physical mode level differs from its detent')
            receipt['positions'].append(state)
        request('/release',{})
        final=request('/status')['mode_dial']
        if final['lock_pressed'] or final['adc_sample']!=selector.SAMPLES[10]:
            raise ValueError('Release did not relock or changed the physical mode')
        rejected('/mode-lock',{'pressed':1})
        rejected('/mode',{'position':'Bulb'})
        receipt.update(completed=True,locked_write_rejected=True,release_keeps_detent=True,
                       invalid_inputs_rejected=True)

    try:
        result=extra_probe.run(output,firmware,python_entry=entry.ROOT/'tools/run_z62_mode_console.py',
                               hardware_version='2026.10.30-r21',before_stop=checks)
        receipt['completed'] &= result['completed']
    except Exception as exc:
        receipt.update(completed=False,failure={'type':type(exc).__name__,'message':str(exc)})
    finally:
        if output.is_dir():
            with (output/'mode-check.json').open('x',encoding='utf-8') as handle: json.dump(receipt,handle,indent=2)
    print({'completed':receipt['completed'],'mode_positions':len(receipt['positions'])})
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--firmware',type=Path)
    args=parser.parse_args()
    raise SystemExit(0 if run(args.output,args.firmware)['completed'] else 1)
