"""Queued body GPIO and nine-position joystick adapter over the r20 console."""
from collections import deque
import hashlib
from pathlib import Path
import time

try:
    from .z62_encoder_queue import EncoderInputMixin
    from . import z62_extra_inputs as inputs
except ImportError:
    from z62_encoder_queue import EncoderInputMixin
    import z62_extra_inputs as inputs

VERSION='2026.10.30-extra-console-r21'
JOY_LEASE=63  # watchdog lease only; never a GPIO or a public key identifier


def initialize(machine):
    inputs.initialize(machine)
    machine._joystick_events=deque()
    machine._joystick_position='neutral'
    machine._joystick_requested='neutral'
    machine._joystick_next_tick=0


class ExtraInputMixin(EncoderInputMixin):
    def _drive_key_pin(self,pin,level):
        if pin in inputs.GPIO_KEYS:
            inputs.drive_gpio(self,pin,level)
        else:
            super()._drive_key_pin(pin,level)

    def set_key(self,pin,level):
        if type(pin) is not int or not 0 <= pin <= 29 or type(level) is not int or level not in (0,1):
            raise ValueError('Invalid body key input')
        with self.io:
            self._ready()
            self._set_key_locked(pin,level)

    def set_joystick(self,position):
        if not isinstance(position,str) or position not in inputs.JOY_PINS:
            raise ValueError('Invalid joystick position')
        with self.io:
            self._ready()
            previous=self._joystick_events[-1] if self._joystick_events else self._joystick_position
            if previous!=position:
                if len(self._joystick_events)>=64:
                    if position!='neutral':
                        raise ValueError('Joystick queue is full')
                    self._joystick_events.clear()
                self._joystick_events.append(position)
            self._joystick_requested=position
            if position=='neutral':
                self.requested_keys.discard(JOY_LEASE)
            else:
                self.requested_keys.add(JOY_LEASE)
                self.key_deadline=time.monotonic()+5
            self._advance_keys()

    def _advance_keys(self):
        super()._advance_keys()
        if not getattr(self,'_joystick_events',None):
            return
        ticks,frequency=self._key_clock()
        if ticks<self._joystick_next_tick:
            return
        position=self._joystick_events[0]
        inputs.drive_joystick(self,position)
        self._joystick_events.popleft()
        self._joystick_position=position
        self._joystick_next_tick=ticks+(frequency*15+99)//100

    def _release(self):
        try:
            if hasattr(self,'_body_gpio_ports'):
                for key in inputs.GPIO_KEYS:
                    if key in self.held or self._body_gpio_levels.get(key)==0:
                        inputs.drive_gpio(self,key,1)
                        self.held.discard(key)
            if hasattr(self,'_joystick_events'):
                self._joystick_events.clear()
                self._joystick_position=self._joystick_requested='neutral'
                self.requested_keys.discard(JOY_LEASE)
                inputs.drive_joystick(self,'neutral')
        finally:
            super()._release()

    def _extra_input_status(self):
        if not hasattr(self,'_joystick_events'):
            return {'known':False}
        return {'known':True,'gpio_levels':dict(self._body_gpio_levels),
                'joystick_position':self._joystick_position,
                'joystick_requested':self._joystick_requested,
                'queued_positions':len(self._joystick_events)}


def identity():
    return {'version':VERSION,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'gpio_input':inputs.identity(),'guest_software_patched':False,
            'photographic_functions_verified':False}


def apply_console(source):
    from reference_updates import replace_once
    path=source/'tools/z62_console.py'
    content=replace_once(path.read_text(encoding='utf-8'),
        'class Z62Machine(EncoderInputMixin, shared.Machine):',
        'from tools.z62_extra_console import ExtraInputMixin, initialize as initialize_extra_inputs\n\n\n'
        'class Z62Machine(ExtraInputMixin, shared.Machine):')
    content=replace_once(content,'        initialize_queue(self)',
        '        initialize_queue(self)\n        initialize_extra_inputs(self)')
    content=replace_once(content,"                elif self.path == '/rotate':",
        "                elif self.path == '/joystick':\n"
        "                    machine.set_joystick(request.get('position'))\n"
        "                elif self.path == '/rotate':")
    content=replace_once(content,'            state["encoder_input"] = self._encoder_status()',
        '            state["encoder_input"] = self._encoder_status()\n'
        '            state["extra_input"] = self._extra_input_status()\n'
        '        state["extra_input_adapter"] = '+repr(identity()))
    path.write_text(content,encoding='utf-8',newline='\n')
    for name in ('z62_extra_inputs.py','z62_extra_console.py'):
        (source/'tools'/name).write_bytes(Path(__file__).with_name(name).read_bytes())

    html=source/'web-z62/index.html'
    controls='<section class="body-key-group" aria-label="前侧与拍摄按键"><h2>前侧与拍摄按键</h2><div class="body-key-grid">'
    for pin,label,key in ((26,'AF-ON','A'),(27,'Fn1','F'),(28,'Fn2','G'),(29,'录像','V')):
        controls+=f'<button class="key" data-pin="{pin}" disabled>{label}<span class="key-detail">{key}</span></button>'
    controls+='</div><p class="body-input-note">按键已接入。当前无镜头；对焦、光圈和视频保存尚未验收。</p></section>'
    controls+='<section class="body-key-group" aria-label="独立对焦摇杆"><h2>独立对焦摇杆</h2><div class="joystick-grid">'
    for position,label in (('left-up','左上'),('up','向上'),('right-up','右上'),('left','向左'),
                           ('center','中央按压'),('right','向右'),('left-down','左下'),('down','向下'),('right-down','右下')):
        controls+=f'<button class="key" data-joystick="{position}" aria-label="摇杆{label}" disabled>{label}</button>'
    controls+='</div><p class="body-input-note">按住倾斜，松开回中。与上方多重选择器分开。</p></section>\n'
    html.write_text(replace_once(html.read_text(encoding='utf-8'),'      <button id="release"',
                                controls+'      <button id="release"'),encoding='utf-8',newline='\n')
    css=source/'web-z62/style.css'
    css.write_text(css.read_text(encoding='utf-8')+
        '\n.joystick-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:6px; }\n'
        '.joystick-grid .key { min-width:0; padding:12px 4px; font-size:12px; touch-action:none; }\n',
        encoding='utf-8',newline='\n')
    script=source/'web-z62/console.js'
    text=replace_once(script.read_text(encoding='utf-8'),'const shortcuts = {',
        'const shortcuts = {KeyA: 26, KeyF: 27, KeyG: 28, KeyV: 29, ')
    text=replace_once(text,"document.querySelectorAll('[data-pin], [data-encoder]').forEach(button => button.disabled = !available);",
        "document.querySelectorAll('[data-pin], [data-encoder], [data-joystick]').forEach(button => button.disabled = !available);")
    text+='''
let joystickHeld = null;
function joystickDown(position) {
  if (!available || joystickHeld !== null) return;
  joystickHeld = position;
  send('/joystick', {position});
}
function joystickUp(position) {
  if (joystickHeld !== position) return;
  joystickHeld = null;
  send('/joystick', {position:'neutral'});
}
document.querySelectorAll('[data-joystick]').forEach(button => {
  const position = button.dataset.joystick;
  button.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    event.preventDefault(); button.setPointerCapture(event.pointerId); joystickDown(position);
  });
  for (const type of ['pointerup','pointercancel','lostpointercapture'])
    button.addEventListener(type, () => joystickUp(position));
  button.addEventListener('keydown', event => {
    if (event.key === ' ' || event.key === 'Enter') {
      event.preventDefault(); if (!event.repeat) joystickDown(position);
    }
  });
  button.addEventListener('keyup', event => {
    if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); joystickUp(position); }
  });
  button.addEventListener('blur', () => joystickUp(position));
});
for (const type of ['blur','pagehide']) window.addEventListener(type, () => { joystickHeld = null; });
document.addEventListener('visibilitychange', () => { if (document.hidden) joystickHeld = null; });
$('release').addEventListener('click', () => { joystickHeld = null; });
setInterval(() => { if (joystickHeld !== null) send('/heartbeat', {}); }, 1000);
'''
    script.write_text(text,encoding='utf-8',newline='\n')
