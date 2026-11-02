"""Exercise the real console key queue with coupled two-stage shutter inputs."""
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_z62_shutter_input import extract_methods
from z62_shutter_input_v2 import apply_console as apply_shutter
from z62_capture_input import CaptureInputMixin, apply_console


class CaptureInputTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        stage = Path(temp.name)
        reference = ROOT / 'third_party/z62-qemu'
        for name in ('tools/z62_console.py', 'web-z62/index.html', 'web-z62/console.js'):
            dest = stage / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(reference / name, dest)
        apply_shutter(stage)
        apply_console(stage)
        parent = type('Parent', (), extract_methods(reference / 'tools/web_console.py', 'Machine', ('_release',)))
        methods = extract_methods(stage / 'tools/z62_console.py', 'Z62Machine', ('_set_key_locked', '_advance_keys'))
        cls = type('Console', (CaptureInputMixin, parent), methods)
        self.m = cls()
        self.m.io = threading.RLock()
        self.m.held, self.m.requested_keys = set(), set()
        self.m.key_events, self.m.next_key_ticks = {}, {}
        self.m.ticks = 0
        self.commands = []
        self.enabled = True
        self.m._qtest = self.commands.append
        self.m._ready = lambda: None
        self.m._key_clock = lambda: (self.m.ticks, 1000)
        self.m.qmp = SimpleNamespace(command=self.query)

    def query(self, command, args):
        if command == 'qom-list':
            return [{'name': x, 'type': 'child<nikon-z72-boot-config>'} for x in ('master', 'slave')]
        if args['property'] == 'master-role':
            return args['path'].endswith('/master')
        return self.enabled

    def test_full_click_closes_half_first_and_releases_full_first(self):
        m = self.m
        m.set_key(25, 0)
        m.set_key(25, 1)
        self.assertEqual(len(self.commands), 4)
        m.ticks = 150
        m._advance_keys()
        self.assertEqual(self.commands, [
            'set_irq_in /machine/controller/keys-gpio unnamed-gpio-in 1 0',
            'set_irq_in /machine/unattached/master capture-contact 0 1',
            'set_irq_in /machine/controller/keys-gpio unnamed-gpio-in 13 0',
            'set_irq_in /machine/unattached/master capture-contact 1 1',
            'set_irq_in /machine/controller/keys-gpio unnamed-gpio-in 13 1',
            'set_irq_in /machine/unattached/master capture-contact 1 0',
            'set_irq_in /machine/controller/keys-gpio unnamed-gpio-in 1 1',
            'set_irq_in /machine/unattached/master capture-contact 0 0'])

    def test_manual_half_survives_full_release(self):
        m = self.m
        m.set_key(24, 0)
        m.set_key(25, 0)
        m.ticks = 200
        m.set_key(25, 1)
        self.assertEqual(m._body_contact_levels, (0, 1))
        self.assertIn(24, m.held)
        self.assertEqual(self.commands[-1], 'set_irq_in /machine/unattached/master capture-contact 1 0')

    def test_focus_loss_releases_both_and_cancels_pending_events(self):
        m = self.m
        m.set_key(25, 0)
        m.set_key(25, 1)
        m._release()
        self.assertFalse(m.held or m.key_events or m.requested_keys)
        self.assertEqual(m._body_contact_levels, (1, 1))
        before = list(self.commands)
        m.ticks = 1000
        m._advance_keys()
        self.assertEqual(self.commands, before)

    def test_missing_capture_hardware_prevents_any_body_write(self):
        self.enabled = False
        with self.assertRaises(ValueError):
            self.m.set_key(25, 0)
        self.assertFalse(self.commands)

    def test_invalid_input_cannot_drive_pins(self):
        for pin, level in ((True, 0), (26, 0), (-1, 0), (25, True), (25, 2)):
            with self.subTest(pin=pin, level=level), self.assertRaises(ValueError):
                self.m.set_key(pin, level)
        self.assertFalse(self.commands)


if __name__ == '__main__':
    unittest.main()
