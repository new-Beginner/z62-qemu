"""r74 permanent fault evidence on the frozen r69 kernel and r72 observations."""
import argparse
import hashlib
from pathlib import Path
import sys
from unittest.mock import patch
import uuid

import run_z62_paired_diagnostic_console as parent
import z62_persistent_diagnostic_console as persistent

ROOT=Path(__file__).resolve().parents[1]


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    parser=argparse.ArgumentParser(description=__doc__,add_help=False)
    parser.add_argument('--diagnostic-output',type=Path)
    parser.add_argument('--help',action='store_true')
    own,rest=parser.parse_known_args(argv)
    if own.help:
        parser.print_help(); return
    if '--version' in rest:
        print(persistent.VERSION); return
    output=(own.diagnostic_output or ROOT/'analysis/z62-persistent-diagnostic-r74'/('session-'+uuid.uuid4().hex[:12])).absolute()
    if not output.resolve().is_relative_to(ROOT.resolve()) or output.exists():
        raise ValueError('Choose a new permanent diagnostic directory inside this workspace')
    output.mkdir(parents=True)
    profile={'version':persistent.VERSION,'workspace':str(ROOT),'output_root':str(output),
        'source_sha256':hashlib.sha256(Path(persistent.__file__).read_bytes()).hexdigest(),
        'vm_cleanup_may_remove_evidence':False,'camera_accessed':False}
    original=parent.diagnostic.apply_console
    def apply(source,diagnostic_profile):
        original(source,diagnostic_profile)
        persistent.apply_console(source,profile)
    with patch.object(parent.diagnostic,'apply_console',apply):
        parent.main(rest)


if __name__=='__main__':
    main()
