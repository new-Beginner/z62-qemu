"""Independent r20 physical encoder console on the preserved camera profile."""
import sys
from unittest.mock import patch

import run_z62_body_console as host
import z62_encoder_queue as encoder
import z62_encoder_labels as labels


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--version' in argv:
        print(encoder.VERSION)
        return
    original = host.body.apply_console

    def apply(source):
        original(source)
        encoder.apply_console(source)
        labels.apply_console(source)

    with patch.object(host.body, 'apply_console', apply):
        host.main(argv)


if __name__ == '__main__':
    main()
