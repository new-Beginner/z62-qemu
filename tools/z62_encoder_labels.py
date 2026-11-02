"""UI labels from original rotary-name table and bounded ISO observation.

Kept separate from the frozen queue implementation tested in queued-messages2.
"""
import hashlib
from pathlib import Path
from reference_updates import replace_once

VERSION = '2026.10.30-encoder-labels-r20'


def identity():
    return {'version': VERSION, 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'labels': ['主拨轮', '副拨轮'], 'basis': 'C1.70 rotary-name table and original ISO combination',
            'clockwise_direction_verified': False, 'shutter_aperture_controls_verified': False}


def apply_console(source):
    path = source / 'web-z62/index.html'
    html = path.read_text(encoding='utf-8')
    for index, label in enumerate(identity()['labels']):
        html = replace_once(html, f'<h2>拨轮 {index + 1}</h2>', f'<h2>{label}</h2>')
        for delta, direction in ((-1, '减少一格'), (1, '增加一格')):
            before = f'<button class="key" data-encoder="{index}" data-delta="{delta}" disabled>'
            after = before[:-1] + f' aria-label="{label}{direction}">'
            html = replace_once(html, before, after)
    html = replace_once(html,
        '两组拨轮正反向电平已接入。主副对应与组合键功能正在验证；＋／−表示原厂计数方向。',
        '按住键盘 O（ISO）再点拨轮。＋／−表示原厂计数方向，画面以原固件响应为准。快门、光圈及其他组合尚未完整验收。')
    path.write_text(html, encoding='utf-8', newline='\n')
    path = source / 'tools/z62_console.py'
    content = replace_once(path.read_text(encoding='utf-8'),
        '        with self.io:\n            state["encoder_input"] = self._encoder_status()',
        '        state["encoder_labels"] = ' + repr(identity()) + '\n'
        + '        with self.io:\n            state["encoder_input"] = self._encoder_status()')
    path.write_text(content, encoding='utf-8', newline='\n')
