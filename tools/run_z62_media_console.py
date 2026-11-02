"""C-level JPEG/NEF media profile; frozen r24 kernel and inputs are preserved."""
import argparse
import sys
from unittest.mock import patch

import run_z62_native_scene_console as host
import z62_media_scene as media


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--photo-format', choices=media.FORMATS, default='jpeg-nef')
    own, rest = parser.parse_known_args(argv)
    if '--version' in argv:
        print(media.VERSION)
        return
    if '--help' in argv:
        parser.print_help()
        host.main(['--help'])
        return
    original = host.scene.apply_console

    def apply(source, config):
        original(source, config)
        media.apply_console(source, {'photo_format': own.photo_format})

    if '--software-card' not in rest and '--software-no-card' not in rest and not any(value.startswith('--software-card=') for value in rest):
        rest += ['--software-card', str(host.host.ROOT / 'artifacts/z62-media-card-r25')]
    if '--port' not in rest and not any(value.startswith('--port=') for value in rest):
        rest += ['--port', '8682']
    with patch.object(host.scene, 'apply_console', apply):
        host.main(rest)


if __name__ == '__main__':
    main()
