"""Transfer and processor callback interfaces must not be conflated."""
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


class TransferBindingsTests(unittest.TestCase):
    def api(self):
        try:
            import trace_z62_transfer_bindings as api
        except ImportError as exc:
            self.fail('Original transfer binding observer is missing: ' + str(exc))
        return api

    def test_wait_snapshot_keeps_transfer_and_processor_banks_separate(self):
        api = self.api()
        words = list(range(10))
        context = bytearray(16)
        struct.pack_into('<II', context, 8, 0x102E719B, 0x102E6F0D)
        rows = {(api.WAIT, 4): bytes.fromhex(api.ANCHORS[api.WAIT]),
                (0x20100000, 40): struct.pack('<10I', *words),
                (0xC1801D60, 24): struct.pack('<6I', 0x103B754D, 0, 0, 0, 0x146, 0x1038B021),
                (0xC1809500, 12): struct.pack('<3I', 0x102E47B1, 0x102E47AB, 0x102E47A5),
                (0xC1801D78, 192): struct.pack('<48I', *[v for _ in range(3) for i in range(8) for v in (1 << i, 1 << i)]),
                (0xC1CF0F40, 32): struct.pack('<8I', 0, 0, 0, 0x10388913, 0, 0, 0, 0),
                (0xC1809554, 4): struct.pack('<I', 0x102E4491),
                (0xC1801ECC, 16): bytes(context),
                (0xC1D52636, 1): b'\x01', (0xC1D5267E, 1): b'\x01'}
        m = Memory(rows)
        result = api.capture(m, {'pc': api.WAIT})
        self.assertEqual(result['transfer_registers']['0x1c'], 7)
        self.assertEqual(result['transfer_control_callback'], '0x1038b021')
        self.assertEqual(result['processor_callback1'], '0x102e6f0d')
        self.assertEqual(result['message_decoder_hook'], '0x102e47b1')
        self.assertEqual(result['result_callbacks'][3], '0x10388913')
        self.assertEqual(result['result_status_tables']['status1c_low'][3], {'status_mask': 8, 'payload': 8})
        self.assertFalse(any(0x203C0000 <= address < 0x203C1000 for address, _ in m.reads))

    def test_irq_sample_uses_original_cpu_status_values_without_reading_io_again(self):
        api = self.api()
        m = Memory({(api.IRQ_SAMPLE, 4): bytes.fromhex(api.ANCHORS[api.IRQ_SAMPLE])})
        d = api.capture(m, {'pc': api.IRQ_SAMPLE, 'r0': 0x20100000,
                            'r4': 8, 'r5': 1, 'r6': 0})
        self.assertEqual(d['native_status20'], 8)
        self.assertEqual(d['native_status18'], 1)
        self.assertEqual(d['native_status1c'], 0)
        self.assertEqual(len(m.reads), 1)

    def packet(self):
        raw = bytearray(32)
        struct.pack_into('<IIII', raw, 12, 0x10263D09, 0x42193081, 0xC2200100, 1)
        return bytes(raw)

    def test_constructed_and_dispatched_message_use_their_actual_pointer_arguments(self):
        api = self.api()
        for pc, regs in ((api.ENQUEUE, {'r0': 0xC2200010, 'r4': 0xC2200000}),
                         (api.DECODE, {'r0': 0, 'r1': 0xC2200010})):
            with self.subTest(pc=pc):
                m = Memory({(pc, 4): bytes.fromhex(api.ANCHORS[pc]),
                            (0xC2200010, 32): self.packet()})
                got = api.capture(m, {'pc': pc, **regs})
                self.assertEqual(got['message_code_raw'], 0x42193081)
                self.assertEqual(got['message_callback'], '0x10263d09')
                self.assertEqual(got['message_payload_raw'], 1)

    def test_unknown_code_short_packet_and_scalar_hooks_do_not_fabricate_binding(self):
        api = self.api()
        m = Memory({(api.DECODE, 4): b'\0' * 4})
        self.assertFalse(api.capture(m, {'pc': api.DECODE})['source_instruction_matches'])
        self.assertEqual(len(m.reads), 1)
        m = Memory({(api.DECODE, 4): bytes.fromhex(api.ANCHORS[api.DECODE]),
                    (0xC2200010, 32): self.packet()[:-1]})
        with self.assertRaises(ValueError):
            api.capture(m, {'pc': api.DECODE, 'r1': 0xC2200010})
        pc = 0x1038B1D8
        m = Memory({(pc, 4): bytes.fromhex(api.ANCHORS[pc])})
        got = api.capture(m, {'pc': pc, 'r0': 0x102E47B1})
        self.assertEqual(got['proposed_hook'], '0x102e47b1')
        self.assertEqual(len(m.reads), 1)


if __name__ == '__main__':
    unittest.main()
