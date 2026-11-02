"""Adapter integrity and host diagnostics; native DMA behavior has its own qtest."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import z62_finite_stats_device as device
from run_z62_finite_stats import configure_command
from z62_finite_stats_status import finite_stats_status


class FiniteStatsTests(unittest.TestCase):
    def test_adapter_hash_bound_and_default_off(self):
        root = ROOT/'.build/z62-raw-stream-2026.10.29-r7/source/qemu-10.2.4/hw/arm'
        inputs = {n:(root/n).read_bytes() for n in device.INPUTS}
        outputs = device.render(inputs)
        self.assertIn('s->finite_source = dst[0]', outputs['nikon-z62-functional-raw.h'])
        self.assertIn('functional_finite_stats, false)', outputs['nikon-z72-input-config.c'])
        self.assertIn('z62_finite_stats, false)', outputs['nikon-z72.c'])
        self.assertEqual(outputs['nikon-z72.c'].count('finite_bridge_control(s, address, value);'),3)
        inputs['nikon-z72.c'] += b'\n'
        with self.assertRaisesRegex(ValueError,'SHA mismatch'):
            device.render(inputs)

    def test_launch_is_explicit_idempotent_and_does_not_mutate_caller(self):
        command = ['qemu-system-arm.exe','-S']
        self.assertEqual(configure_command(command, False), command)
        enabled = configure_command(command)
        self.assertEqual(configure_command(enabled), enabled)
        self.assertEqual(command,['qemu-system-arm.exe','-S'])
        self.assertFalse(any('laboratory-metadata-completion' in a for a in enabled))

    def test_missing_counter_is_unknown(self):
        machine = SimpleNamespace(qmp=SimpleNamespace(command=Mock(side_effect=ValueError('missing'))))
        result = finite_stats_status(machine)['finite_stats_status']
        self.assertFalse(result['known'])
        self.assertEqual(result['engines']['master'],{})
        self.assertFalse(result['silicon_metering_verified'])
        self.assertFalse(result['live_view_verified'])
        self.assertTrue(all(c.args[0]=='qom-get' for c in machine.qmp.command.call_args_list))


if __name__ == '__main__':
    unittest.main()
