"""An explicitly requested attach-stop still runs after a verified-profile failure."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import probe_z62_native_scene_console as probe


class NativeProbeCleanupTests(unittest.TestCase):
    def check_target(self, verified):
        stops = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                if self.path == '/status':
                    value = {'hardware_version': '2026.11.01-r24' if verified else 'other-app',
                             'native_scene': {'version': '2026.11.01-native-scene-console-r24'}}
                    status = 200
                else:
                    value, status = {'error': 'simulated scene failure'}, 503
                data = json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def do_POST(self):
                if self.path == '/stop':
                    stops.append('stop')
                data = b'{"ok":true}'
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                result = probe.run(Path(folder) / 'probe', url=f'http://127.0.0.1:{server.server_port}', stop=True)
                self.assertFalse(result['completed'])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)
        return stops

    def test_known_profile_failure_still_stops_once(self):
        self.assertEqual(self.check_target(True), ['stop'])

    def test_unknown_target_is_never_stopped(self):
        self.assertEqual(self.check_target(False), [])


if __name__ == '__main__':
    unittest.main()
