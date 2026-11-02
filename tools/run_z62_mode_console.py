"""Mode-dial control with all previous inputs on the verified r21 kernel."""
import argparse
from pathlib import Path
import sys
from unittest.mock import patch

import run_z62_extra_console as host
import run_z62_analog_input as hardware
import z62_mode_console as mode


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if '--version' in argv:
        print(mode.VERSION)
        return
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    own,rest=parser.parse_known_args(argv)
    hardware.verify_build(own.qemu)
    original=host.extra.apply_console
    def apply(source):
        original(source)
        mode.apply_console(source)
    with patch.object(host.extra,'apply_console',apply):
        host.main(['--qemu',str(own.qemu)]+rest)


if __name__=='__main__':
    main()
