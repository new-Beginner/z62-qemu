"""Recover an injected host read timeout in the same original-firmware process."""
import argparse
import json
from pathlib import Path
import probe_z62_liveview as base
import probe_z62_preview_firmware as preview
import z62_qmp_transport as monitor


def run(output):
    original_apply,original_observe=base.host.host.apply_console,base.observe_capture
    recovery=None
    def apply(source,persistent=False):
        original_apply(source,persistent)
        monitor.apply_console(source)
    def observe(machine):
        nonlocal recovery
        capture=original_observe(machine)
        ticks,frequency=machine._key_clock()
        now=ticks/frequency
        if recovery is None and now>=2:
            sock=machine.qmp.sock
            class OneReadTimeout:
                def __getattr__(self,name): return getattr(sock,name)
                def recv(self,size): raise TimeoutError('controlled host monitor read failure')
            machine.qmp.sock=OneReadTimeout()
            failure=None
            try:
                machine.qmp.command('query-status')
            except TimeoutError as exc:
                failure=str(exc)
            finally:
                machine.qmp.sock=sock
            if failure is None:
                raise RuntimeError('Read-timeout control did not execute')
            status=machine.qmp.command('query-status')
            recovery={'guest_virtual_seconds':now,'pid':machine.process.pid,'timeout':failure,
                      'recovered_status':status,'diagnostics':machine.qmp.diagnostics()}
            print('MONITOR_RECOVERY',json.dumps(recovery),flush=True)
        capture['monitor_transport']=machine.qmp.diagnostics()
        return capture
    base.host.host.apply_console,base.observe_capture=apply,observe
    try:
        result=preview.run(output,4,180)
    finally:
        base.host.host.apply_console,base.observe_capture=original_apply,original_observe
    result['monitor_recovery']=recovery
    result['monitor_transport']=monitor.identity()
    result['monitor_recovery_verified']=bool(result['observation_completed'] and recovery and
        recovery['pid']==result['pid'] and recovery['recovered_status']['running'] is True and
        recovery['diagnostics']['timed_out_requests']==1 and recovery['diagnostics']['late_replies']==1 and
        all(not row.get('observation_error') for row in result['samples'] if row.get('virtual_seconds',0) and row['virtual_seconds']>2))
    (output/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=run(args.output)
    print('monitor_recovery_verified=',result['monitor_recovery_verified'])
    raise SystemExit(0 if result['monitor_recovery_verified'] else 1)
