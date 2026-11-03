"""Firmware-free native r52 geometry and explicit-request ownership checks."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_grid as grid
import run_z62_grid_geometry as host


@contextmanager
def session(binary, geometry=True, retained=False):
    old = grid.preview.host.configure_command
    def configure(command, *args, **kwargs):
        result = list(old(command, *args, **kwargs))
        for enabled,name in ((geometry,'z62-grid-geometry'),(retained,'z62-grid-retained-input')):
            if enabled:
                result += ['-global','nikon-z72-boot-config.'+name+'=on']
        return result
    with patch.object(grid.preview.host,'configure_command',configure), grid.session(binary) as machine:
        yield machine


def configure_video(s):
    grid.configure(s)
    # These are precisely the bank0 field changes in the r50 original capture.
    s.write(0x20100460,0x0022003c)
    s.write(0x201004a0,0x0022003c)
    s.write(grid.PARAMETER+0x30,33<<16)
    s.write(0x20102644,34)
    s.write(0x20102648,3)


def outputs(s):
    for slot,address in zip(grid.observed()['source_slots'],grid.observed()['outputs']):
        address = int(address,16)
        assert s.read(address,34*96) == grid.expected(slot)[:34*96]
        assert s.read(address-16,16) == b'\xa5'*16
        assert s.read(address+34*96,6*96+16) == b'\xa5'*(6*96+16)


def check(binary):
    host.verify_build(binary)
    result = {'schema':1,'algorithm_level':'C','firmware_executed':False,
              'physical_cache_lifetime_verified':False,'camera_accessed':False}
    with session(binary,False,False) as s:
        configure_video(s);grid.fill_inputs(s);grid.supplied(s);grid.preview.advance(s)
        assert grid.get(s,'groups') == 0
        assert grid.read(s,0x20100020) == grid.read(s,0x2010001c) == 0
        result['default_off_rejects_new_geometry'] = True
    with session(binary,True,False) as s:
        configure_video(s);grid.fill_inputs(s);grid.supplied(s);grid.preview.advance(s)
        assert grid.get(s,'groups') == 1 and grid.get(s,'bytes') == 4*34*96
        outputs(s)
        grid.acknowledge(s)
        s.write(0x20102648,3);grid.preview.advance(s)
        assert grid.get(s,'groups') == 1 and grid.get(s,'retained-jobs') == 0
        result['fresh_34_geometry_and_guard'] = True
        result['retained_requires_separate_opt_in'] = True
    with session(binary,True,True) as s:
        configure_video(s);grid.fill_inputs(s);grid.preview.advance(s)
        assert grid.get(s,'groups') == 0  # RAM bytes alone are not provenance.
        grid.supplied(s);grid.preview.advance(s)
        assert grid.get(s,'groups') == 1 and grid.get(s,'retained-jobs') == 0
        assert grid.get(s,'config-consumed') == grid.get(s,'config-requests') == 1
        grid.acknowledge(s);grid.preview.advance(s)
        assert grid.get(s,'groups') == 1  # ACK is not a new request.
        source_events = grid.get(s,'source-events')
        first = int(grid.observed()['outputs'][0],16)
        s.access(f'memset {first:#x} {34*96:#x} 0xa6')
        s.write(0x20102648,3);grid.preview.advance(s)
        assert grid.get(s,'groups') == 2 and grid.get(s,'retained-jobs') == 1
        assert grid.get(s,'source-events') == source_events
        assert grid.get(s,'config-consumed') == grid.get(s,'config-requests') == 2
        outputs(s)
        # A new explicit request waits behind both outstanding completion latches.
        s.write(0x20102648,3);grid.preview.advance(s)
        assert grid.get(s,'groups') == 2
        grid.acknowledge(s);grid.preview.advance(s)
        assert grid.get(s,'groups') == 3 and grid.get(s,'retained-jobs') == 2
        outputs(s)
        grid.acknowledge(s)
        s.write(0x20102648,3)
        s.write(0x20102648,0)
        grid.preview.advance(s)
        assert grid.get(s,'groups') == 3
        assert grid.read(s,0x20100020) == grid.read(s,0x2010001c) == 0
        s.write(0x20100020,4);grid.preview.advance(s)
        assert grid.get(s,'groups') == 3
        s.write(0x20102648,3);grid.preview.advance(s)
        assert grid.get(s,'groups') == 4
        grid.pulse(s,0,s.slave)
        assert grid.get(s,'source-events',s.slave) == grid.get(s,'config-requests',s.slave) == 0
        s.query('qom-set',{'path':s.master,'property':'grid-config-requests','value':0},error=True)
        s.query('system_reset');grid.preview.advance(s)
        assert all(grid.get(s,name) == 0 for name in
                   ('groups','bytes','source-events','config-requests','config-consumed','retained-jobs'))
        result.update(no_unproven_ram_supply=True,new_request_actual_four_outputs=True,
                      retained_is_not_new_acquisition=True,ack_does_not_replay=True,
                      pending_completion_backpressure=True,cancel_withdraws_request=True,
                      new_request_after_cancel=True,slave_isolation=True,
                      counters_readonly=True,reset=True,command=s.command)
    result['completed'] = True
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu',type=Path,default=host.DEFAULT_QEMU)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Existing native evidence is immutable')
    result = check(args.qemu.resolve())
    with args.output.open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    print(json.dumps(result),flush=True)
