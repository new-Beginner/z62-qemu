from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class PreviewResultConfigTests(unittest.TestCase):
    def api(self):
        try:
            import probe_z62_preview_result_config as api
        except ImportError as exc:
            self.fail('Physical preview configuration reader is missing: ' + str(exc))
        return api

    def test_reads_three_actual_submit_registers_and_bounded_ram_parameters(self):
        api = self.api()
        rows = {}
        for address, pointer in ((0x201009E0, 0xC2200000), (0x20100940, 0xC2201000),
                                  (0x20100BA0, 0xC2202000)):
            rows[(address, 24)] = struct.pack('<6I', 0, 3, 0x200087E0, 0x88000, pointer, 0)
            rows[(pointer, 160)] = bytes(range(160))
        class Memory:
            def read(self, address, size):
                return rows[(address, size)]
        got = api.configuration(Memory())
        self.assertEqual([x['physical_unit'] for x in got], [54, 49, 55])
        self.assertEqual(got[1]['parameter_pointer'], '0xc2201000')
        self.assertEqual(got[2]['parameters_0a0'], bytes(range(160)).hex())
        self.assertFalse(got[0]['hardware_completion_verified'])

    def test_non_ram_and_short_parameters_are_not_invented(self):
        api = self.api()
        class Memory:
            def read(self, address, size):
                if size == 24:
                    return struct.pack('<6I', 0, 0, 0, 0, 0x20100000, 0)
                raise AssertionError('A device address must not be followed as RAM')
        got = api.configuration(Memory())
        self.assertFalse(any(x['parameters_available'] for x in got))
        class Short:
            def read(self, address, size):
                return bytes(size-1)
        with self.assertRaises(ValueError):
            api.configuration(Short())
