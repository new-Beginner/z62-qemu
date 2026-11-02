"""r27 camera: source acquisition stays on the guest clock; finalization does not."""
from pathlib import Path

try:
    from .z62_video_scene import VideoSceneCamera
    from .z62_software_camera import CameraError, fields
    from .z62_async_video_job import VideoJob
except ImportError:
    from z62_video_scene import VideoSceneCamera
    from z62_software_camera import CameraError, fields
    from z62_async_video_job import VideoJob

VERSION = '2026.11.01-async-video-console-r27'


class AsyncVideoSceneCamera(VideoSceneCamera):
    def __init__(self, *, job_directory, **kwargs):
        self.job_directory = Path(job_directory)
        self._job = None
        self._closing_video = False
        super().__init__(**kwargs)

    def job_active(self):
        return self._job is not None and not self._job.snapshot()['terminal']

    def status(self, now_ns):
        state = super().status(now_ns)
        state['video_profile'] = VERSION
        state['capabilities']['async_video'] = True
        state['video']['async'] = True
        if self._job is not None:
            job = self._job.snapshot()
            state['video'].update(job, job_directory=str(self._job.work), recording=False)
            state['video']['closed'] = self._job.recorder.closed
            if job['phase'] == 'saved' and job['result']:
                state['video']['last_saved'] = job['result']['name']
        return state

    def abort_video(self):
        super().abort_video()
        if self.job_active():
            try:
                self._job.cancel()
            except ValueError:
                pass  # A started catalog commit is awaited, never claimed cancelled.

    def wait_video(self, timeout=None):
        return self._job is None or self._job.wait(timeout)

    def close_video(self, timeout=15):
        self.begin_shutdown()
        if self._job is not None:
            self._job.close(timeout=timeout)

    def begin_shutdown(self):
        self._closing_video = True
        self.abort_video()

    def event(self, kind, payload, now_ns):
        if self._closing_video:
            raise CameraError('video_camera_closing')
        if kind != 'record':
            if self.job_active() and (kind == 'mode' or kind == 'power' and payload.get('on') is False or
                                      kind == 'shutter' and payload.get('stage') == 'full' and payload.get('pressed')):
                raise CameraError('video_job_active: wait or cancel before this operation')
            return super().event(kind, payload, now_ns)
        self._advance(now_ns)
        self._on()
        fields(payload, ('action',))
        action = payload.get('action')
        if self.job_active():
            if action != 'cancel':
                raise CameraError('video_job_active')
            self._job.cancel()
            return {'state': self.status(now_ns), 'result': {'cancel_requested': True, 'job_id': self._job.job_id}}
        if action == 'start':
            if self._job is not None:
                snapshot = self._job.snapshot()
                if snapshot['phase'] == 'saved' and snapshot['result']:
                    self._last_video = snapshot['result']['name']
                self._job.close(timeout=1)
                self._job = None
            return super().event(kind, payload, now_ns)
        if action != 'stop':
            return super().event(kind, payload, now_ns)
        if self._recorder is None:
            raise CameraError('not_recording')
        self.observe_video(now_ns)
        if self._recorder is None:
            raise CameraError('video_source_failed: ' + str(self._video_error))
        recorder = self._recorder
        try:
            job = VideoJob(recorder, self.card, self.job_directory, stop_ns=now_ns)
        except Exception as exc:
            self._video_fail(exc)
            raise
        self._video_stats = recorder.status()
        self._recorder = None
        self._video_phase = 'queued'
        self._job = job
        job.start()
        return {'state': self.status(self.time_ns), 'result': {'encoding': True, 'job_id': job.job_id}}
