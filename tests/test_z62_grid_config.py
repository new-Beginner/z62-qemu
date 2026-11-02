from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))


class GridConfigTests(unittest.TestCase):
    def api(self):
        try:
            import probe_z62_grid_config as api
        except ImportError as exc:
            self.fail('Bank0 physical configuration reader is missing: '+str(exc))
        return api

    def rows(self, source=0x88EDF000):
        a, b, table = [0]*13, [0]*13, [0]*64
        a[0], a[4], a[5], a[6], a[8], a[10], a[11] = 0x20121,128,128,128,0x28003C,0x12000,0x24000
        b[0], b[4], b[5], b[8] = 0x10621,96,96,0x28003C
        table[1], table[2] = source, 0x89C48400
        rows = {(0x20102000,4): struct.pack('<I',1),
                (0x20102640,12): struct.pack('<3I',0,1000,1),
                (0x20100440,52): struct.pack('<13I',*a),
                (0x20100480,52): struct.pack('<13I',*b),
                (0x20102200,256): struct.pack('<64I',*table),
                (0x201009C0,24): struct.pack('<6I',0,0,0,0,0,0),
                (0x89C48400,3840): bytes(3840)}
        if source == 0x88EDF000:
            for p, v in ((0x88EDF000,100),(0x88EF1000,200),(0x88F03000,300)):
                rows[(p,5120)] = struct.pack('<2560H', *([v]*2560))
        return rows

    def test_keeps_three_input_planes_and_packed_output_separate(self):
        api = self.api()
        rows = self.rows()
        class Memory:
            def read(self, address, size): return rows[(address,size)]
        d = api.configuration(Memory())
        self.assertEqual(d['ports'][0]['words'][0],0x20121)
        self.assertEqual(d['ports'][1]['words'][0],0x10621)
        f = d['frames'][0]
        self.assertEqual([p['minimum_active_u16'] for p in f['input_planes']], [100,200,300])
        self.assertEqual(f['packed_output']['pointer'],'0x89c48400')
        self.assertEqual(f['continuous_rgb_slot'],0)
        self.assertFalse(d['hardware_direction_semantics_verified'])

    def test_io_pointer_and_short_registers_do_not_produce_fake_ram_samples(self):
        api = self.api()
        rows = self.rows(0x20100000)
        class Memory:
            def read(self, address, size): return rows[(address,size)]
        d = api.configuration(Memory())
        self.assertFalse(d['frames'][0]['input_planes'][0]['available'])
        class Short:
            def read(self,address,size): return bytes(size-1)
        with self.assertRaises(ValueError): api.configuration(Short())
