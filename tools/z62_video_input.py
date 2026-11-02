"""Extend issued record-GPIO edges with explicit C video effects."""


class VideoBodyInputMixin:
    def __init__(self, *args, **kwargs):
        self._video_pending_action = None
        super().__init__(*args, **kwargs)

    def _drive_key_pin(self, pin, level):
        epoch = str(getattr(self, 'work', 'single-epoch'))
        previous = self._camera_input_levels.get(pin, 1) if self._camera_input_epoch == epoch else 1
        try:
            super()._drive_key_pin(pin, level)
        except Exception:
            if pin == 29:
                self._video_pending_action = None
            raise
        if pin != 29 or previous == level or level != 0:
            return
        event = self._camera_input_events[-1]
        action, self._video_pending_action = self._video_pending_action, None
        if event['hardware_outcome'] != 'issued':
            return
        try:
            camera, now_ns = self._software_locked()
            if action is None:
                action = 'stop' if camera._recorder is not None else 'start'
            result = camera.event('record', {'action': action}, now_ns)
            event.update(software_applied=True, software_effect='record', virtual_time_ns=now_ns,
                         record_action=action, result=result['result'])
        except Exception as exc:
            # Encoder, decoder and storage errors are C backend failures, not
            # reasons to kill the firmware input worker or fabricate success.
            event.update(software_applied=False, software_effect='record', record_action=action,
                         error=type(exc).__name__ + ': ' + str(exc))

    def _release(self):
        super()._release()
        self._video_pending_action = None
        self._camera_input_levels[29] = 1
