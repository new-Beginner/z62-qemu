# SPDX-License-Identifier: GPL-2.0-or-later
import io
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_z62_transaction import close_owned_session


class CleanupTests(unittest.TestCase):
    def test_graceful_exit_does_not_terminate(self):
        process = Mock()
        process.poll.side_effect = [None, 0]
        session = Mock()
        handles = [io.BytesIO(), io.BytesIO()]
        self.assertEqual(close_owned_session(process, session, handles[:1], handles[1:], True), [])
        session.query.assert_called_once_with('quit')
        process.terminate.assert_not_called()
        process.kill.assert_not_called()
        self.assertTrue(all(handle.closed for handle in handles))

    def test_failed_handshake_terminates_only_owned_child(self):
        process = Mock()
        process.poll.side_effect = [None, 1]
        session = Mock()
        handles = [io.BytesIO()]
        close_owned_session(process, session, handles, [], False)
        session.query.assert_not_called()
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=15)
        self.assertTrue(handles[0].closed)

    def test_poisoned_qmp_falls_back_and_closes_every_handle(self):
        process = Mock()
        process.poll.side_effect = [None, 1]
        process.wait.side_effect = [subprocess.TimeoutExpired('owned',15),
                                    subprocess.TimeoutExpired('owned',10), 1]
        session = Mock()
        session.query.side_effect = OSError('cannot read from timed out object')
        bad, good = Mock(), io.BytesIO()
        bad.close.side_effect = OSError('close failed')
        notes = close_owned_session(process, session, [bad, good], [], True)
        self.assertEqual(len(notes), 2)
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()
        self.assertTrue(good.closed)

    def test_unreapable_child_still_closes_handles(self):
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = OSError('wait failed')
        session = Mock()
        handle = io.BytesIO()
        with self.assertRaisesRegex(OSError, 'wait failed'):
            close_owned_session(process, session, [handle], [], False)
        self.assertTrue(handle.closed)


if __name__ == '__main__':
    unittest.main()
