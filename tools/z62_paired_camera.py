"""Committed C-ISP frame ownership and observed photo/video transitions."""
from copy import deepcopy
import json

try:
    from .z62_software_camera import Frame, CameraError
except ImportError:
    from z62_software_camera import Frame, CameraError

VERSION = '2026.11.03-paired-camera-r70'
MODES = ('photo', 'video')


def output_record(value):
    row = json.loads(value) if isinstance(value, str) else deepcopy(value)
    if not isinstance(row, dict) or row.get('schema') != 1 or row.get('scope') != 'device-input-to-software-isp-output':
        raise CameraError('output_lineage_schema')
    if any(type(row.get(k)) is not bool for k in ('enabled', 'valid', 'pixel_identity_proven')):
        raise CameraError('output_lineage_flags')
    if row['pixel_identity_proven'] is not False or row.get('mode') not in (*MODES, 'unknown'):
        raise CameraError('output_lineage_scope')
    if row.get('source') not in ('legacy-raw-stream', 'software-paired', 'unknown'):
        raise CameraError('output_lineage_source')
    if any(type(row.get(k)) is not int or not 0 <= row[k] < 1 << 64 for k in
           ('commits', 'sequence', 'epoch', 'publish_id', 'frame_id', 'time_ns')):
        raise CameraError('output_lineage_numbers')
    if row['valid'] and (not row['enabled'] or not row['commits'] or not row['sequence'] or
                         not row['publish_id'] or row['mode'] not in MODES or row['source'] == 'unknown'):
        raise CameraError('output_lineage_inconsistent')
    return row


def owner_matches(row, metadata):
    if not isinstance(metadata, dict):
        return False
    source = metadata.get('native_scene_source', {})
    fields = {'epoch': 'epoch', 'publish_id': 'publish_id', 'frame_id': 'frame_id', 'time_ns': 'virtual_time_ns'}
    return all(type(source.get(name)) is int and source[name] == row[key] for key, name in fields.items())


def owned_frame(exchange, value):
    row = output_record(value)
    if not row['enabled'] or not row['valid']:
        raise CameraError('committed_output_unavailable')
    frame = exchange.frames.get(row['publish_id'])
    if frame is None:
        raise CameraError('committed_scene_not_owned')
    if not owner_matches(row, frame.metadata):
        raise CameraError('committed_scene_tag_mismatch')
    if frame.metadata.get('frame_id') != row['frame_id'] or frame.metadata.get('virtual_time_ns') != row['time_ns']:
        raise CameraError('committed_frame_tag_mismatch')
    return frame


def committed_frame(exchange, value, now_ns, revision, mode):
    row = output_record(value); frame = owned_frame(exchange, row)
    if row['mode'] != mode or frame.metadata.get('pipeline_mode') != mode:
        raise CameraError('committed_output_mode_pending')
    if frame.metadata.get('scene_revision') != revision:
        raise CameraError('scene_settings_pending')
    if type(now_ns) is not int or now_ns < row['time_ns']:
        raise CameraError('future_committed_frame')
    age = now_ns-row['time_ns']
    if age > exchange.max_age_ns:
        raise CameraError('committed_scene_stale')
    metadata = deepcopy(frame.metadata)
    metadata.update(output_lineage=row, capture_virtual_time_ns=now_ns, native_frame_age_ns=age)
    return Frame(frame.image.copy(), metadata)


class PipelineMode:
    def __init__(self, timeout_ns=15_000_000_000, max_age_ns=1_000_000_000):
        self.timeout_ns = timeout_ns
        self.max_age_ns = max_age_ns
        self.confirmed_mode = self.requested_mode = None
        self.ready = False
        self.phase = 'waiting-output'
        self.delivery = 'none'
        self.deadline = self.baseline = self.applied_commits = 0
        self.applied_revision = None

    def begin(self, mode, now_ns, commits):
        if mode not in MODES:
            raise CameraError('invalid_mode')
        if self.requested_mode is not None and self.phase != 'timed-out':
            if mode == self.requested_mode:
                return False
            raise CameraError('pipeline_mode_pending')
        if self.requested_mode is None and self.ready and self.confirmed_mode == mode:
            return False
        self.requested_mode = mode
        self.baseline = commits
        self.deadline = now_ns+self.timeout_ns
        self.applied_revision = None
        self.ready = False
        self.phase = 'awaiting-output'
        self.delivery = 'requested'
        return True

    def delivery_unknown(self):
        self.delivery = 'unknown'

    def applied(self, revision, commits):
        if self.requested_mode is None:
            raise CameraError('pipeline_mode_not_requested')
        self.applied_revision, self.applied_commits = revision, commits
        self.phase = 'awaiting-current-frame'

    def observe(self, value, metadata, camera_mode, revision, now_ns):
        row = output_record(value)
        owned = (row['enabled'] and row['valid'] and owner_matches(row, metadata) and
                 type(now_ns) is int and 0 <= now_ns-row['time_ns'] <= self.max_age_ns)
        current = (owned and metadata.get('scene_revision') == revision and
                   metadata.get('pipeline_mode') == camera_mode and row['mode'] == camera_mode)
        self.ready = False
        result = {'apply_mode': None, 'transition_completed': False}
        if self.requested_mode is None:
            if current:
                self.confirmed_mode = camera_mode
                self.ready = True; self.phase = 'ready'
                return result
            self.phase = 'waiting-output'
            if owned and row['mode'] != camera_mode:
                self.begin(row['mode'], now_ns, max(0, row['commits']-1))
                self.delivery = 'observed-external'
        target = self.requested_mode
        if target is not None and owned and row['mode'] == target:
            if self.applied_revision is None and row['commits'] > self.baseline:
                self.phase = 'awaiting-current-frame'
                result['apply_mode'] = target
                return result
            if (self.applied_revision is not None and row['commits'] > self.applied_commits and current and
                    camera_mode == target and revision >= self.applied_revision):
                self.confirmed_mode = target; self.requested_mode = None
                self.ready = True; self.phase = 'ready'; self.delivery = 'confirmed'
                result['transition_completed'] = True
                return result
        if target is not None and now_ns >= self.deadline:
            self.phase = 'timed-out'
        return result

    def status(self):
        return {'version': VERSION, 'confirmed_mode': self.confirmed_mode, 'requested_mode': self.requested_mode,
                'ready': self.ready, 'phase': self.phase, 'delivery': self.delivery,
                'deadline_virtual_ns': self.deadline if self.requested_mode is not None else None,
                'physical_selector_identity_verified': False, 'whole_camera_verified': False}
