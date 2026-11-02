"""Additional GPIO buttons and physical sub-selector on the r20 host profile."""
import sys
import os
from pathlib import Path
from unittest.mock import patch
import run_z62_encoder_console as host
import z62_extra_console as extra


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if '--version' in argv:
        print(extra.VERSION)
        return
    original=host.labels.apply_console
    def apply(source):
        original(source)
        extra.apply_console(source)
    previous_scratch=os.environ.get('PI_SCRATCH_DIR')
    if previous_scratch is None:
        root=Path(os.environ.get('Z62_RUNTIME_ROOT',str(Path.home()/'Documents/Z62-QEMU-runtime')))
        scratch=(root/'sessions').resolve()
        if not str(scratch).isascii() or ',' in str(scratch):
            raise ValueError('Set Z62_RUNTIME_ROOT to a stable ASCII runtime directory')
        scratch.mkdir(parents=True,exist_ok=True)
        os.environ['PI_SCRATCH_DIR']=str(scratch)
    try:
        with patch.object(host.labels,'apply_console',apply):
            host.main(argv)
    finally:
        if previous_scratch is None:
            os.environ.pop('PI_SCRATCH_DIR',None)


if __name__=='__main__':
    main()
