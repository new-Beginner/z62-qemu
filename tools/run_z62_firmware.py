# SPDX-License-Identifier: GPL-2.0-or-later
"""Run a user-selected Z62 C1.70-layout candidate in an isolated QEMU session.

Pass --firmware for a complete update container or --members for the three
complete master.bin/slave.bin/controller.bin images including CRC trailers.
Remaining options are the r5 host options. Automatic MENU starts disabled.
"""
import argparse
from pathlib import Path

import run_z62_transaction as host
from z62_candidate_firmware import load_candidate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--firmware', type=Path)
    group.add_argument('--members', type=Path)
    parser.add_argument('--inspect-only', action='store_true',
                        help='Validate and print identity without starting QEMU')
    parser.add_argument('--help', action='store_true')
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--help' in argv:
        parser.print_help()
        print('\nHost options (one parameter source is required):')
        try:
            host.parse_args(['--help'])
        except SystemExit:
            return
    args, remaining = parser.parse_known_args(argv)
    candidate = load_candidate(package=args.firmware, members=args.members)
    if args.inspect_only:
        if remaining:
            parser.error('Unknown arguments with --inspect-only: ' + ' '.join(remaining))
        import json
        print(json.dumps(candidate.metadata, indent=2, ensure_ascii=False))
        return
    if '--port' not in remaining and not any(a.startswith('--port=') for a in remaining):
        remaining += ['--port', '8674']
    host.main(remaining, candidate=candidate)


if __name__ == '__main__':
    main()
