"""r22 opt-in software photography alongside the preserved r21 firmware host."""
import argparse
from pathlib import Path
import sys
from unittest.mock import patch

import run_z62_mode_console as host
import z62_software_console as software

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--software-card', type=Path, default=ROOT / 'artifacts/z62-software-card-r22')
    group.add_argument('--software-no-card', action='store_true')
    parser.add_argument('--software-scene', type=Path)
    parser.add_argument('--software-width', type=int, default=640)
    parser.add_argument('--software-height', type=int, default=424)
    if '--help' in argv:
        parser.print_help()
        return
    if '--version' in argv:
        print(software.VERSION)
        return
    own, rest = parser.parse_known_args(argv)
    # Keep the un-resolved user path until the card layer has rejected links.
    config = {'card': None if own.software_no_card else str(own.software_card.absolute()),
              'scene': str(own.software_scene.absolute()) if own.software_scene else None,
              'width': own.software_width, 'height': own.software_height}
    original = host.mode.apply_console

    def apply(source):
        original(source)
        software.apply_console(source, config)

    if '--port' not in rest and not any(value.startswith('--port=') for value in rest):
        rest += ['--port', '8680']
    with patch.object(host.mode, 'apply_console', apply):
        host.main(rest)


if __name__ == '__main__':
    main()
