"""Issued body edges -> explicit C photo actions, never guest success flags.

The hardware edge is sent once first. A hardware error has unknown outcome and
propagates. Software camera/card errors are observable but must not kill the
firmware input worker or manufacture a successful photo/AF result.
"""
from collections import deque
from copy import deepcopy

VERSION = '2026.11.01-unified-input-r23'


class UnifiedCameraInputMixin:
    def __init__(self, *args, **kwargs):
        self._camera_input_levels = {}
        self._camera_input_epoch = None
        self._camera_input_events = deque(maxlen=64)
        self._camera_input_sequence = 0
        super().__init__(*args, **kwargs)

    def _camera_input_record(self, event):
        self._camera_input_sequence += 1
        event['sequence'] = self._camera_input_sequence
        self._camera_input_events.append(event)

    def _drive_key_pin(self, pin, level):
        event = {'pin': pin, 'level': level, 'hardware_outcome': 'unknown',
                 'software_applied': False, 'software_implementation_level': 'C'}
        try:
            super()._drive_key_pin(pin, level)
        except (OSError, ValueError, RuntimeError) as exc:
            event['error'] = type(exc).__name__ + ': ' + str(exc)
            self._camera_input_record(event)
            raise
        event['hardware_outcome'] = 'issued'
        epoch = str(getattr(self, 'work', 'single-epoch'))
        if epoch != self._camera_input_epoch:
            self._camera_input_levels.clear()
            self._camera_input_epoch = epoch
        previous = self._camera_input_levels.get(pin, 1)
        self._camera_input_levels[pin] = level
        if previous == level:
            event['software_effect'] = 'no-new-edge'
            self._camera_input_record(event)
            return
        # No AF/record/Fn implementation is invented for the remaining pins.
        if pin not in (24, 25, 8, 23, 22, 21, 6, 7):
            event['software_effect'] = 'not-mapped'
            self._camera_input_record(event)
            return
        try:
            camera, now_ns = self._software_locked()
            event['virtual_time_ns'] = now_ns
            kind, payload = None, None
            if pin in (24, 25):
                kind, payload = 'shutter', {'stage': 'half' if pin == 24 else 'full', 'pressed': level == 0}
            elif level == 0:
                if pin == 8:
                    kind, payload = 'playback', {'action': 'open'}
                elif pin == 23:
                    kind, payload = 'delete', {}
                elif pin in (22, 21):
                    kind, payload = 'zoom', {'factor': min(16, camera.zoom * 2) if pin == 22 else max(1, camera.zoom // 2)}
                elif camera.playback:
                    kind, payload = 'playback', {'action': 'next' if pin == 6 else 'previous'}
            if kind is not None:
                result = camera.event(kind, payload, now_ns)
                event.update(software_applied=True, software_effect=kind, result=result['result'])
            else:
                event['software_effect'] = 'release-or-unmapped-context'
        except (OSError, ValueError, RuntimeError) as exc:
            event['error'] = type(exc).__name__ + ': ' + str(exc)
        self._camera_input_record(event)

    def camera_input_status(self):
        return {'version': VERSION, 'sequence': self._camera_input_sequence,
                'last_event': deepcopy(self._camera_input_events[-1]) if self._camera_input_events else None,
                'events': deepcopy(list(self._camera_input_events)),
                'factory_capture_chain_verified': False, 'factory_af_verified': False}

    def status(self):
        state = super().status()
        state['shared_camera_input'] = self.camera_input_status()
        return state
