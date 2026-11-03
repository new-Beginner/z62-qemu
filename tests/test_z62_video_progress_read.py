"""An exclusively held progress file must not abort a valid owned worker."""
from importlib.util import find_spec
from pathlib import Path
import ctypes
from ctypes import wintypes
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from z62_video_codec import VideoRecorder
from z62_async_video_card import AsyncVideoCard
from z62_async_video_job import VideoJob, atomic_json
from test_z62_video_codec import frame


@unittest.skipUnless(os.name == 'nt' and find_spec('av'), 'Windows native file-sharing test')
class VideoProgressReadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name); (root/'jobs').mkdir()
        card = AsyncVideoCard.create(root/'card'); self.addCleanup(card.close)
        recorder = VideoRecorder(root, start_ns=0, clock_epoch='video-test')
        self.addCleanup(recorder.abort)
        recorder.append(frame('red', 10_000_000, 1)); recorder.append(frame('blue', 70_000_000, 2))
        self.job = VideoJob(recorder, card, root/'jobs', stop_ns=100_000_000)
        self.progress = self.job.work/'progress.json'

    def test_exclusive_reader_keeps_last_state_then_recovers_without_publishing(self):
        atomic_json(self.progress, {'job_id': self.job.job_id, 'phase': 'validating', 'prepared_frames': 2})
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(self.progress), 0x80000000, 0, None, 3, 0x80, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            self.job._read_progress()
            state = self.job.snapshot()
            self.assertEqual(state['phase'], 'idle')
            self.assertEqual(state['progress_read_error']['type'], 'PermissionError')
            self.assertFalse(state['terminal'])
            self.assertEqual(self.job.card.list(), [])
        finally:
            kernel.CloseHandle(handle)
        self.job._read_progress()
        state = self.job.snapshot()
        self.assertEqual(state['phase'], 'validating')
        self.assertEqual(state['prepared_frames'], 2)
        self.assertIsNone(state['progress_read_error'])
        self.assertFalse(state['terminal'])
        self.assertEqual(self.job.card.list(), [])

    def test_corrupt_progress_remains_an_error(self):
        # Use the product writer to create an invalid schema, not a partial write.
        atomic_json(self.progress, {'job_id': 'wrong', 'phase': 'ready', 'prepared_frames': 2})
        with self.assertRaisesRegex(ValueError, 'progress_contract'):
            self.job._read_progress()
