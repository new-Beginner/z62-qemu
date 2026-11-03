"""Remove only this failed r83 observer's known breakpoints on the same owned VM."""
import argparse
import importlib
import json
from pathlib import Path
import sys
import urllib.request

from probe_z62_capture_submit import owner, profiles
from probe_z62_kernel_events import ARM, THUMB
from record_z62_action_evidence import workspace, digest, require


def recover(session, failed, output, url):
    session, failed, output = map(workspace, (session, failed, output))
    prior = json.loads(failed.read_text(encoding='utf-8'))
    require(prior['completed_observation'] is False and prior.get('cleanup_error') and
            profiles(session) == prior['profile'], 'Not this failed observer session')
    commands = list((session/'runs').glob('*/command.json')); require(len(commands)==1, 'Ambiguous VM')
    command = json.loads(commands[0].read_text(encoding='utf-8'))
    port = int(command[command.index('-gdb')+1].rsplit(':',1)[1]); binary = Path(command[0])
    require(digest(binary) == prior['profile']['diagnostic_profile']['binary_sha256'], 'Runtime changed')
    owned = owner(port,binary); require(owned['ProcessId']==prior['owner']['ProcessId'], 'VM was replaced')
    output.mkdir(parents=True,exist_ok=False)
    record={'schema':1,'failed_result_sha256':digest(failed),'owner':owned,'controls_sent':[],
            'guest_memory_written':False,'guest_registers_written':False,'removed':[],
            'completed_recovery':False,'functional_acceptance_eligible':False}
    remote=None
    try:
        sys.path.insert(0,str(session/'source'))
        Remote=importlib.import_module('analyze.qemu_display').Remote
        remote=Remote(port); record['stop']=remote.command('?')
        for pc in {**THUMB,**ARM}:
            response=remote.command('z1,%x,%d'%(pc,4 if pc in ARM else 2))
            record['removed'].append({'pc':hex(pc),'size':4 if pc in ARM else 2,'response':response})
            if response == 'E22':
                inserted=remote.command('Z1,%x,%d'%(pc,4 if pc in ARM else 2))
                removed=remote.command('z1,%x,%d'%(pc,4 if pc in ARM else 2)) if inserted=='OK' else None
                record['removed'][-1].update(probe_insert=inserted,probe_remove=removed)
                require(inserted=='OK' and removed=='OK','Cannot establish a clear breakpoint address')
            else:
                require(response=='OK','Cannot confirm removal of this observer breakpoint')
        record['detach']=remote.command('D')
        require(record['detach']=='OK','Cannot detach this observer')
        with urllib.request.urlopen(url.rstrip('/')+'/status',timeout=40) as response:
            status=json.load(response)
        record['after']={k:status.get(k) for k in ('phase','execution','virtual_seconds','error','monitor_transport')}
        require(status['phase']=='running' and status['execution']=='running' and not status['error'],
                'VM has not resumed')
        record['completed_recovery']=True
    except Exception as exc:
        record['failure']={'type':type(exc).__name__,'message':str(exc)}
    finally:
        if remote is not None: remote.sock.close()
        with (output/'result.json').open('x',encoding='utf-8') as handle:
            json.dump(record,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in record.items() if k!='owner'},ensure_ascii=False),flush=True)
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',type=Path,required=True); parser.add_argument('--failed',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--url',default='http://127.0.0.1:8688')
    args=parser.parse_args(); result=recover(args.session,args.failed,args.output,args.url)
    raise SystemExit(0 if result['completed_recovery'] else 1)


