"""Adapter and status integrity; pixel/DMA behavior is tested natively."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import z62_preview_device as device
from run_z62_preview import configure_command
from z62_preview_status import preview_status
import probe_z62_preview_cycle as cycle


class PreviewTests(unittest.TestCase):
    def test_hash_bound_source_and_default_off(self):
        root=ROOT/'.build/z62-finite-stats-2026.10.29-r8/source/qemu-10.2.4/hw/arm'
        inputs={n:(root/n).read_bytes() for n in device.INPUTS}
        rendered=device.render(inputs)
        self.assertIn('z62_preview, false)',rendered['nikon-z72.c'])
        self.assertIn('preview_source_notify(s)',rendered['nikon-z62-raw-stream.h'])
        self.assertIn('.minimum_version_id = 42',rendered['nikon-z72.c'])
        inputs['nikon-z72.c']+=b'\n'
        with self.assertRaisesRegex(ValueError,'SHA mismatch'): device.render(inputs)

    def test_only_explicit_idempotent_enable(self):
        command=['qemu-system-arm.exe','-S']
        self.assertEqual(configure_command(command,False),command)
        enabled=configure_command(command)
        self.assertEqual(configure_command(enabled),enabled)
        self.assertEqual(command,['qemu-system-arm.exe','-S'])
        self.assertEqual(enabled[-1],'nikon-z72-boot-config.z62-preview=on')

    def test_absent_diagnostics_stay_unknown(self):
        machine=SimpleNamespace(qmp=SimpleNamespace(command=Mock(side_effect=ValueError('missing'))))
        result=preview_status(machine)['preview_status']
        self.assertFalse(result['known'])
        self.assertEqual(result['engines'],{})
        self.assertFalse(result['statistics_bank0_completed'])
        self.assertFalse(result['silicon_pixel_math_verified'])

    def test_empty_device_list_is_not_known(self):
        machine=SimpleNamespace(qmp=SimpleNamespace(command=Mock(return_value=[])))
        self.assertFalse(preview_status(machine)['preview_status']['known'])

    def test_existing_cycle_evidence_is_never_relabelled(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            report=path/'report.json'
            report.write_bytes(b'{"prior":true}')
            with self.assertRaises(FileExistsError): cycle.run(SimpleNamespace(output=path))
            self.assertEqual(report.read_bytes(),b'{"prior":true}')


if __name__=='__main__': unittest.main()
