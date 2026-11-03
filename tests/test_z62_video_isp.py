"""The experimental video path needs explicit, unambiguous software geometry."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))


class VideoIspTests(unittest.TestCase):
    def api(self):
        try:
            import run_z62_video_isp as host
            import z62_video_isp_device as device
        except ImportError as exc:
            self.fail('Explicit video device integration is missing: '+str(exc))
        return host,device

    def test_origin_is_required_even_and_bounded(self):
        host,_=self.api()
        for origin in (None,(1,76),(0,77),(0,4098),('0',76),(0,),[False,76]):
            with self.subTest(origin=origin),self.assertRaises(ValueError):
                host.configure_command(['qemu'],video=True,origin=origin)
        command=host.configure_command(['qemu'],video=True,origin=(0,76))
        self.assertIn('nikon-z72-boot-config.z62-video-isp=on',command)
        self.assertIn('nikon-z72-boot-config.z62-video-origin-x=0',command)
        self.assertIn('nikon-z72-boot-config.z62-video-origin-y=76',command)

    def test_default_has_no_implicit_video_or_origin(self):
        host,_=self.api()
        command=host.configure_command(['qemu'])
        self.assertFalse(any('.z62-video-' in item for item in command))
        with self.assertRaises(ValueError):
            host.configure_command(['qemu'],origin=(0,76))

    def test_duplicate_video_properties_reject_instead_of_shadowing(self):
        host,_=self.api()
        with self.assertRaises(ValueError):
            host.configure_command(['qemu','-global','nikon-z72-boot-config.z62-video-isp=off'],
                                   video=True,origin=(0,76))

    def test_adapter_rejects_a_changed_parent_without_mutating_input(self):
        _,device=self.api()
        source=ROOT/'.build/z62-photo-results-2026.11.03-r53/source/qemu-10.2.4/hw/arm'
        files={name:(source/name).read_bytes() for name in device.INPUTS}
        original=dict(files)
        first=next(iter(files)); files[first]=files[first]+b'\n'
        with self.assertRaises(ValueError): device.render(files)
        self.assertEqual(original[first],(source/first).read_bytes())
