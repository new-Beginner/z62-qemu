"""Independent r19 body-input console; preserved r13/r16 camera profile."""
import sys
from unittest.mock import patch

import run_z62_capture_console as host
import z62_body_controls as body


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--version' in argv:
        print(body.VERSION)
        return
    original = host.input_adapter.apply_console

    def apply(source):
        original(source)
        body.apply_console(source)

    with patch.object(host.input_adapter, 'apply_console', apply):
        host.main(argv)


if __name__ == '__main__':
    main()
