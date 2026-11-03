"""r72 diagnostic host on the frozen r69 core; no guest execution-state changes."""
import argparse
from pathlib import Path
import sys
from unittest.mock import patch

import run_z62_paired_console as parent
import z62_paired_diagnostic_console as diagnostic
import z62_host_timeout_capture as capture


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    parser=argparse.ArgumentParser(description=__doc__,add_help=False)
    parser.add_argument('--qemu',type=Path,default=parent.hardware.DEFAULT_QEMU)
    parser.add_argument('--host-gdb',type=Path,default=capture.DEFAULT_GDB)
    parser.add_argument('--help',action='store_true')
    if '--version' in argv:
        print(diagnostic.VERSION); return
    own,rest=parser.parse_known_args(argv)
    if own.help:
        parser.print_help(); return
    build=parent.hardware.verify_build(own.qemu)
    if not own.host_gdb.is_file():
        raise ValueError('The owned-process diagnostic needs an existing host GDB')
    original=parent.paired.apply_console
    with capture.ascii_runtime(own.qemu,build['binary_sha256']) as runtime:
        profile={'version':diagnostic.VERSION,'binary_sha256':build['binary_sha256'],
            'logical_binary':str(own.qemu.resolve()),'runtime_binary':str(runtime['binary']),
            'runtime_file_sha256':runtime['file_sha256'],'gdb':str(own.host_gdb.resolve()),
            'diagnostic_only':True,'camera_accessed':False}
        def apply(source,paired_profile):
            original(source,paired_profile)
            diagnostic.apply_console(source,profile)
        if '--port' not in rest and not any(v.startswith('--port=') for v in rest):
            rest+=['--port','8688']
        if '--software-card' not in rest and '--software-no-card' not in rest and not any(v.startswith('--software-card=') for v in rest):
            rest+=['--software-card',str(parent.ROOT/'artifacts/z62-diagnostic-card-r72')]
        if '--input-trace' not in rest:
            rest.append('--input-trace')
        with patch.object(parent.paired,'apply_console',apply):
            parent.main(['--qemu',str(own.qemu)]+rest)


if __name__=='__main__':
    main()
