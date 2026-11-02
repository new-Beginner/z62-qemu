"""Additional original Z6II expander controls, applied only to private staging.

Mapping is recovered from C1.70, not the Z72 web labels. The underlying input
queue and electrical expander model remain the preserved r16 implementations.
"""
import hashlib
from pathlib import Path

from reference_updates import replace_once

VERSION = '2026.10.30-body-input-r19'
CONTROLS = (
    ('play', '播放', 8, 'KeyP', 'P', '回放'),
    ('delete', '删除', 23, 'Delete', 'Delete', '回放'),
    ('release-mode', '连拍／自拍', 1, 'KeyR', 'R', '拍摄控制'),
    ('i', 'i 菜单', 2, 'KeyI', 'I', '拍摄控制'),
    ('iso', 'ISO', 19, 'KeyO', 'O', '拍摄控制'),
    ('exposure-compensation', '曝光补偿', 18, 'KeyE', 'E', '拍摄控制'),
    ('disp', 'DISP', 10, 'KeyD', 'D', '显示与缩放'),
    ('zoom-in', '放大 ＋', 22, 'Equal', '+', '显示与缩放'),
    ('zoom-out', '缩小 −', 21, 'Minus', '−', '显示与缩放'),
)


def identity():
    return {'version': VERSION,
            'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'controls': [{'id': name, 'pin': pin, 'keyboard_code': code,
                          'mapping_basis': 'original-C1.70-static-route',
                          'functional_acceptance': 'pending'}
                         for name, label, pin, code, key, group in CONTROLS],
            'guest_software_patched': False, 'complete_body_controls': False}


def apply_console(source):
    """Apply after r16 capture input; leave upstream and frozen adapters intact."""
    html = source / 'web-z62/index.html'
    groups = []
    for group in ('回放', '拍摄控制', '显示与缩放'):
        buttons = '\n'.join(
            f'<button class="key" data-pin="{pin}" data-body-control="{name}" disabled>'
            f'{label}<span class="key-detail">{key}</span></button>'
            for name, label, pin, code, key, section in CONTROLS if section == group)
        groups.append(f'<section class="body-key-group" aria-label="{group}">'
                      f'<h2>{group}</h2><div class="body-key-grid">{buttons}</div></section>')
    content = html.read_text(encoding='utf-8')
    content = replace_once(content, '      <button id="release"',
        '<section class="body-controls" aria-label="新增机身输入">'
        '<p class="body-input-note">新增按键已接入原厂输入，功能逐项验证中。'
        'ISO、曝光补偿的组合拨轮尚未接入；拍照保存尚未完成。</p>'
        + '\n'.join(groups) + '</section>\n      <button id="release"')
    html.write_text(content, encoding='utf-8', newline='\n')

    script = source / 'web-z62/console.js'
    content = script.read_text(encoding='utf-8')
    shortcuts = ', '.join(f'{code}: {pin}' for _, _, pin, code, _, _ in CONTROLS)
    content = replace_once(content, 'const shortcuts = {', 'const shortcuts = {' + shortcuts + ', ')
    script.write_text(content, encoding='utf-8', newline='\n')

    css = source / 'web-z62/style.css'
    content = css.read_text(encoding='utf-8') + '''
/* r19 body controls: camera-grey surfaces, silver labels, yellow focus. */
.body-controls { margin: 22px 0; }
.body-input-note { color: #c6c9ca; font-size: 12px; line-height: 1.65; }
.body-key-group { margin-top: 18px; }
.body-key-group h2 { margin: 0 0 9px; color: #e8e9e9; font-size: 13px;
  font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-weight: 600; }
.body-key-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 8px; }
.body-key-grid .key { min-width: 0; min-height: 54px; padding: 10px 8px;
  background: #292c2e; color: #eef0f0; border-color: #5c6266; font-size: 13px; }
.body-key-grid .key.held { background: #49515a; border-color: #f4cd4b; }
.body-key-grid .key:focus-visible { outline: 2px solid #f4cd4b; outline-offset: 3px; }
'''
    css.write_text(content, encoding='utf-8', newline='\n')

    console = source / 'tools/z62_console.py'
    content = console.read_text(encoding='utf-8')
    content = replace_once(content, "        if self.phase != 'running':\n            return state",
        '        state["body_controls"] = ' + repr(identity()) + '\n'
        + "        if self.phase != 'running':\n            return state")
    content = replace_once(content, "            state['execution'] = self.qmp.command('query-status')['status']",
        "            state['execution'] = self.qmp.command('query-status')['status']\n"
        + "            try:\n"
        + "                levels = self.qmp.command('qom-get', {'path': '/machine/peripheral/keys', 'property': 'input-levels'})\n"
        + "                if type(levels) is not int or not 0 <= levels <= 0xffffff:\n"
        + "                    raise ValueError('Malformed expander levels')\n"
        + "                state['body_controls']['electrical_input'] = {'known': True, 'levels': levels}\n"
        + "            except (OSError, RuntimeError, ValueError) as exc:\n"
        + "                state['body_controls']['electrical_input'] = {'known': False, 'error': str(exc)}")
    console.write_text(content, encoding='utf-8', newline='\n')
