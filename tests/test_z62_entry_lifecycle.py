"""Probe failures must preserve the HTTP state and allow an unconditional stop."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import probe_z62_entry as entry


class EntryLifecycleTests(unittest.TestCase):
    def exercise(self, callback):
        state = {'phase': 'running', 'virtual_seconds': 2,
                 'hardware_version': 'test', 'preview_status': {'known': True}}
        requests = []
        closed = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self):
                requests.append(self.path)
                if self.path == '/stop':
                    closed.set()
                body = (json.dumps(state).encode() if self.path == '/status'
                        else b'test' if self.path == '/' else b'{"ok": true}')
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = respond

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()

        class Process:
            pid = 123456
            returncode = None

            def poll(self):
                self.returncode = 0 if closed.is_set() else None
                return self.returncode

            def wait(self, timeout):
                if not closed.wait(timeout):
                    raise TimeoutError('Owned test server was not stopped')
                self.returncode = 0
                return 0

        real_request = entry.Request

        def redirect(url, *args, **kwargs):
            from urllib.parse import urlsplit
            return real_request(f'http://127.0.0.1:{server.server_port}' + urlsplit(url).path,
                                *args, **kwargs)

        try:
            with tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / 'probe'
                error = None
                with patch.object(entry.subprocess, 'Popen', return_value=Process()), \
                        patch.object(entry, 'Request', redirect):
                    try:
                        entry.run(output, expected_version='test', diagnostic_key='preview_status',
                                  before_stop=lambda request: callback(request, state))
                    except Exception as exc:
                        error = exc
                report = json.loads((output / 'report.json').read_text()) if output.exists() else {}
                return report, requests, error
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_failed_check_runs_once_and_cleanup_preserves_its_state(self):
        calls = []

        def check(request, state):
            calls.append('checked')
            state.update(phase='failed', error='QMP read deadline', input_worker_failure={'stage': 'clock'})
            request('/status')
            raise RuntimeError('probe check failed')

        report, requests, error = self.exercise(check)
        self.assertEqual(calls, ['checked'])
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(requests.count('/stop'), 1)
        self.assertEqual(report['last_state']['error'], 'QMP read deadline')
        self.assertEqual(report['last_state']['input_worker_failure'], {'stage': 'clock'})
        self.assertIn('probe check failed', report['failure']['traceback'])
        self.assertFalse(report.get('forced_cleanup', False))
        self.assertTrue(report['process_closed'])

    def test_successful_check_can_observe_before_a_single_stop(self):
        report, requests, error = self.exercise(lambda request, state: request('/status'))
        self.assertIsNone(error)
        self.assertTrue(report['completed'])
        self.assertEqual(requests.count('/stop'), 1)
        self.assertEqual(report['last_state']['phase'], 'running')


if __name__ == '__main__':
    unittest.main()
