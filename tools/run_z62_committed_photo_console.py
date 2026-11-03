"""r75 UI synchronization over r74's permanent evidence and frozen r69 core."""
import sys
from unittest.mock import patch

import run_z62_persistent_diagnostic_console as parent
import z62_committed_controls_console as controls


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if '--version' in argv:
        print(controls.VERSION); return
    original=parent.persistent.apply_console
    def apply(source,profile):
        original(source,profile)
        controls.apply_console(source)
    with patch.object(parent.persistent,'apply_console',apply):
        parent.main(argv)


if __name__=='__main__':
    main()
