"""Actual HTTP delivery for four GPIO buttons and all joystick positions."""
import argparse
import json
from pathlib import Path
import time
from urllib.error import HTTPError

import probe_z62_encoder_console as parent
import z62_extra_console as extra
import z62_extra_inputs as inputs


def run(output,firmware=None,*,python_entry=None,hardware_version='2026.10.29-r13',before_stop=None):
    receipt={'schema':1,'completed':False,'gpio':[],'joystick':[],
             'adapter':json.loads(json.dumps(extra.identity())),'photographic_functions_verified':False}
    def checks(http_request):
        def request(path, payload=None):
            return json.loads(http_request(path, payload is not None, payload))
        def wait(predicate):
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                state=request('/status')
                if predicate(state):
                    return state
                request('/heartbeat',{})
                time.sleep(.1)
            raise TimeoutError('Extra input did not reach its requested state')
        state=request('/status')
        if state.get('extra_input_adapter')!=receipt['adapter']:
            raise ValueError('Extra input adapter identity mismatch')
        for key in inputs.GPIO_KEYS:
            request('/key',{'pin':key,'level':0})
            pressed=wait(lambda s:s['extra_input']['gpio_levels'][str(key)]==0 and key in s['held'])
            request('/key',{'pin':key,'level':1})
            released=wait(lambda s:s['extra_input']['gpio_levels'][str(key)]==1 and key not in s['held'])
            receipt['gpio'].append({'key':key,'pressed':pressed['extra_input'],'released':released['extra_input']})
        for position in inputs.JOY_WIRE:
            request('/joystick',{'position':position})
            pressed=wait(lambda s:s['extra_input']['joystick_position']==position)
            actual=pressed['body_controls']['electrical_input']
            if actual!={'known':True,'levels':inputs.joystick_levels(0xffffff,position)}:
                raise ValueError('Wrong physical joystick pattern')
            request('/joystick',{'position':'neutral'})
            released=wait(lambda s:s['extra_input']['joystick_position']=='neutral')
            if released['body_controls']['electrical_input']!={'known':True,'levels':0xffffff}:
                raise ValueError('Joystick contacts did not release')
            receipt['joystick'].append({'position':position,'pressed_levels':actual['levels'],'released_levels':0xffffff})
        request('/key',{'pin':26,'level':0})
        request('/joystick',{'position':'left-up'})
        request('/release',{})
        final=request('/status')
        if (final['held'] or final['queued'] or final['extra_input']['queued_positions'] or
                final['extra_input']['joystick_position']!='neutral' or
                any(value!=1 for value in final['extra_input']['gpio_levels'].values())):
            raise ValueError('Release-all left extra body inputs active')
        try:
            request('/joystick',{'position':'invalid'})
        except HTTPError as exc:
            if exc.code!=400:
                raise
        else:
            raise ValueError('Invalid joystick state accepted')
        receipt.update(completed=True,release_all_verified=True,invalid_input_rejected=True)
        if before_stop is not None:
            before_stop(http_request)

    try:
        result=parent.run(output,firmware,python_entry=python_entry or parent.entry.ROOT/'tools/run_z62_extra_console.py',
                          hardware_version=hardware_version,before_stop=checks)
        receipt['completed'] &= result['completed']
    except Exception as exc:
        receipt.update(completed=False,failure={'type':type(exc).__name__,'message':str(exc)})
    finally:
        if output.is_dir():
            with (output/'extra-check.json').open('x',encoding='utf-8') as handle:
                json.dump(receipt,handle,indent=2)
    print({'completed':receipt['completed'],'gpio':len(receipt['gpio']),'joystick':len(receipt['joystick'])})
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--firmware',type=Path)
    args=parser.parse_args()
    raise SystemExit(0 if run(args.output,args.firmware)['completed'] else 1)
