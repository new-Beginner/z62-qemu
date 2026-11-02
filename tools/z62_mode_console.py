"""Physical mode ladder and mechanical lock over the complete input host.

The dial position is distinct from the firmware's effective exposure mode.
No-lens P/S behavior and photographic operation remain separate acceptance.
"""
import hashlib
from pathlib import Path
import time

try:
    from .z62_extra_console import ExtraInputMixin
    from . import z62_mode_selector as selector
except ImportError:
    from z62_extra_console import ExtraInputMixin
    import z62_mode_selector as selector

VERSION='2026.10.30-mode-console-r22'
MODES={'P':0,'S':1,'A':2,'M':3,'U1':4,'U2':5,'U3':6,'AUTO':10}
LOCK_LEASE=64


def initialize(machine):
    selector.initialize(machine)
    machine._mode_lock_pressed=False


class ModeInputMixin(ExtraInputMixin):
    def set_mode_lock(self,pressed):
        if type(pressed) is not bool:
            raise ValueError('Expected a boolean mode-lock input')
        with self.io:
            self._ready()
            self._mode_lock_pressed=pressed
            if pressed:
                self.requested_keys.add(LOCK_LEASE)
                self.key_deadline=time.monotonic()+5
            else:
                self.requested_keys.discard(LOCK_LEASE)

    def set_mode(self,name):
        if not isinstance(name,str) or name not in MODES:
            raise ValueError('Unknown mode-dial position')
        with self.io:
            self._ready()
            if not self._mode_lock_pressed:
                raise ValueError('请先按住模式盘锁释放键（键盘 L）')
            selector.drive(self,MODES[name])

    def _mode_status(self):
        pressed=getattr(self,'_mode_lock_pressed',False)
        if not hasattr(self,'_mode_adc_path'):
            return {'known':False,'lock_pressed':pressed}
        try:
            sample=self.qmp.command('qom-get',{'path':self._mode_adc_path,'property':'input-channel2'})
            if type(sample) is not int or not 0<=sample<=4095:
                raise ValueError('Invalid mode ADC level')
            code=next(code for low,high,code in selector.BANDS if low<=sample<high)
            name=next(name for name,value in MODES.items() if value==code)
            return {'known':True,'lock_pressed':pressed,'position':name,'code':code,'adc_sample':sample,
                    'effective_firmware_mode_known':False}
        except (OSError,RuntimeError,ValueError) as exc:
            return {'known':False,'lock_pressed':pressed,'error':str(exc)}

    def _release(self):
        self._mode_lock_pressed=False
        self.requested_keys.discard(LOCK_LEASE)
        # Spring-release the mechanical lock. The selected voltage is persistent.
        super()._release()


def identity():
    return {'version':VERSION,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'modes':MODES,'selector':selector.identity(),'mechanical_lock_only':True,
            'guest_software_patched':False,'all_exposure_mode_functions_verified':False}


def apply_console(source):
    from reference_updates import replace_once
    path=source/'tools/z62_console.py'
    content=replace_once(path.read_text(encoding='utf-8'),
        'class Z62Machine(ExtraInputMixin, shared.Machine):',
        'from tools.z62_mode_console import ModeInputMixin, initialize as initialize_mode_dial\n\n\n'
        'class Z62Machine(ModeInputMixin, shared.Machine):')
    content=replace_once(content,'        initialize_extra_inputs(self)',
        '        initialize_extra_inputs(self)\n        initialize_mode_dial(self)')
    content=replace_once(content,"                elif self.path == '/joystick':",
        "                elif self.path == '/mode-lock':\n"
        "                    machine.set_mode_lock(request.get('pressed'))\n"
        "                elif self.path == '/mode':\n"
        "                    machine.set_mode(request.get('position'))\n"
        "                elif self.path == '/joystick':")
    content=replace_once(content,'            state["extra_input"] = self._extra_input_status()',
        '            state["extra_input"] = self._extra_input_status()\n'
        '            state["mode_dial"] = self._mode_status()\n'
        '        state["mode_dial_adapter"] = '+repr(identity()))
    path.write_text(content,encoding='utf-8',newline='\n')
    for name in ('z62_mode_selector.py','z62_mode_console.py'):
        (source/'tools'/name).write_bytes(Path(__file__).with_name(name).read_bytes())
    path=source/'web-z62/index.html'
    html=path.read_text(encoding='utf-8')
    control='<section class="body-key-group" aria-label="模式盘"><h2>模式盘</h2>'
    control+='<p id="mode-position" class="body-input-note">等待挡位输入</p>'
    control+='<button class="key" id="mode-lock" aria-pressed="false" disabled>按住解锁<span class="key-detail">键盘 L</span></button>'
    control+='<div class="mode-dial-grid">'
    for name in ('AUTO','P','S','A','M','U1','U2','U3'):
        control+=f'<button class="key" data-mode="{name}" disabled>{name}</button>'
    control+='</div><p class="body-input-note">按住 L 再选择挡位，也可按 1–8（依上方顺序）。这里显示物理挡位，拍摄模式以原厂屏幕为准；当前无镜头，P/S 成像尚未验收。</p></section>\n'
    html=replace_once(html,'      <button id="release"',control+'      <button id="release"')
    path.write_text(html,encoding='utf-8',newline='\n')
    path=source/'web-z62/style.css'
    path.write_text(path.read_text(encoding='utf-8')+
        '\n.mode-dial-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:6px; margin-top:8px; }\n'
        '.mode-dial-grid .key { min-width:0; padding:12px 4px; font-size:12px; }\n'
        '.mode-dial-grid .key[aria-current="true"] { border-color:#f4cd4b; color:#f4cd4b; }\n',encoding='utf-8',newline='\n')
    path=source/'web-z62/console.js'
    text=replace_once(path.read_text(encoding='utf-8'),"    $('release').disabled = !available;",
        "    $('release').disabled = !available;\n    paintModeDial(state);")
    text+='''
let modeLockHeld = false, lastModeState = null;
// Candidate staging runs after this adapter and uses the original heading as
// an identity anchor. Retitle only the normal rendered page, never the candidate.
const modeHeading = document.querySelector('h1');
if (modeHeading && modeHeading.textContent === '操作原厂菜单') modeHeading.textContent = '操作机身控件';
function paintModeDial(state) {
  lastModeState = state.mode_dial || {known:false};
  $('mode-lock').disabled = !available;
  $('mode-lock').setAttribute('aria-pressed', String(modeLockHeld));
  $('mode-position').textContent = lastModeState.known ? '模式盘挡位：' + lastModeState.position : '挡位暂不可读';
  document.querySelectorAll('[data-mode]').forEach(button => {
    button.disabled = !(available && modeLockHeld && lastModeState.known && lastModeState.lock_pressed);
    button.setAttribute('aria-current', String(lastModeState.known && button.dataset.mode === lastModeState.position));
  });
}
function modeLock(pressed) {
  if ((pressed && !available) || modeLockHeld === pressed) return;
  modeLockHeld = pressed;
  $('mode-lock').setAttribute('aria-pressed', String(pressed));
  if (!pressed) document.querySelectorAll('[data-mode]').forEach(button => button.disabled = true);
  send('/mode-lock', {pressed}).then(status);
}
$('mode-lock').addEventListener('pointerdown', event => {
  if (event.button !== 0) return;
  event.preventDefault(); $('mode-lock').setPointerCapture(event.pointerId); modeLock(true);
});
for (const type of ['pointerup','pointercancel','lostpointercapture'])
  $('mode-lock').addEventListener(type, () => modeLock(false));
$('mode-lock').addEventListener('keydown', event => {
  if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); if (!event.repeat) modeLock(true); }
});
$('mode-lock').addEventListener('keyup', event => {
  if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); modeLock(false); }
});
document.addEventListener('keydown', event => {
  if (event.code === 'KeyL' && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault(); if (!event.repeat) modeLock(true);
  }
  const index = ['Digit1','Digit2','Digit3','Digit4','Digit5','Digit6','Digit7','Digit8'].indexOf(event.code);
  if (index >= 0 && available && modeLockHeld && !event.repeat && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault();
    send('/mode', {position:['AUTO','P','S','A','M','U1','U2','U3'][index]}).then(status);
  }
});
document.addEventListener('keyup', event => {
  if (event.code === 'KeyL') { event.preventDefault(); modeLock(false); }
});
document.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => {
  if (available && modeLockHeld) send('/mode', {position:button.dataset.mode}).then(status);
}));
for (const type of ['blur','pagehide']) window.addEventListener(type, () => { modeLockHeld = false; });
document.addEventListener('visibilitychange', () => { if (document.hidden) modeLockHeld = false; });
$('release').addEventListener('click', () => { modeLockHeld = false; });
setInterval(() => { if (modeLockHeld) send('/heartbeat', {}); }, 1000);
'''
    path.write_text(text,encoding='utf-8',newline='\n')
