"""Run r27 asynchronous C video; earlier runtime pins stay unchanged."""
import sys
from unittest.mock import patch

import run_z62_video_console as host
import z62_async_video_console as asynchronous
from z62_async_video_scene import VERSION


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--version' in argv:
        print(VERSION)
        return
    original = host.video.apply_console

    def apply(source):
        original(source)
        asynchronous.apply_console(source)

    if '--software-card' not in argv and '--software-no-card' not in argv and not any(v.startswith('--software-card=') for v in argv):
        argv += ['--software-card', str(host.host.host.host.ROOT / 'artifacts/z62-async-video-card-r27')]
    if '--port' not in argv and not any(v.startswith('--port=') for v in argv):
        argv += ['--port', '8684']
    with patch.object(host.video, 'apply_console', apply):
        host.main(argv)


if __name__ == '__main__':
    main()
