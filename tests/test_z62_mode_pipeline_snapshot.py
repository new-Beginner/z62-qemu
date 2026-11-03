"""Bounded observation must handle new geometry without reading MMIO holes."""
import hashlib
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import z62_mode_pipeline_snapshot as subject


class Memory:
    def __init__(self):
        self.regions = []
        self.reads = []

    def map(self, address, data):
        for index, (start, previous) in enumerate(self.regions):
            if start <= address and address+len(data) <= start+len(previous):
                content = bytearray(previous)
                content[address-start:address-start+len(data)] = data
                self.regions[index] = (start, bytes(content))
                return
        self.regions.append((address, bytes(data)))

    def read(self, address, size):
        self.reads.append((address, size))
        for start, data in reversed(self.regions):
            if start <= address and address + size <= start + len(data):
                return data[address-start:address-start+size]
        raise ValueError('Unmapped fixture read: '+hex(address)+'/'+str(size))


def fixture(height=34):
    memory = Memory()
    core = bytearray(0x3000)
    struct.pack_into('<3I', core, 0x2640, 0x202, height, 3)
    struct.pack_into('<3I', core, 0x2600, 0x300, 846, 3)
    for offset, row, format_word in ((0x440, 128, 0x20121), (0x480, 96, 0x10621)):
        words = [format_word, 0, 0, 0, row, row, 128 if offset == 0x440 else 0,
                 0, height << 16 | 60, 0, 0x12000 if offset == 0x440 else 0,
                 0x24000 if offset == 0x440 else 0, 0]
        struct.pack_into('<13I', core, offset, *words)
    for slot in range(4):
        struct.pack_into('<II', core, 0x2204+slot*64,
                         0x88edf000+slot*0x36000, 0x8af14400+slot*0xd800)
    memory.map(0x20100000, core)
    memory.map(0x20380000, bytes(0x440))
    raw = [6, 1514 << 16, 850 << 16]
    memory.map(0x20069500, bytes(0x34))
    memory.map(0x20069514, struct.pack('<3I', *raw))
    memory.map(0x2006a200, bytes(0x174))
    # Only source-established RAW/DMA fields exist; holes must not be probed.
    offsets = (8, 0x14, 0x18, 0x24, 0x3c, 0x40, 0x44, 0x48, 0x4c,
               0x50, 0x54, 0x58, 0x5c, 0x60, 0x64, 0x68, 0x6c, 0x80)
    for offset in offsets:
        memory.map(0x20069a00+offset, struct.pack('<I', 2272 if offset == 8 else 0))
    for ch in range(5):
        fields = (0x14, 0x18, 0x24, 0x3c, 0x40, 0x44, 0x48, 0x4c,
                  0x50, 0x60, 0x74, 0x80)
        if ch >= 2:
            fields += (0x54, 0x58, 0x5c, 0x64, 0x68, 0x6c)
        for offset in fields:
            memory.map(0x2006a400+ch*0x100+offset, bytes(4))
    memory.map(0x20068008, bytes(4))
    memory.map(0x20068010, bytes(4))
    memory.map(0x20068018, bytes(4))
    memory.map(0x20068290, bytes(4))
    for slot in range(4):
        for plane in range(3):
            data = b''.join(struct.pack('<60H', *[100+slot+plane+y+x for x in range(60)])
                            + b'\xee'*8 for y in range(height))
            memory.map(0x88edf000+slot*0x36000+plane*0x12000, data)
    return memory


class PipelineSnapshot(unittest.TestCase):
    def test_new_height_uses_programmed_rows(self):
        memory = fixture(34)
        result = subject.capture(memory)
        self.assertEqual(result['raw']['width_field_high16'], 1514)
        self.assertEqual(result['raw']['height_field_high16'], 850)
        self.assertEqual(result['command_groups']['0'], [0x202, 34, 3])
        self.assertEqual(result['command_groups']['1'], [0x300, 846, 3])
        plane = result['grid_views'][0]['input_planes'][0]
        self.assertEqual(plane['captured_bytes'], 128*34)
        self.assertTrue(plane['captured'])
        self.assertIn((0x88edf000, 128*34), memory.reads)
        self.assertNotIn((0x88edf000, 128*40), memory.reads)
        self.assertFalse(result['numerical_execution_verified'])
        self.assertFalse(result['generation_freshness_verified'])

    def test_photo_height_still_observable(self):
        result = subject.capture(fixture(40))
        self.assertEqual(result['grid_views'][0]['input_planes'][0]['captured_bytes'], 128*40)

    def test_raw_field_is_independent_of_new_command_height(self):
        memory = fixture(34)
        memory.map(0x2006951c, struct.pack('<I', 1006 << 16))
        result = subject.capture(memory)
        self.assertEqual(result['raw']['height_field_high16'], 1006)
        self.assertEqual(result['command_groups']['1'][1], 846)

    def test_mmio_pointer_is_not_followed_as_parameter_ram(self):
        memory = fixture()
        memory.map(0x201009d0, struct.pack('<I', 0xf8100000))
        result = subject.capture(memory)
        unit = next(x for x in result['unit_parameters'] if x['offset'] == '0x9c0')
        self.assertFalse(unit['payload_candidate']['captured'])
        self.assertFalse(any(address == 0xf8100000 for address, _ in memory.reads))

    def test_mmio_read_failure_is_not_zero_filled(self):
        memory = fixture()
        original = memory.read
        memory.read = lambda address, size: b'\0'*(size-1) if address == 0x20069500 else original(address, size)
        with self.assertRaises(ValueError):
            subject.capture(memory)

    def test_missing_plane_is_explicitly_unavailable(self):
        memory = fixture()
        original = memory.read
        def read(address, size):
            if address == 0x88edf000:
                raise RuntimeError('Expected missing RAM')
            return original(address, size)
        memory.read = read
        plane = subject.capture(memory)['grid_views'][0]['input_planes'][0]
        self.assertFalse(plane['captured'])
        self.assertEqual(plane['error']['type'], 'RuntimeError')
        self.assertNotIn('sha256', plane)

    def test_overflow_and_budget_do_not_read_ram(self):
        memory = fixture()
        memory.map(0x20100460, struct.pack('<I', 0xffff003c))
        result = subject.capture(memory)
        self.assertFalse(result['grid_views'][0]['input_planes'][0]['captured'])
        self.assertFalse(any(address == 0x88edf000 for address, _ in memory.reads))

    def test_parameter_candidate_preserves_opaque_bytes(self):
        memory = fixture()
        payload = bytes(range(160))
        memory.map(0x201009d0, struct.pack('<I', 0x8b000000))
        memory.map(0x8b000000, payload)
        unit = next(x for x in subject.capture(memory)['unit_parameters'] if x['offset'] == '0x9c0')
        self.assertEqual(unit['payload_candidate']['sha256'], hashlib.sha256(payload).hexdigest())
        self.assertEqual(bytes.fromhex(unit['payload_candidate']['raw']), payload)
        self.assertFalse(unit['payload_semantics_verified'])


if __name__ == '__main__':
    unittest.main()
