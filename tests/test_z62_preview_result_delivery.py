from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))


class PreviewResultDeliveryTests(unittest.TestCase):
    def api(self):
        try:
            import trace_z62_preview_result_delivery as api
        except ImportError as exc:
            self.fail('Native result delivery observer is missing: '+str(exc))
        return api

    def test_native_callback_and_publication_read_actual_counter_without_changing_it(self):
        api = self.api()
        raw = struct.pack('<10I', 0, 2, 3, 0, 0, 7, 0, 0, 0, 0)
        class Memory:
            def read(self, address, size):
                if address in api.ANCHORS:
                    return bytes.fromhex(api.ANCHORS[address])
                self_case.assertEqual((address, size), (0xC1864864, 40))
                return raw
        self_case = self
        got = api.capture(Memory(), {'pc': api.CALLBACK, 'r0': 0x42193082, 'r1': 2})
        self.assertEqual(got['message_code_raw'], 0x42193082)
        self.assertEqual(got['argument1_raw'], 2)
        self.assertEqual(got['native_result_count_before_or_at_point'], 7)
        got = api.capture(Memory(), {'pc': api.PUBLICATION, 'r0': 0xC18647EC, 'r1': 4})
        self.assertTrue(got['is_result_event_object'])
        self.assertEqual(got['event_mask_raw'], 4)
        self.assertEqual(got['native_result_count_before_or_at_point'], 7)
        self.assertEqual(raw, struct.pack('<10I', 0, 2, 3, 0, 0, 7, 0, 0, 0, 0))

    def test_wrong_code_and_short_counter_reads_cannot_report_a_delivery(self):
        api = self.api()
        class Wrong:
            def read(self, address, size):
                return bytes(size)
        got = api.capture(Wrong(), {'pc': api.PUBLICATION})
        self.assertFalse(got['source_instruction_matches'])
        self.assertNotIn('is_result_event_object', got)
        class Short:
            def read(self, address, size):
                return bytes.fromhex(api.ANCHORS[address]) if size == 4 else bytes(size-1)
        with self.assertRaises(ValueError):
            api.capture(Short(), {'pc': api.PUBLICATION, 'r0': 0xC18647EC, 'r1': 4})
