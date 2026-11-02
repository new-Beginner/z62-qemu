"""Trace natural finite capture -> native result -> backend configuration on r8."""
import argparse
from pathlib import Path
from types import SimpleNamespace

import trace_z62_capture_setup as capture
import run_z62_raw_stream as parent
import run_z62_finite_stats as host

POINTS = {0x10239734:'raw-buffer-descriptor', 0x1023C38A:'finite-batch-consumer',
          0x102301BC:'finite-result-task', 0x10210B0E:'finite-data-consumer',
          0x102DBBEA:'sensor-mode-result', 0x103C03BE:'backend-node-config'}


def run(output, duration):
    host.verify_build(host.DEFAULT_QEMU.resolve())
    old = capture.POINTS, capture.STATE, parent.configure_command
    def configure(command, *a, **kw):
        return host.configure_command(old[2](command, *a, **kw), True)
    def hit(remote, reg):
        result = {}
        for name in ('r0','r1','r2','r3'):
            address = reg[name]
            if 0xC0000000 <= address <= 0xCFFFFF80:
                result[name] = {'pointer':hex(address),'bytes_128':remote.read(address,128).hex()}
        if reg['pc'] == 0x103C03BE and 0xC0000000 <= reg['r5'] <= 0xCFFFFFF8:
            container = remote.read(reg['r5'], 8)
            table = int.from_bytes(container[:4], 'little')
            count = int.from_bytes(container[4:], 'little')
            if (1 <= count <= 64 and 0xC0000000 <= table <= 0xCFFFFFFF-count*16 and
                    table <= reg['r0'] < table+count*16 and (reg['r0']-table)%16 == 0):
                data = remote.read(table, count*16)
                nodes = []
                for index in range(count):
                    node = data[index*16:(index+1)*16]
                    pointer = int.from_bytes(node[12:16], 'little')
                    row = {'index':index, 'address':hex(table+index*16),
                           'type_byte':node[0], 'physical_unit':node[1],
                           'record_16':node.hex(), 'payload_pointer':hex(pointer)}
                    if 0xC0000000 <= pointer <= 0xCFFFFE00:
                        row['payload_512'] = remote.read(pointer,512).hex()
                    nodes.append(row)
                result['native_graph'] = {'container':hex(reg['r5']), 'table':hex(table), 'count':count,
                                          'nodes':nodes, 'semantics_verified':False}
        return result
    capture.POINTS = POINTS
    capture.STATE = {**old[1], 0xC26A060C:17, 0xC1887CB0:48,
                     0xC2377F78:24, 0x20068008:5}
    parent.configure_command = configure
    args = SimpleNamespace(output=output,qemu=host.DEFAULT_QEMU,native_source=True,
        input_drain=True,frame_start=True,boundary_experiment=False,boundary_line=136,
        ready_bit_experiment=False,ready_set_experiment=False,lifecycle=False,
        frame_objects=False,ownership=False,metadata_event_experiment=False,startup_waits=False,
        virtual_limit=duration,wall_limit=900,menu_at=1000,poll=2,max_stops=300)
    try:
        return capture.run(args,extra_hit_hook=hit)
    finally:
        capture.POINTS,capture.STATE,parent.configure_command = old


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--duration',type=float,default=20)
    args=p.parse_args()
    if not 15<=args.duration<=30: p.error('duration must be 15..30')
    result=run(args.output,args.duration)
    print(result['summary']['counts'])
    raise SystemExit(0 if result['capture_setup_observed'] else 1)
