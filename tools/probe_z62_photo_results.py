"""Native r53 post-return output data and geometry-transition checks."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_preview_results as result_probe
import probe_z62_grid_geometry as grid_probe
import run_z62_photo_results as host


@contextmanager
def results_session(binary, enabled):
    previous=result_probe.preview.host.configure_command
    def configure(command,*args,**kwargs):
        values=list(previous(command,*args,**kwargs))
        if enabled: values+=['-global','nikon-z72-boot-config.z62-photo-result-layouts=on']
        return values
    with patch.object(result_probe.preview.host,'configure_command',configure), result_probe.session(binary) as machine:
        yield machine


def recovered_photo(s):
    result_probe.preview.configure(s)
    result_probe.configure_units(s)
    s.write(0x20100520,0x02a80400)
    s.write(result_probe.PARAMETERS[1]+0x30,697<<16)


def check(binary):
    host.verify_build(binary)
    result={'schema':1,'firmware_executed':False,'camera_accessed':False,
            'physical_cache_lifetime_verified':False}
    with results_session(binary,False) as s:
        recovered_photo(s);result_probe.preview.new_raw(s);result_probe.preview.advance(s)
        assert result_probe.get(s,'batches')==0
        assert result_probe.preview.get(s,'reason')=='result-configuration'
        assert result_probe.preview.read(s,0x2010001c)==0
        result['new_recipe_default_off']=True
    with results_session(binary,True) as s:
        recovered_photo(s)
        geometry=list(result_probe.preview.GEOMETRY)
        w,_,stride,uv=geometry[1];geometry[1]=(w,680,stride,uv)
        for channel,(w,h,stride,uv) in enumerate(geometry):
            for address in set(result_probe.preview.OUTPUTS[channel]):
                for base,size in ((address,stride*h),(address+uv,stride*h//2)):
                    s.access(f'memset {base-16:#x} {size+32:#x} 0xa5')
        result_probe.preview.advance(s)
        assert result_probe.get(s,'batches')==0
        result_probe.preview.new_raw(s);result_probe.preview.advance(s)
        assert result_probe.preview.get(s,'reason')=='success'
        assert result_probe.get(s,'batches')==1 and result_probe.get(s,'units')==3
        expected_bytes=4*sum(stride*h*3//2 for _,h,stride,_ in geometry)
        assert result_probe.preview.get(s,'outputs')==12
        assert result_probe.preview.get(s,'bytes')==expected_bytes
        assert result_probe.preview.read(s,0x2010001c)==0x61
        for channel,(w,h,stride,uv) in enumerate(geometry):
            yprefix,uvprefix=result_probe.preview.expected_prefix(w,h)
            for address in set(result_probe.preview.OUTPUTS[channel]):
                assert s.read(address,32)==yprefix and s.read(address+uv,32)==uvprefix
                for base,size in ((address,stride*h),(address+uv,stride*h//2)):
                    assert s.read(base-16,16)==s.read(base+size,16)==b'\xa5'*16
                    assert s.read(base+size-32,32)!=b'\xa5'*32
        result_probe.acknowledge(s);result_probe.preview.advance(s)
        assert result_probe.get(s,'batches')==1
        result.update(actual_twelve_outputs=True,active_680_extent=True,
                      independent_prefixes=True,last_rows_written=True,
                      guards_preserved=True,ack_does_not_replay=True,
                      output_bytes=expected_bytes,command=s.command)
    # A completed34-row job can be explicitly re-entered as40 rows only when
    # both the separate C retained-input policy and photo-return option are on.
    for enabled in (False,True):
        old=grid_probe.grid.preview.host.configure_command
        def options(command,*args,**kwargs):
            values=list(old(command,*args,**kwargs))
            if enabled: values+=['-global','nikon-z72-boot-config.z62-photo-result-layouts=on']
            return values
        with patch.object(grid_probe.grid.preview.host,'configure_command',options), \
             grid_probe.session(binary,True,True) as s:
            grid_probe.configure_video(s);grid_probe.grid.fill_inputs(s);grid_probe.grid.supplied(s)
            grid_probe.grid.preview.advance(s)
            assert grid_probe.grid.get(s,'groups')==1 and grid_probe.grid.get(s,'last-rows')==34
            grid_probe.grid.acknowledge(s)
            s.write(0x20102648,0)
            grid_probe.grid.configure(s)
            grid_probe.grid.preview.advance(s)
            assert grid_probe.grid.get(s,'groups')==(2 if enabled else 1)
            if enabled:
                assert grid_probe.grid.get(s,'retained-jobs')==1
                assert grid_probe.grid.get(s,'last-rows')==40
                grid_probe.grid.verify_outputs(s)
                grid_probe.grid.acknowledge(s)
                s.write(0x20102648,3);grid_probe.grid.preview.advance(s)
                assert grid_probe.grid.get(s,'groups')==2
                s.query('system_reset')
                assert grid_probe.grid.get(s,'last-rows')==0
    result.update(photo_reentry_needs_both_options=True,completed_rows_transition=True,
                  no_indefinite_photo_replay=True,completed_rows_reset=True,completed=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu',type=Path,default=host.DEFAULT_QEMU)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): raise FileExistsError('Existing photo output evidence is immutable')
    result=check(args.qemu.resolve())
    with args.output.open('x',encoding='utf-8') as handle: json.dump(result,handle,indent=2)
    print(json.dumps(result),flush=True)
