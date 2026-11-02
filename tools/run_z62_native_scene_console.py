"""Run the isolated r24 native scene bridge and shared C photography profile."""
import argparse
from pathlib import Path
import sys
from unittest.mock import patch

import run_z62_software_console as host
import run_z62_scene_file as hardware
import z62_native_scene_console as scene


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--qemu', type=Path, default=hardware.DEFAULT_QEMU)
    own, rest = parser.parse_known_args(argv)
    if '--version' in argv:
        print(scene.VERSION)
        return
    if '--help' in argv:
        parser.print_help()
        host.main(['--help'])
        return
    hardware.verify_build(own.qemu)
    original = host.software.apply_console

    def apply(source, config):
        original(source, config)
        scene.apply_console(source, config)

    if '--software-card' not in rest and '--software-no-card' not in rest and not any(value.startswith('--software-card=') for value in rest):
        rest += ['--software-card', str(host.ROOT / 'artifacts/z62-native-scene-card-r24')]
    if '--port' not in rest and not any(value.startswith('--port=') for value in rest):
        rest += ['--port', '8681']
    with patch.object(host.software, 'apply_console', apply):
        host.main(['--qemu', str(own.qemu)] + rest)


if __name__ == '__main__':
    main()
