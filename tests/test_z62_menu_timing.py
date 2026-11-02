# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline tests; never connect a camera or start QEMU."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from probe_z62_menu_timing import classify
from trace_z62_capture_waits import signed32


class TimingEvidenceTests(unittest.TestCase):
    def test_empty_is_not_success(self):
        r=classify([])
        self.assertIsNone(r['first_0x3f'])
        self.assertFalse(r['menu_observed'])
        self.assertFalse(r['reopened_observed'])

    def test_after_request_error_is_not_before_request(self):
        r=classify([{'stage':'before-menu','status_codes':[]},
                    {'stage':'after-first-menu','status_codes':[63],'virtual_seconds':4}])
        self.assertFalse(r['observed_0x3f_before_menu'])
        self.assertEqual(r['first_0x3f']['virtual_seconds'],4)

    def test_background_error_is_distinguished(self):
        r=classify([{'stage':'before-menu','status_codes':[63]}])
        self.assertTrue(r['observed_0x3f_before_menu'])

    def test_menu_requires_display(self):
        self.assertFalse(classify([{'stage':'after-first-menu','index':1,
                                  'display_enabled':False}])['menu_observed'])

    def test_first_menu_does_not_imply_reopen(self):
        r=classify([{'stage':'after-first-menu','index':1,'display_enabled':True},
                    {'stage':'after-reopen','index':3,'display_enabled':True}])
        self.assertTrue(r['menu_observed'])
        self.assertFalse(r['reopened_observed'])

    def test_reopen_can_coexist_with_error(self):
        r=classify([{'stage':'after-reopen','index':1,'display_enabled':True,
                    'status_codes':[63]}])
        self.assertTrue(r['reopened_observed'])
        self.assertIsNotNone(r['first_0x3f'])

    def test_signed_kernel_return(self):
        self.assertEqual(signed32(0xffffffce),-50)
        self.assertEqual(signed32(0xffffffff),-1)
        self.assertEqual(signed32(0),0)
        self.assertEqual(signed32(0x7fffffff),2147483647)


if __name__=='__main__':
    unittest.main()
