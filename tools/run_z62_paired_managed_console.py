"""Run r72 in task-owned D-drive scratch with capacity checks; no global TEMP changes."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

import run_z62_paired_diagnostic_console as diagnostic

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_SCRATCH=ROOT.parent/'z62-qemu-tools/interactive-sessions'


def managed_scratch(root,required_bytes):
    root=Path(root).absolute()
    if not str(root).isascii() or ',' in str(root):
        raise ValueError('Runtime scratch needs an ASCII path without commas')
    for part in (root,*root.parents):
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
            raise ValueError('Linked scratch path is protected')
    marker=root/'z62-sessions-owner.json'
    identity={'schema':1,'workspace':str(ROOT),'purpose':'generated Z62 diagnostic sessions only'}
    if root.exists():
        if not marker.is_file() or json.loads(marker.read_text(encoding='utf-8'))!=identity:
            raise ValueError('Existing scratch directory has no matching owner marker')
    else:
        root.mkdir()
        with marker.open('x',encoding='utf-8') as handle:
            json.dump(identity,handle,indent=2)
    free=shutil.disk_usage(root).free
    if free<required_bytes:
        raise ValueError('Insufficient scratch space before SD staging: need '+str(required_bytes)+', free '+str(free))
    return root


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    parser=argparse.ArgumentParser(description=__doc__,add_help=False)
    parser.add_argument('--scratch-root',type=Path,default=DEFAULT_SCRATCH)
    parser.add_argument('--sd-card',type=Path,default=diagnostic.parent.FIXTURES/'card-r22-4096.raw')
    parser.add_argument('--help',action='store_true')
    args,rest=parser.parse_known_args(argv)
    if args.help:
        parser.print_help(); return
    if '--version' in argv:
        print('2026.11.03-managed-diagnostic-r72a'); return
    if not args.sd_card.is_file():
        raise ValueError('A dedicated regular SD fixture is required')
    scratch=managed_scratch(args.scratch_root,args.sd_card.stat().st_size+2*1024**3)
    # r71 already verifies its fresh-staging parent against gettempdir(). Keep
    # that boundary consistent within this process and restore it on return.
    with patch.object(tempfile,'gettempdir',lambda:str(scratch)), \
         patch.dict(os.environ,{'TEMP':str(scratch),'TMP':str(scratch),'PI_SCRATCH_DIR':str(scratch)}):
        diagnostic.main(['--sd-card',str(args.sd_card)]+rest)


if __name__=='__main__':
    main()
