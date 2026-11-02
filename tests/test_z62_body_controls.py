"""Verify composed staging and firmware-specific body bindings."""
import ast
from html.parser import HTMLParser
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools')]
import z62_body_controls as body
import z62_shutter_input_v2 as shutter
import z62_capture_input as capture
import export_z62_body_contract as contract


class Buttons(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pins = []
        self.body = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'button' and 'data-pin' in attrs:
            self.pins.append(int(attrs['data-pin']))
            if 'data-body-control' in attrs:
                self.body[attrs['data-body-control']] = int(attrs['data-pin'])


class BodyControlTests(unittest.TestCase):
    def test_staged_controls_preserve_existing_shutter_and_directions(self):
        reference = ROOT / 'third_party/z62-qemu'
        names = ('tools/z62_console.py', 'web-z62/index.html', 'web-z62/console.js', 'web-z62/style.css')
        before = {name: (reference / name).read_bytes() for name in names}
        with tempfile.TemporaryDirectory() as folder:
            stage = Path(folder)
            for name in names:
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(reference / name, target)
            shutter.apply_console(stage)
            capture.apply_console(stage)
            body.apply_console(stage)
            buttons = Buttons()
            buttons.feed((stage / 'web-z62/index.html').read_text(encoding='utf-8'))
            self.assertEqual(len(buttons.pins), len(set(buttons.pins)))
            self.assertEqual(set(buttons.pins), {1,2,3,4,5,6,7,8,9,10,18,19,21,22,23,24,25})
            self.assertEqual(buttons.body['delete'], 23)
            self.assertEqual(buttons.body['iso'], 19)
            script = (stage / 'web-z62/console.js').read_text(encoding='utf-8')
            self.assertIn('ArrowLeft: 7, ArrowRight: 6', script)
            self.assertIn('KeyX: 24, KeyS: 25,', script)
            self.assertIn("window.addEventListener('blur', releaseAll)", script)
            ast.parse((stage / 'tools/z62_console.py').read_text(encoding='utf-8'))
        self.assertEqual(before, {name: (reference / name).read_bytes() for name in names})

    def test_labels_match_identity_checked_original_name_table(self):
        recovered = {row['pin']: row for row in contract.recover()['routes']}
        names = {'play':'PLAY', 'delete':'DELETE', 'release-mode':'RELEASE_MODE', 'i':'I',
                 'iso':'ISO', 'exposure-compensation':'EXP_CORRECT', 'disp':'DISP',
                 'zoom-in':'ZOOM', 'zoom-out':'THUMBNAIL'}
        for key, label, pin, code, shortcut, group in body.CONTROLS:
            row = recovered[pin]
            self.assertEqual(row['name'], f"ID_SW{row['switch_word']}_{names[key]}")
        self.assertEqual(len({row[3] for row in body.CONTROLS}), len(body.CONTROLS))

    def test_identity_does_not_claim_full_camera_or_unobserved_features(self):
        identity = body.identity()
        self.assertFalse(identity['guest_software_patched'])
        self.assertFalse(identity['complete_body_controls'])
        self.assertTrue(all(row['functional_acceptance'] == 'pending' for row in identity['controls']))


if __name__ == '__main__':
    unittest.main()
