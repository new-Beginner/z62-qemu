"""Trace full-press shared-work validation and the real input field snapshot."""
import argparse
from pathlib import Path
from trace_z62_shutter_route import run
from trace_z62_ready_shared_work import SHARED, STATE

BODY = {**SHARED,
        0x104E43C4:'shared-inputs-built', 0x104E43C8:'shared-validation-a-return',
        0x104E43EC:'shared-work-result', 0x104E43F2:'shared-validation-b-return',
        0x104E4406:'shared-special-result', 0x104E440C:'shared-validation-c-return',
        0x104E4428:'shared-validation-d-return', 0x104E4490:'shared-redraw-request',
        0x105556BA:'shutter-state-to-work-context'}
POINTS={0x10239734:'raw-buffer-descriptor',0x104E97AC:'mode-action-entry',
        0x1054512A:'mode-action-caller-return',**BODY}
WINDOW={'entry':0x104E97AC,'return_pc':0x1054512A,'register':'r0','equals':0x14,
        'points':list(BODY)}


def context(remote, registers):
    if registers['pc']!=0x105556BA:
        return {}
    pointer=registers['r6']
    if not 0xC0000000<=pointer<=0xDFFFFC00:
        raise ValueError('Unexpected work-context pointer')
    return {'work_context':hex(pointer),'shutter_value_to_store':registers['r0'],
            'prior_shutter_halfword':remote.read(pointer+0x2ec,2).hex(),
            'work_context_prefix_64':remote.read(pointer,64).hex()}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--card',type=Path,required=True)
    args=p.parse_args()
    result=run(args.output,args.card,only_points=POINTS,
        extra_state={**STATE,0xC202CEF8:50,0xC181DABC:2,0xC202BF40:64},max_stops=600,
        wait_for_ready=True,duration=45,breakpoint_window=WINDOW,extra_hit_hook=context)
    print(result['summary'])
    print(result.get('breakpoint_window_events'))
    raise SystemExit(0 if result['shutter_route_observation_completed'] and
        not result.get('breakpoint_window_active',True) else 1)
