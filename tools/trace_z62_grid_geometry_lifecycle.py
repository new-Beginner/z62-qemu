"""Run the unchanged selector scenario with the two r52 options separately."""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

import trace_z62_mode_inputs as parent
import run_z62_grid_geometry as host

VERSION = '2026.11.03-grid-geometry-lifecycle-r52'


def collect_counters(machine, cache):
    class PropertyNames:
        def command(self, name, arguments=None):
            if (name == 'qom-get' and arguments.get('path') == '/machine/master-input' and
                    arguments.get('property') == 'raw-reason'):
                arguments = {**arguments,'property':'raw-last-reason'}
            return machine.qmp.command(name,arguments)
    # The r51 schema name is retained, but its real source is declared below.
    result = ORIGINAL_COUNTERS(SimpleNamespace(io=machine.io,qmp=PropertyNames()),cache)
    result['property_source_aliases'] = {'input.raw-reason':'/machine/master-input.raw-last-reason'}
    with machine.io:
        for name in ('grid-config-requests','grid-config-consumed','grid-retained-jobs'):
            try:
                value = machine.qmp.command('qom-get',{'path':cache['stream'],'property':name})
                if type(value) is not int or value < 0:
                    raise ValueError('Invalid grid request counter')
                result['stream'][name] = value
            except (OSError,RuntimeError,ValueError) as exc:
                result['errors'].append({'property':name,'type':type(exc).__name__,'message':str(exc)})
    result['known'] = not result['errors']
    return result


ORIGINAL_COUNTERS = parent.collect_counters


def run(output,card,group23,qemu,retained=False,duration=55):
    build = host.verify_build(qemu)
    configure = parent.pipeline.parent.configure_command
    def options(command,grid=True):
        return host.configure_command(configure(command,grid),True,retained)
    with patch.object(parent,'collect_counters',collect_counters), \
         patch.object(parent,'VERSION',VERSION), \
         patch.object(parent.pipeline.parent,'configure_command',options):
        result = parent.run(output,card,group23,qemu,duration)
    result = {**result,'entry_profile':VERSION,'geometry_enabled':True,
              'retained_input_enabled':retained,
              'entry_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'grid_geometry_build':build,
              'retained_input_is_new_acquisition':False}
    with (output/'grid-geometry-lifecycle.json').open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--card',type=Path,required=True)
    parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--qemu',type=Path,default=host.DEFAULT_QEMU)
    parser.add_argument('--retained-input',action='store_true')
    parser.add_argument('--duration',type=float,default=55)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.with_name(args.output.name+'-stdout.txt').open('x',encoding='utf-8') as log:
        with redirect_stdout(parent.pipeline.parent.Tee(sys.stdout,log)):
            result = run(args.output,args.card,args.group23,args.qemu.resolve(),args.retained_input,args.duration)
    raise SystemExit(0 if result['completed_observation'] else 1)
