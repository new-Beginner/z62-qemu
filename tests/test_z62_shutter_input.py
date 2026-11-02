"""Exercise real queued key methods and cancellation with the new GPIO route."""
import ast
from collections import deque
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from z62_shutter_input import ShutterInputMixin
from z62_shutter_input_v2 import apply_console


def extract_methods(path, class_name, names):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    module = ast.Module(body=[n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names],
                        type_ignores=[])
    scope = {'deque': deque, 'time': time}
    exec(compile(module, str(path), 'exec'), scope)
    return {n: scope[n] for n in names}


class ShutterInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        stage = Path(self.temp.name)
        reference = ROOT / 'third_party/z62-qemu'
        for relative in ('tools/z62_console.py', 'web-z62/index.html', 'web-z62/console.js'):
            dest = stage / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(reference / relative, dest)
        apply_console(stage)
        self.stage = stage
        parent = type('Parent', (), extract_methods(reference / 'tools/web_console.py', 'Machine', ('_release',)))
        methods = extract_methods(stage / 'tools/z62_console.py', 'Z62Machine', ('_set_key_locked', '_advance_keys'))
        cls = type('Console', (ShutterInputMixin, parent), methods)
        self.machine = cls()
        self.machine.io = threading.RLock()
        self.machine.held = set()
        self.machine.requested_keys = set()
        self.machine.key_events = {}
        self.machine.next_key_ticks = {}
        self.machine.ticks = 0
        self.commands = []
        self.machine._key_clock = lambda: (self.machine.ticks, 1000)
        self.machine._qtest = self.commands.append
        self.machine._ready = lambda: None

    def test_short_click_preserves_both_edges_for_guest_scan(self):
        m = self.machine
        m.set_key(24, 0)
        m.set_key(24, 1)
        self.assertEqual(len(self.commands), 1)
        self.assertIn(24, m.held)
        m.ticks = 149
        m._advance_keys()
        self.assertEqual(len(self.commands), 1)
        m.ticks = 150
        m._advance_keys()
        self.assertEqual(self.commands, [
            'set_irq_in /machine/controller/keys-gpio unnamed-gpio-in 1 0',
            'set_irq_in /machine/controller/keys-gpio unnamed-gpio-in 1 1'])
        self.assertFalse(m.held)
        self.assertFalse(m.key_events)

    def test_focus_loss_releases_gpio_and_expander_and_cancels_pending_clicks(self):
        m = self.machine
        m.set_key(24, 0)
        m.set_key(9, 0)
        m.set_key(24, 1)
        m._release()
        self.assertFalse(m.held or m.key_events or m.requested_keys or m.next_key_ticks)
        self.assertEqual(self.commands[-2:], [
            'set_irq_in /machine/controller/keys-gpio unnamed-gpio-in 1 1',
            'set_irq_in /machine/peripheral/keys pins 9 1'])
        n = len(self.commands)
        m.ticks = 10000
        m._advance_keys()
        self.assertEqual(len(self.commands), n)

    def test_old_raw_input_is_not_silently_remapped(self):
        self.machine.set_key(0, 0)
        self.assertEqual(self.commands, ['set_irq_in /machine/peripheral/keys pins 0 0'])

    def test_invalid_identifiers_cannot_drive_gpio(self):
        for pin, level in ((True, 0), (-1, 0), (25, 0), ('24', 0), (24, True), (24, 2)):
            with self.subTest(pin=pin, level=level), self.assertRaises(ValueError):
                self.machine.set_key(pin, level)
        self.assertEqual(self.commands, [])

    def test_browser_and_keyboard_use_the_same_half_press(self):
        html = (self.stage / 'web-z62/index.html').read_text(encoding='utf-8')
        js = (self.stage / 'web-z62/console.js').read_text(encoding='utf-8')
        self.assertIn('data-pin="24"', html)
        self.assertNotIn('>EXIT ', html)
        self.assertIn('KeyX: 24,', js)
        compile((self.stage / 'tools/z62_console.py').read_text(encoding='utf-8'), 'console', 'exec')

    def test_both_body_stages_are_released_before_guest_continuation(self):
        tree = ast.parse((self.stage / 'tools/z62_console.py').read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Z62Machine')
        start = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_start')
        index = next(i for i, n in enumerate(start.body) if isinstance(n, ast.Expr)
                     and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)
                     and n.value.func.id == 'initialize_inputs')
        calls = []
        scope = {'self': SimpleNamespace(remote='remote', wire='wire'),
                 'initialize_inputs': lambda *a, **kw: calls.append(('initial', a)),
                 'shutter_qtest': lambda wire, cmd: calls.append((wire, cmd))}
        block = ast.Module(body=start.body[index:index+2], type_ignores=[])
        exec(compile(block, 'actual-generated-startup', 'exec'), scope)
        self.assertEqual(calls, [('initial', ('remote', 'wire')),
            ('wire', 'set_irq_in /machine/controller/keys-gpio unnamed-gpio-in 1 1'),
            ('wire', 'set_irq_in /machine/controller/keys-gpio unnamed-gpio-in 13 1')])
        # The selected block must precede debugger detach, which starts the CPUs.
        remainder = ast.unparse(ast.Module(body=start.body[index+2:], type_ignores=[]))
        self.assertIn("self.remote.command('D')", remainder)


if __name__ == '__main__':
    unittest.main()
