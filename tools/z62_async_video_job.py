"""Owned r27 worker lifecycle. A result file alone never authorizes publication."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

try:
    from .z62_directory_card import plain_path
except ImportError:
    from z62_directory_card import plain_path

VERSION = '2026.11.03-async-video-job-r60-progress'
WORKER_SCRIPT = Path(__file__).with_name('z62_async_video_worker.py')
CODE_FILES = ('z62_async_video_worker.py', 'z62_async_video_job.py', 'z62_async_video_card.py',
              'z62_video_codec.py', 'z62_video_card.py', 'z62_nef_codec.py', 'z62_scene_packet.py',
              'z62_software_camera.py', 'z62_directory_card.py')
TERMINAL = ('saved', 'error', 'cancelled')
_VERIFIED = object()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def code_hashes():
    return {name: digest(Path(__file__).with_name(name).read_bytes()) for name in CODE_FILES}


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as handle:
            handle.write(canonical(value))
            handle.flush()
        deadline = time.monotonic() + 1
        delay = .002
        while True:
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                # Windows readers/scanners can temporarily deny rename while
                # holding the previous JSON. Only this owned file operation is
                # retried; no QMP/GPIO/control request is retransmitted.
                if time.monotonic() >= deadline:
                    raise
                time.sleep(delay)
                delay = min(.05, delay * 2)
    finally:
        if temporary.exists():
            temporary.unlink()


def remove_owned_directory(root, name):
    root = plain_path(root, directory=True).resolve()
    target = plain_path(root / name)
    if target.parent.resolve() != root or target.resolve() != root / name:
        raise ValueError('video_job_cleanup_outside_owned_directory')
    if target.exists():
        plain_path(target, directory=True)
        shutil.rmtree(target)


class WorkerContainment:
    """Windows job handle owns descendants; cancellation never targets a reused PID."""
    def __init__(self):
        self.handle = None
        self.assigned = False
        if os.name != 'nt':
            return
        import ctypes
        from ctypes import wintypes

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in
                        ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                         'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

        class BasicLimits(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong),
                        ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', BasicLimits), ('IoInfo', IoCounters),
                        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process):
        if os.name == 'nt' and not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            import ctypes
            raise ctypes.WinError(ctypes.get_last_error())
        self.assigned = True

    def terminate(self, process):
        if process.poll() is not None:
            return
        if os.name == 'nt' and not self.assigned:
            # The child waits for contained.json before launching any encoder.
            # Popen.terminate uses the retained process handle, not an arbitrary PID.
            process.terminate()
        elif os.name == 'nt':
            if not self.kernel.TerminateJobObject(self.handle, 1):
                import ctypes
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)

    def close(self):
        if self.handle is not None:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class OwnedVideoResult:
    def __init__(self, video, poster, metadata, proof=None):
        if proof is not _VERIFIED:
            raise ValueError('unowned_movie_result')
        self.video, self.poster, self.metadata = video, poster, metadata
        self._video_hash, self._poster_hash = digest(video), digest(poster)
        self._metadata_hash = digest(canonical(metadata))
        self._proof = proof

    def is_verified(self):
        return self._proof is _VERIFIED

    def check_bytes(self):
        if (digest(self.video) != self._video_hash or digest(self.poster) != self._poster_hash or
                digest(canonical(self.metadata)) != self._metadata_hash):
            raise ValueError('verified_movie_changed_before_commit')


class VideoJob:
    def __init__(self, recorder, card, directory, *, stop_ns, timeout_s=180):
        if (type(stop_ns) is not int or len(recorder.samples) < 2 or
                stop_ns < recorder.samples[-1]['virtual_time_ns'] or
                stop_ns - recorder.start_ns > recorder.max_duration or not 0 < timeout_s <= 600):
            raise ValueError('video_invalid_async_stop')
        samples = [deepcopy(row) for row in recorder.samples if row['virtual_time_ns'] < stop_ns]
        if len(samples) < 2:
            raise ValueError('video_insufficient_async_frames')
        directory = plain_path(directory, directory=True)
        self.work = Path(tempfile.mkdtemp(prefix='video-job-', dir=directory))
        self.recorder, self.card = recorder, card
        self.stop_ns, self.timeout_s = stop_ns, float(timeout_s)
        self.job_id = uuid.uuid4().hex
        self.samples = samples
        self.expected_source_hash = digest(canonical(samples))
        self.codes = code_hashes()
        self.entry = plain_path(WORKER_SCRIPT, directory=False).resolve()
        self.entry_hash = digest(self.entry.read_bytes())
        self.process = None
        self.thread = None
        self.lock = threading.RLock()
        self.cancelled = threading.Event()
        self.done = threading.Event()
        self.created = time.monotonic()
        self.state = {'job_id': self.job_id, 'phase': 'idle', 'frames': len(samples), 'prepared_frames': 0,
                      'error': None, 'result': None, 'log': str(self.work / 'worker.log')}

    def start(self):
        with self.lock:
            if self.thread is not None:
                raise ValueError('video_job_already_started')
            self.state['phase'] = 'queued'
            self.thread = threading.Thread(target=self._run, name='z62-video-' + self.job_id[:8], daemon=True)
            self.thread.start()
        return self

    def snapshot(self):
        with self.lock:
            result = deepcopy(self.state)
            process = self.process
        result.update(worker_pid=process.pid if process else None,
                      worker_running=process is not None and process.poll() is None,
                      worker_exit_code=process.returncode if process else None,
                      elapsed_wall_seconds=round(time.monotonic() - self.created, 3))
        result['terminal'] = self.done.is_set() and not result['worker_running'] and result['phase'] in TERMINAL
        return result

    def cancel(self):
        with self.lock:
            if self.done.is_set() and self.state['phase'] in TERMINAL:
                return False
            if self.state['phase'] == 'committing':
                raise ValueError('video_commit_in_progress: wait for its actual result')
            self.cancelled.set()
            self.state['phase'] = 'cancelling'
        return True

    def wait(self, timeout=None):
        return self.done.wait(timeout)

    def close(self, timeout=15):
        if self.thread is None:
            self.recorder.abort()
            return
        try:
            self.cancel()
        except ValueError:
            pass  # A commit must complete before the card lease is closed.
        if not self.done.wait(timeout):
            raise RuntimeError('video_job_close_pending: worker or commit is not terminal')
        self.thread.join(timeout=1)

    def _read_progress(self):
        path = self.work / 'progress.json'
        if not path.exists():
            return
        try:
            raw = path.read_bytes()
        except PermissionError as exc:
            # Progress is observational. Windows may deny an open while the
            # worker atomically replaces this file. Keep the last valid state
            # and retry on the existing polling cycle; result/exit/hash checks
            # remain the only authority for publication.
            with self.lock:
                self.state['progress_read_error'] = {'type': type(exc).__name__, 'message': str(exc)}
            return
        if len(raw) > 65536:
            raise ValueError('video_worker_progress_too_large')
        progress = json.loads(raw)
        if progress['job_id'] != self.job_id or not 0 <= progress['prepared_frames'] <= len(self.samples):
            raise ValueError('video_worker_progress_contract')
        phase = progress['phase']
        if phase not in ('preparing', 'encoding_auditing', 'validating', 'ready', 'error'):
            raise ValueError('video_worker_unknown_phase')
        with self.lock:
            self.state['progress_read_error'] = None
            self.state['prepared_frames'] = progress['prepared_frames']
            if not self.cancelled.is_set():
                self.state['phase'] = ('awaiting_worker_exit' if phase == 'ready' else
                                       'worker_reported_error' if phase == 'error' else phase)

    def _load_result(self, descriptor_hash):
        if self.process is None or self.process.poll() != 0:
            raise ValueError('video_worker_not_successfully_exited')
        if code_hashes() != self.codes or digest(self.entry.read_bytes()) != self.entry_hash:
            raise ValueError('video_worker_code_changed')
        result_path = plain_path(self.work / 'result.json', directory=False)
        if result_path.stat().st_size > 65536:
            raise ValueError('video_worker_result_size')
        result = json.loads(result_path.read_bytes())
        if (result.get('job_id') != self.job_id or result.get('descriptor_sha256') != descriptor_hash or
                result.get('code_sha256') != self.codes or result.get('entry_sha256') != self.entry_hash):
            raise ValueError('video_worker_result_identity')
        blobs = {}
        for key, name, maximum in (('video', 'movie.mp4', 256 * 1024 * 1024),
                                   ('poster', 'poster.jpg', 32 * 1024 * 1024),
                                   ('metadata', 'media.json', 32 * 1024 * 1024)):
            path = plain_path(self.work / 'output' / name, directory=False)
            expected = result['files'][key]
            if not 0 < expected['bytes'] <= maximum or path.stat().st_size != expected['bytes']:
                raise ValueError('video_worker_output_size')
            blobs[key] = path.read_bytes()
            if digest(blobs[key]) != expected['sha256']:
                raise ValueError('video_worker_output_hash')
        metadata = json.loads(blobs['metadata'])
        if (metadata['source_map_sha256'] != self.expected_source_hash or metadata['samples'] != self.samples or
                metadata['clock_epoch'] != self.recorder.clock_epoch or metadata['stop_request_ns'] != self.stop_ns or
                metadata['factory_encoder'] is not False or metadata['audio'] is not False):
            raise ValueError('video_worker_source_contract')
        audit = metadata['independent_audit']
        pts = [(row['virtual_time_ns'] - self.samples[0]['virtual_time_ns']) // 1000 for row in self.samples]
        end = (self.stop_ns - self.samples[0]['virtual_time_ns']) // 1000
        if (audit['pixel_format'] != 'yuv420p' or audit['timestamps_us'] != pts or audit['duration_us'] != end or
                audit['pixel_sha256'] != metadata['encoded_pixel_sha256'] or
                len(audit['source_mse']) != len(self.samples) or not all(0 <= error <= 1000 for error in audit['source_mse'])):
            raise ValueError('video_worker_audit_contract')
        return OwnedVideoResult(blobs['video'], blobs['poster'], metadata, _VERIFIED)

    def _run(self):
        containment = None
        try:
            descriptor = {'version': VERSION, 'job_id': self.job_id, 'parent_pid': os.getpid(),
                'source_directory': str(plain_path(self.recorder.work, directory=True).resolve()),
                'start_ns': self.recorder.start_ns, 'stop_ns': self.stop_ns,
                'clock_epoch': self.recorder.clock_epoch, 'samples': self.samples,
                'source_map_sha256': self.expected_source_hash, 'code_sha256': self.codes,
                'entry_script': str(self.entry), 'entry_sha256': self.entry_hash}
            atomic_json(self.work / 'descriptor.json', descriptor)
            descriptor_hash = digest((self.work / 'descriptor.json').read_bytes())
            (self.work / 'scratch').mkdir()
            environment = dict(os.environ, TEMP=str(self.work / 'scratch'), TMP=str(self.work / 'scratch'))
            containment = WorkerContainment()
            with (self.work / 'worker.log').open('xb') as log:
                with self.lock:
                    if self.cancelled.is_set():
                        return
                    self.state['phase'] = 'starting'
                process = subprocess.Popen([sys.executable, '-X', 'utf8', '-B', str(self.entry),
                    '--job', str(self.work)], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    env=environment, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                    start_new_session=os.name != 'nt')
                with self.lock:
                    self.process = process
                containment.assign(self.process)
                atomic_json(self.work / 'contained.json', {'job_id': self.job_id})
                deadline = time.monotonic() + self.timeout_s
                while self.process.poll() is None:
                    if self.cancelled.wait(.04):
                        containment.terminate(self.process)
                        return
                    if time.monotonic() > deadline:
                        containment.terminate(self.process)
                        raise TimeoutError('video_worker_timeout')
                    self._read_progress()
                self._read_progress()
                if self.cancelled.is_set():
                    return
                if self.process.returncode != 0:
                    detail = ''
                    error_path = self.work / 'worker-error.json'
                    if error_path.is_file() and error_path.stat().st_size <= 65536:
                        error = json.loads(error_path.read_bytes())
                        detail = ': ' + error.get('type', 'WorkerError') + ': ' + error.get('message', '')
                    raise RuntimeError('video_worker_exit_' + str(self.process.returncode) + detail)
                with self.lock:
                    self.state['phase'] = 'checking_result'
                prepared = self._load_result(descriptor_hash)
                with self.lock:
                    if self.cancelled.is_set():
                        return
                    self.state['phase'] = 'committing'
                saved = self.card.commit_verified(prepared)
                with self.lock:
                    self.state.update(phase='saved', result={key: saved[key] for key in ('name', 'bytes', 'sha256', 'kind')})
        except Exception as exc:
            with self.lock:
                self.state.update(phase='error', error={'type': type(exc).__name__, 'message': str(exc)})
        finally:
            try:
                if self.process is not None and self.process.poll() is None:
                    if containment is not None:
                        containment.terminate(self.process)
                    else:
                        self.process.terminate()
                        self.process.wait(timeout=10)
                if containment is not None:
                    containment.close()
                self.recorder.abort()
                remove_owned_directory(self.work, 'scratch')
                with self.lock:
                    if self.cancelled.is_set() and self.state['phase'] != 'saved':
                        self.state.update(phase='cancelled', error=None)
                if self.state['phase'] in ('saved', 'cancelled'):
                    remove_owned_directory(self.work, 'input')
                    # Keep the small manifest/metadata/log; immutable card owns the saved bytes.
                    for name in ('movie.mp4', 'poster.jpg'):
                        path = self.work / 'output' / name
                        if path.exists():
                            plain_path(path, directory=False).unlink()
                atomic_json(self.work / 'parent-result.json', self.snapshot())
            except Exception as exc:
                with self.lock:
                    self.state.update(phase='error', error={'type': type(exc).__name__, 'message': 'video_job_cleanup: ' + str(exc)})
            finally:
                self.done.set()
