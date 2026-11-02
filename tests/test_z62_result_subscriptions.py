"""Keep raw result subscriptions distinct from hardware and software success."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class Memory:
    def __init__(self, rows):
        self.rows, self.reads = rows, []

    def read(self, address, size):
        self.reads.append((address, size))
        return self.rows[(address, size)]


class ResultSubscriptionsTests(unittest.TestCase):
    def api(self):
        try:
            import trace_z62_result_subscriptions as api
        except ImportError as exc:
            self.fail('Result subscription observer is missing: ' + str(exc))
        return api

    def state_rows(self, api, pc):
        return {(pc, 4): bytes.fromhex(api.ANCHORS[pc]),
                (0xC180954C, 20): struct.pack('<5I', 0xC2200000, 0, 0x1038AD1F, 0x1038AD1B, 0x61),
                (0xC1809500, 60): struct.pack('<15I', 0x102E47B1, 0x102E47AB, 0x102E47A5,
                                             0, 0, 0x70, 0x80, 1, 2, 4, 8, 16, 32, 64, 128),
                (0xC1D521C8, 96): bytes(96),
                (0xC1D52268, 96): struct.pack('<24I', *range(24)),
                (0x2010000C, 12): struct.pack('<3I', 1, 0x71, 0x3FF7FFC)}

    def test_wait_retains_distinct_hardware_selection_and_software_forwarding(self):
        api = self.api()
        mem = Memory(self.state_rows(api, api.WAIT))
        got = api.capture(mem, {'pc': api.WAIT})
        self.assertEqual(got['forward_mask_raw'], 0x61)
        self.assertEqual(got['hardware_masks_raw'], [1, 0x71, 0x3FF7FFC])
        self.assertEqual(got['result_dispatch_callback'], '0x1038ad1b')
        self.assertEqual(got['result_translation_rows'][5], [15, 16, 17])
        self.assertFalse(got['hardware_completion_verified'])
        self.assertFalse(any(a in (0x20100018, 0x2010001C, 0x203C0024) for a, _ in mem.reads))

    def test_mask_store_point_reports_the_native_result_without_writing_it(self):
        api = self.api()
        mem = Memory(self.state_rows(api, api.MASK_STORED))
        got = api.capture(mem, {'pc': api.MASK_STORED, 'r0': 0x1, 'r1': 0x61})
        self.assertTrue(got['native_stored_mask_matches_r1'])
        self.assertEqual(got['forward_mask_raw'], 0x61)
        self.assertFalse(got['guest_software_written_by_host'])

    def test_library_handoff_keeps_81_and_82_and_their_callbacks_separate(self):
        api = self.api()
        raw = bytearray(32)
        struct.pack_into('<I', raw, 0x14, 0xC2200100)
        for mode, code, callback in ((0, 0x42193081, '0x10263d09'),
                                      (1, 0x42193082, '0x10263d4d')):
            with self.subTest(mode=mode):
                rows = {(api.HANDOFF, 4): bytes.fromhex(api.ANCHORS[api.HANDOFF]),
                        (0xC2200000, 32): bytes(raw),
                        (0xC2200100, 12): struct.pack('<3I', 0, 0x10263D09, 0x10263D4D)}
                got = api.capture(Memory(rows), {'pc': api.HANDOFF, 'r0': 0x20,
                                                'r1': 0xC2200000, 'r2': mode})
                self.assertEqual(got['predicted_message_code_raw'], code)
                self.assertEqual(got['predicted_callback'], callback)
                self.assertEqual(got['handoff_argument0_raw'], 0x20)
                self.assertFalse(got['callback_execution_verified'])

    def test_graph_records_physical_units_and_rejects_truncated_payload(self):
        api = self.api()
        row = bytearray(16)
        row[0:2] = bytes((4, 54))
        struct.pack_into('<I', row, 12, 0xC2202000)
        rows = {(api.GRAPH, 4): bytes.fromhex(api.ANCHORS[api.GRAPH]),
                (0xC2200000, 8): struct.pack('<2I', 0xC2201000, 1),
                (0xC2201000, 16): bytes(row), (0xC2202000, 512): b'\x32' * 512}
        got = api.capture(Memory(rows), {'pc': api.GRAPH, 'r0': 0xC2201000, 'r5': 0xC2200000})
        self.assertEqual(got['graph']['nodes'][0]['physical_unit'], 54)
        self.assertEqual(got['graph']['nodes'][0]['payload_512'], '32' * 512)
        self.assertFalse(got['graph']['hardware_unit_semantics_verified'])
        rows[(0xC2202000, 512)] = b'\0' * 511
        with self.assertRaises(ValueError):
            api.capture(Memory(rows), {'pc': api.GRAPH, 'r0': 0xC2201000, 'r5': 0xC2200000})

    def test_invalid_anchor_and_non_ram_handoff_do_not_invent_a_callback(self):
        api = self.api()
        mem = Memory({(api.HANDOFF, 4): bytes(4)})
        self.assertFalse(api.capture(mem, {'pc': api.HANDOFF})['source_instruction_matches'])
        mem = Memory({(api.HANDOFF, 4): bytes.fromhex(api.ANCHORS[api.HANDOFF])})
        got = api.capture(mem, {'pc': api.HANDOFF, 'r0': 1, 'r1': 0x20100000, 'r2': 1})
        self.assertFalse(got['library_context']['available'])
        self.assertNotIn('predicted_callback', got)
        self.assertEqual(len(mem.reads), 1)


if __name__ == '__main__':
    unittest.main()
