"""Bounded guest-clock quadrature queue with non-counting cancellation paths."""
from collections import deque
import hashlib
from pathlib import Path

try:
    from .z62_capture_input import CaptureInputMixin
    from .z62_encoder_input import ENCODERS, drive_phase, initialize
except ImportError:
    from z62_capture_input import CaptureInputMixin
    from z62_encoder_input import ENCODERS, drive_phase, initialize

VERSION = '2026.10.30-encoder-queue-r20'
MAX_PHASES = 128
# Neither sampler counts any of these return-to-rest transitions. Returning
# straight to 00 from an arbitrary phase would create an unintended step.
HOME = {0: {0: (), 1: (0,), 2: (3, 1, 0), 3: (1, 0)},
        1: {0: (), 1: (3, 2, 0), 2: (0,), 3: (2, 0)}}


def initialize_queue(machine):
    initialize(machine)
    machine._encoder_events = deque()
    machine._encoder_due = 0
    machine._encoder_edges = 0
    machine._encoder_cancel_requests = 0


class EncoderInputMixin(CaptureInputMixin):
    def rotate(self, encoder, steps):
        if (type(encoder) is not int or encoder not in ENCODERS or
                type(steps) is not int or steps == 0 or not -32 <= steps <= 32):
            raise ValueError('Expected encoder 0/1 and nonzero integer steps in -32..32')
        with self.io:
            self._ready()
            if len(self._encoder_events) + 4 * abs(steps) > MAX_PHASES:
                raise ValueError('Encoder queue is full; wait for current movement')
            pattern = ENCODERS[encoder]['positive' if steps > 0 else 'negative']
            self._encoder_events.extend((encoder, phase) for _ in range(abs(steps)) for phase in pattern)
            self._advance_keys()

    def _advance_keys(self):
        self._advance_button_keys()
        if not getattr(self, '_encoder_events', None):
            return
        ticks, frequency = self._key_clock()
        if frequency <= 0:
            raise ValueError('Encoder clock is unavailable')
        if ticks < self._encoder_due:
            return
        encoder, phase = self._encoder_events[0]
        drive_phase(self, encoder, phase)
        self._encoder_events.popleft()
        self._encoder_edges += 1
        # At least 20 ms per phase in guest time. One edge per pump; never
        # collapse several phases because the host was suspended or delayed.
        self._encoder_due = ticks + max(1, (frequency + 49) // 50)

    def _cancel_encoder_motion(self):
        if not hasattr(self, '_encoder_events'):
            return
        self._encoder_events.clear()
        self._encoder_cancel_requests += 1
        for encoder, phase in self._encoder_phases.items():
            self._encoder_events.extend((encoder, target) for target in HOME[encoder][phase])
        # Preserve the current deadline so the MCU samples the already-issued
        # phase before seeing a homing transition. Completed steps stay completed.

    def _release(self):
        self._cancel_encoder_motion()
        super()._release()

    def _encoder_status(self):
        if not hasattr(self, '_encoder_events'):
            return {'known': False, 'reason': 'not initialized'}
        return {'known': True, 'queued_phases': len(self._encoder_events),
                'phases': dict(self._encoder_phases), 'issued_phases': self._encoder_edges,
                'cancel_requests': self._encoder_cancel_requests,
                'counts_are_guest_observations': False}


def identity():
    return {'version': VERSION, 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'max_queued_phases': MAX_PHASES, 'minimum_phase_guest_seconds': .02,
            'guest_software_patched': False, 'photographic_function_verified': False}


def apply_console(source):
    from reference_updates import replace_once
    path = source / 'tools/z62_console.py'
    content = path.read_text(encoding='utf-8')
    content = replace_once(content, 'class Z62Machine(CaptureInputMixin, shared.Machine):',
        'from tools.z62_encoder_queue import EncoderInputMixin, initialize_queue\n\n\n'
        'class Z62Machine(EncoderInputMixin, shared.Machine):')
    content = replace_once(content, '    def _advance_keys(self):', '    def _advance_button_keys(self):')
    content = replace_once(content, '        self.qmp = shared.QmpClient(qmp_port)',
        '        self.qmp = shared.QmpClient(qmp_port)\n        initialize_queue(self)')
    content = replace_once(content, "                elif self.path == '/release':",
        "                elif self.path == '/rotate':\n"
        + "                    machine.rotate(request.get('encoder'), request.get('steps'))\n"
        + "                elif self.path == '/release':")
    content = replace_once(content, "        if self.phase != 'running':\n            return state",
        '        state["encoder_adapter"] = ' + repr(identity()) + '\n'
        + '        with self.io:\n            state["encoder_input"] = self._encoder_status()\n'
        + "        if self.phase != 'running':\n            return state")
    path.write_text(content, encoding='utf-8', newline='\n')
    (source / 'tools/z62_encoder_queue.py').write_bytes(Path(__file__).read_bytes())
    (source / 'tools/z62_encoder_input.py').write_bytes(Path(__file__).with_name('z62_encoder_input.py').read_bytes())

    html = source / 'web-z62/index.html'
    controls = '<section class="body-key-group" aria-label="拨轮输入"><h2>拨轮输入</h2>'
    controls += '<p class="body-input-note">两组拨轮正反向电平已接入。主副对应与组合键功能正在验证；＋／−表示原厂计数方向。</p>'
    for index in (0, 1):
        controls += f'<h2>拨轮 {index + 1}</h2><div class="body-key-grid">'
        for delta, label in ((-1, '− 一格'), (1, '＋ 一格')):
            controls += f'<button class="key" data-encoder="{index}" data-delta="{delta}" disabled>{label}</button>'
        controls += '</div>'
    controls += '</section>\n'
    content = replace_once(html.read_text(encoding='utf-8'), '      <button id="release"', controls + '      <button id="release"')
    content = replace_once(content, 'ISO、曝光补偿的组合拨轮尚未接入；拍照保存尚未完成。',
        '可以按住 ISO 或曝光补偿，再操作下面的拨轮；组合功能仍在验收。拍照保存尚未完成。')
    html.write_text(content, encoding='utf-8', newline='\n')
    script = source / 'web-z62/console.js'
    content = replace_once(script.read_text(encoding='utf-8'),
        "    document.querySelectorAll('[data-pin]').forEach(button => button.disabled = !available);",
        "    document.querySelectorAll('[data-pin], [data-encoder]').forEach(button => button.disabled = !available);")
    content += '''
document.querySelectorAll('[data-encoder]').forEach(button => {
  button.addEventListener('click', () => {
    if (available) send('/rotate', {encoder: Number(button.dataset.encoder), steps: Number(button.dataset.delta)});
  });
});
'''
    script.write_text(content, encoding='utf-8', newline='\n')
