"""Locate the missing ready callback across registration, queue and real worker."""
import argparse
from pathlib import Path
from trace_z62_shutter_route import run

POINTS = {0x10239734:'raw-buffer-descriptor', 0x1032461C:'ready-prequeue-call',
          0x10324620:'ready-prequeue-return', 0x1031624C:'operation-queue-submit',
          0x1031627E:'operation-queue-submit-return', 0x10316288:'operation-queue-wake-return',
          0x10315624:'operation-worker-call', 0x10315626:'operation-worker-return',
          0x10322B50:'ready-join-bit2-producer', 0x104E97AC:'mode-action-entry'}
STATE = {0xC23D9EE8:32, 0xC1868A70:36, 0xC201BEA0:6, 0xC1821EB4:6}


def faults(remote, registers):
    if registers['pc'] != 0x104E97AC or registers['r0'] != 0x14:
        return {}
    current = remote.command('qC')
    if not current.startswith('QC'):
        raise RuntimeError('Cannot identify stopped CPU')
    original = remote.regs()
    cores = []
    try:
        for thread in range(1, 5):
            remote.select_thread(thread)
            core = {'thread':thread, 'pc':hex(remote.get(remote.regs(),'pc'))}
            core['faults'] = {name:remote.read_register(name) for name in
                              ('DFAR_S','IFAR_S','DFSR_S','IFSR_S')}
            cores.append(core)
        remote.select_thread(5)
        cores.append({'thread':5,'pc':hex(remote.get(remote.regs(),'pc')),
                      'scb_cfsr_hfsr_hex':remote.read(0xE000ED28,8).hex()})
        return {'stopped_cpu_fault_snapshot':cores}
    finally:
        remote.select_thread(int(current[2:],16))
        if remote.regs() != original:
            raise RuntimeError('Stopped CPU selection was not restored')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--card',type=Path,required=True)
    args=p.parse_args()
    result=run(args.output,args.card,only_points=POINTS,extra_state=STATE,max_stops=2400,extra_hit_hook=faults)
    print(result['summary'])
    raise SystemExit(0 if result['shutter_route_observation_completed'] else 1)
