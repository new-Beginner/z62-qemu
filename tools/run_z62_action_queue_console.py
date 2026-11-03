"""r76 read-only capture/application diagnostics on the r75 interactive profile."""
import sys
from unittest.mock import patch

import run_z62_committed_photo_console as parent
import z62_action_queue_console as observation


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if '--version' in argv:
        print(observation.VERSION); return
    target=parent.parent.persistent
    original=target.apply_console
    def apply(source,profile):
        original(source,profile)
        observation.apply_console(source)
    with patch.object(target,'apply_console',apply):
        parent.main(argv)


if __name__=='__main__':
    main()
