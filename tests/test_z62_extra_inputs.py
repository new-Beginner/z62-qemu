"""Actual shared input queue composition, GPIO release and joystick isolation."""
from collections import deque
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from test_z62_shutter_input import extract_methods
import z62_extra_inputs as inputs
import z62_extra_console as extra
import z62_shutter_input_v2 as shutter
import z62_capture_input as capture
import z62_body_controls as body
import z62_encoder_queue as encoder
import z62_encoder_labels as labels


class ExtraInputTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        stage=Path(temporary.name)
        reference=ROOT/'third_party/z62-qemu'
        for name in ('tools/z62_console.py','web-z62/index.html','web-z62/console.js','web-z62/style.css'):
            target=stage/name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(reference/name,target)
        for adapter in (shutter,capture,body,encoder,labels,extra):
            adapter.apply_console(stage)
        self.stage=stage
        parent=type('Parent',(),extract_methods(reference/'tools/web_console.py','Machine',('_release',)))
        methods=extract_methods(stage/'tools/z62_console.py','Z62Machine',('_set_key_locked','_advance_button_keys'))
        cls=type('Console',(extra.ExtraInputMixin,parent),methods)
        self.m=cls()
        m=self.m
        m.io=threading.Lock()
        m.held,m.requested_keys=set(),set()
        m.key_events,m.next_key_ticks={},{}
        m.ticks=0
        m._ready=lambda:None
        m._key_clock=lambda:(m.ticks,1000)
        m._body_gpio_ports={config['port']:{'path':f"/gpio-{config['port']:x}"} for config in inputs.GPIO_KEYS.values()}
        m._body_gpio_levels={key:1 for key in inputs.GPIO_KEYS}
        m._body_stages={24:1,25:1}
        m._encoder_events=deque()
        m._encoder_phases={0:0,1:0}
        m._encoder_due=m._encoder_edges=m._encoder_cancel_requests=0
        m._joystick_events=deque()
        m._joystick_position=m._joystick_requested='neutral'
        m._joystick_next_tick=0
        self.levels=0xffffff
        self.commands=[]
        def qtest(command):
            self.commands.append(command)
            parts=command.split()
            if parts[1]=='/machine/peripheral/keys':
                pin,level=map(int,parts[-2:])
                self.levels=(self.levels&~(1<<pin))|(level<<pin)
        def query(command,args):
            self.assertEqual(args['property'],'input-levels')
            if command=='qom-get':
                return self.levels
            self.assertEqual(command,'qom-set')
            self.levels=args['value']
        m._qtest=qtest
        m.qmp=SimpleNamespace(command=query)

    def test_four_gpio_clicks_use_real_button_queue(self):
        for key,config in inputs.GPIO_KEYS.items():
            self.m.set_key(key,0)
            self.m.set_key(key,1)
            self.assertEqual(self.m._body_gpio_levels[key],0)
            self.m.ticks+=150
            self.m._advance_keys()
            self.assertEqual(self.m._body_gpio_levels[key],1)
            self.assertNotIn(key,self.m.held)
            self.assertIn(f"unnamed-gpio-in {config['pin']} 0",self.commands[-2])
        self.assertFalse(any('/machine/peripheral/keys' in command for command in self.commands))

    def test_joystick_preserves_menu_and_uses_watchdog_lease(self):
        m=self.m
        m.set_key(9,0)
        m.set_joystick('right-up')
        self.assertIn(extra.JOY_LEASE,m.requested_keys)
        self.assertFalse(self.levels&(1<<9))
        self.assertEqual(self.levels&inputs.JOY_MASK,
                         inputs.joystick_levels(0xffffff,'right-up')&inputs.JOY_MASK)
        m.set_joystick('neutral')
        m.ticks=150
        m._advance_keys()
        self.assertNotIn(extra.JOY_LEASE,m.requested_keys)
        self.assertIn(9,m.held)
        self.assertEqual(self.levels&inputs.JOY_MASK,inputs.JOY_MASK)
        self.assertFalse(self.levels&(1<<9))

    def test_short_center_click_holds_for_guest_debounce(self):
        self.m.set_joystick('center')
        self.m.set_joystick('neutral')
        self.assertEqual(self.m._joystick_position,'center')
        self.m.ticks=149
        self.m._advance_keys()
        self.assertEqual(self.m._joystick_position,'center')
        self.m.ticks=150
        self.m._advance_keys()
        self.assertEqual(self.m._joystick_position,'neutral')

    def test_release_clears_all_gpio_joystick_and_queued_events(self):
        self.m.set_key(26,0)
        self.m.set_key(27,0)
        self.m.set_key(9,0)
        self.m.set_joystick('left-down')
        self.m.set_joystick('center')
        self.m._release()
        self.assertEqual(self.levels,0xffffff)
        self.assertEqual(self.m._body_gpio_levels,{26:1,27:1,28:1,29:1})
        self.assertFalse(self.m.held or self.m.requested_keys or self.m.key_events or self.m._joystick_events)
        self.m.ticks=1000
        self.m._advance_keys()
        self.assertEqual(self.levels,0xffffff)
        self.assertFalse(any(' pins 26 ' in command or ' pins 63 ' in command for command in self.commands))

    def test_invalid_inputs_do_not_change_signals(self):
        for position in (None,True,[],'unknown'):
            with self.assertRaises(ValueError):
                self.m.set_joystick(position)
        for pin,level in ((True,0),(30,0),(29,True)):
            with self.assertRaises(ValueError):
                self.m.set_key(pin,level)
        self.assertEqual(self.levels,0xffffff)
        self.assertFalse(self.commands)

    def test_staged_ui_contains_separate_joystick_and_original_keys(self):
        import ast
        html=(self.stage/'web-z62/index.html').read_text(encoding='utf-8')
        for position in inputs.JOY_WIRE:
            self.assertEqual(html.count(f'data-joystick="{position}"'),1)
        for pin in (24,25,26,27,28,29):
            self.assertEqual(html.count(f'data-pin="{pin}"'),1)
        ast.parse((self.stage/'tools/z62_console.py').read_text(encoding='utf-8'))


if __name__=='__main__':
    unittest.main()
