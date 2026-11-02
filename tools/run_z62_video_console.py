"""Run the isolated C video profile without changing earlier photo profiles."""
import sys
from unittest.mock import patch

import run_z62_media_console as host
import z62_video_console as video
from z62_video_scene import VERSION


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--version' in argv:
        print(VERSION)
        return
    original = host.media.apply_console

    def apply(source, config):
        original(source, config)
        video.apply_console(source)

    if '--software-card' not in argv and '--software-no-card' not in argv and not any(v.startswith('--software-card=') for v in argv):
        argv += ['--software-card', str(host.host.host.ROOT / 'artifacts/z62-video-card-r26')]
    if '--port' not in argv and not any(v.startswith('--port=') for v in argv):
        argv += ['--port', '8683']
    with patch.object(host.media, 'apply_console', apply):
        host.main(argv)


if __name__ == '__main__':
    main()
