"""Read-only boot-wait diagnostic unit tests; not firmware behavior coverage."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'fenestra/z62'))
import observe_boot_wait as boot


class BootWaitTests(unittest.TestCase):
    def test_windows_are_bounded(self):
        self.assertEqual(boot.check_windows([1, 5, 15]), [1.0, 5.0, 15.0])
        for values in ([], [0], [-1], [float('nan')], [float('inf')], [121], [1] * 5):
            with self.subTest(values=values), self.assertRaises(ValueError):
                boot.check_windows(values)

    def test_profiles_are_explicit(self):
        for profile in ('minimal', 'controller', 'controller-link'):
            cmd = boot.build_command(Path('Q:/'), profile, 12345, 12346)
            self.assertIn('-nic', cmd)
            self.assertIn('none', cmd)
            self.assertNotIn('-qtest', cmd)
            self.assertNotIn('-global', cmd)
            self.assertNotIn('-drive', cmd)
            self.assertEqual(sum(x.startswith('loader,') for x in cmd), 4)
        with self.assertRaises(ValueError):
            boot.build_command(Path('Q:/'), 'bench', 12345, 12346)
        a = boot.build_command(Path('Q:/'), 'controller', 12345, 12346)
        b = boot.build_command(Path('Q:/'), 'controller-link', 12345, 12346)
        self.assertEqual(a[2] + ',controller-link=on', b[2])
        self.assertNotIn('battery-peer', b[2])

    def test_rom_window_must_match_original(self):
        image = bytes(range(128))
        row = boot.code_window(image, boot.BASE + 32, False, image[16:80])
        self.assertTrue(row['matches_original'])
        with self.assertRaises(ValueError):
            boot.code_window(image, boot.BASE + 32, False, bytes(64))
        with self.assertRaises(ValueError):
            boot.code_window(image, boot.BASE - 1, False, bytes(64))

    def test_interrupt_is_audited(self):
        remote = object.__new__(boot.BootRemote)
        with patch.object(boot.ReadOnlyRemote, 'interrupt', return_value='T02thread:01;'):
            self.assertEqual(remote.interrupt(), 'T02thread:01;')
        self.assertEqual(remote.controls, ['interrupt'])

    def test_write_commands_are_rejected(self):
        remote = object.__new__(boot.BootRemote)
        for command in ('G00', 'P0=00', 'M10020000,1:ff', 's', 'Hc1', 'qRcmd,00'):
            with self.subTest(command=command), self.assertRaises(ValueError):
                remote.command(command)

    def test_original_scheduler_literals_and_tamper(self):
        images = boot.read_inputs()
        expected = {'master': (0xC2B2A934, 0xC2B2A944),
                    'slave': (0xC189F6B0, 0xC189F6C0)}
        for role, image in images.items():
            points = boot.scheduler_points(image, role)
            self.assertEqual((points['current'], points['ready']), expected[role])
            bad = bytearray(image)
            bad[points['loop'] - boot.BASE] ^= 1
            with self.assertRaises(ValueError):
                boot.scheduler_points(bad, role)

    def test_qmp_mutations_are_rejected(self):
        session = boot.BootSession()
        for command, arguments in (('system_reset', None), ('cont', None),
                ('qom-set', {'path': '/', 'property': 'x', 'value': 1}),
                ('human-monitor-command', {'command-line': 'set_link x on'})):
            with self.subTest(command=command), self.assertRaises(ValueError):
                session.query(command, arguments)


if __name__ == '__main__':
    unittest.main()
