"""Offline error-report tests; imports do not open WPD or USB."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import read_z62_device_info as probe


class ErrorRecordTests(unittest.TestCase):
    def test_python_failure_is_not_hresult_success(self):
        self.assertEqual(probe.error_record(ValueError('private payload')),
                         {'type':'ValueError','hresult':None})

    def test_hresult_preserved_without_private_message(self):
        error=OSError('private device serial')
        error.hresult=-2147024891
        result=probe.error_record(error)
        self.assertEqual(result['hresult'],'0x80070005')
        self.assertNotIn('private',str(result))

    def test_driver_result_exception_keeps_hresult(self):
        error=probe.WpdCommandError(0x80070005)
        self.assertEqual(probe.error_record(error)['hresult'],'0x80070005')

    def test_parser_still_self_tests_offline(self):
        probe.self_test()


if __name__=='__main__':
    unittest.main()
