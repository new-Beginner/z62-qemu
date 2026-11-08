"""Synthetic byte-heap evidence tests, not stock error-input or ABI validation."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fenestra/z62'))
import heap_calls as m
from heap_contract import aligned_size, descriptor_for_flags
from test_fenestra_z62_pool import event


def profile():
    return dict(allocate=0x1100, release=0x1200, descriptor_base=0x2000,
                descriptors=[dict(base=descriptor_for_flags(0x2000, f), flags=f) for f in (0, 0x10, 0x300, 0x310)],
                geometry=dict(start=0x3000, pool_end=0x4000, end=0xC000, count=16, block_bytes=0x800),
                copied_table=0x10000, vector=0x8000)


def snap(nodes=(), free=16):
    return dict(descriptor=0x2018, descriptor_words=[0]*7, control=[0, 0x800],
                pool_state=[16, free, 0x3000, 0x4000],
                headers=[dict(address=a, words=list(w)) for a, w in sorted(nodes)])


def allocation(sequence=0):
    e = event('allocate', sequence=sequence, r0=17, flags=0x2018)
    r = event('return', sequence=sequence+1, r0=0x4008)
    e['heap'] = snap()
    r['heap'] = snap([(0x4000, (0x4020, 3)), (0x4020, (0x4800, 0x4000))], free=15)
    return [e, r]


def release(sequence=2, raw=0x600001D3, merge_previous=False, merge_next=False):
    h = 0x4020 if merge_previous else 0x4000
    previous = 0x4000 if merge_previous else 2
    nodes = {h: (h+32, previous | 1), h+32: (0x4800, h | (0 if merge_next else 1)),
             0x4800: (0, h+32 | 4)}
    if merge_previous:
        nodes[0x4000] = (h, 2)
    owner = 0x4000
    nxt = 0x4800 if merge_next else h+32
    after = dict(nodes)
    after[owner] = (nxt, 2)
    after[nxt] = (after[nxt][0], owner | (after[nxt][1] & 7))
    e = event('release', sequence=sequence, r0=h+8, flags=0)
    r = event('return', sequence=sequence+1, r0=raw)
    e['heap'], r['heap'] = snap(nodes.items(), 15), snap(after.items(), 15)
    return [e, r]


class HeapTests(unittest.TestCase):
    def setUp(self):
        self.contract = dict(roles={role: profile() for role in ('master', 'slave')})

    def test_size_and_descriptor_selectors(self):
        for size, expected in [(0,16),(1,16),(16,16),(17,24),(24,24),(0xFFFFFFF8,0xFFFFFFF8)]:
            self.assertEqual(aligned_size(size),expected)
        for size in (-1,0xFFFFFFF9,2**32):
            with self.assertRaises(ValueError): aligned_size(size)
        self.assertEqual([descriptor_for_flags(0x2000,f) for f in (0,0x10,0x300,0x310)],
                         [0x2018,0x2000,0x2050,0x2038])

    def test_allocation_header_capacity_and_original_pairing(self):
        ledger, results = m.analyze_events(allocation(), self.contract)
        self.assertFalse(ledger.pending)
        self.assertTrue(results[0]['allocation_header_verified'])
        self.assertEqual(results[0]['capacity_bytes'],24)

    def test_allocation_zero_preserved_not_manufactured_success(self):
        rows=allocation(); rows[1]['registers']['r0']=0; rows[1]['heap']=snap()
        _, results=m.analyze_events(rows,self.contract)
        self.assertTrue(results[0]['zero_return'])
        self.assertNotIn('allocation_header_verified',results[0])

    def test_release_raw_return_is_not_zero_success_status(self):
        for raw in (0,0x13,0x600001D3,0xFFFFFFFF):
            rows=release(sequence=0,raw=raw)
            _, results=m.analyze_events(rows,self.contract)
            self.assertEqual(results[0]['raw_return_r0'],raw)
            self.assertFalse(results[0]['release_return_is_status'])
            self.assertEqual(results[0]['release_evidence'],'merged-free-header')

    def test_both_merge_directions(self):
        for previous in (False,True):
            for nxt in (False,True):
                _, rs=m.analyze_events(release(0,merge_previous=previous,merge_next=nxt),self.contract)
                self.assertEqual(rs[0]['merged_previous'],previous)
                self.assertEqual(rs[0]['merged_next'],nxt)

    def test_unresolved_release_not_claimed_as_verified(self):
        rows=release(0); rows[1]['heap']=copy.deepcopy(rows[0]['heap'])
        ledger, results=m.analyze_events(rows,self.contract)
        self.assertEqual(results[0]['release_evidence'],'unresolved')
        self.assertEqual(m.summarize(ledger.calls,results)['master']['release_unresolved'],1)

    def test_omitted_or_corrupt_header_capacity_rejected(self):
        for change in ('missing','used','capacity','backlink'):
            rows=allocation(); hs=rows[1]['heap']['headers']
            if change=='missing': hs.pop()
            elif change=='used': hs[0]['words'][1] &= ~1
            elif change=='capacity': hs[0]['words'][0]=0x4010
            else: hs[1]['words'][1]=0x4010
            with self.subTest(change=change), self.assertRaises(ValueError):
                m.analyze_events(rows,self.contract)

    def test_register_irq_descriptor_and_sequence_changes_rejected(self):
        for change in ('saved','irq','descriptor','sequence'):
            rows=allocation()
            if change=='saved': rows[1]['registers']['r4'] ^= 1
            elif change=='irq': rows[1]['registers']['cpsr'] ^= 0x80
            elif change=='descriptor': rows[0]['registers']['r1']=0x2028
            else: rows[1]['sequence']=9
            with self.subTest(change=change), self.assertRaises(ValueError):
                m.analyze_events(rows,self.contract)

    def test_exact_reuse_requires_prior_verified_release(self):
        rows=allocation()+release()+allocation(4)
        ledger,results=m.analyze_events(rows,self.contract)
        summary=m.summarize(ledger.calls,results)['master']
        self.assertEqual(summary['matched_prior_allocations'],1)
        self.assertEqual(summary['exact_pointer_reuses'],1)
        rows[3]['heap']=copy.deepcopy(rows[2]['heap'])
        ledger,results=m.analyze_events(rows,self.contract)
        self.assertEqual(m.summarize(ledger.calls,results)['master']['exact_pointer_reuses'],0)

    def test_bounded_read_ranges(self):
        p=profile()
        for a in (0,0x3FF8,0x4001,0xC000,2**32): self.assertFalse(m.valid_header(p,a))
        for a in (0x4000,0xBFF8): self.assertTrue(m.valid_header(p,a))


class HeapSnapshotTests(unittest.TestCase):
    def test_snapshot_reads_only_two_links_and_native_bounds(self):
        import struct
        from observe_heap import snapshot
        p=profile(); p.update(heap_control=0x1000,pool_state=0x1100)
        class Reader:
            def __init__(self): self.reads=[]
            def read(self,address,size):
                self.reads.append((address,size))
                if address==0x2018: return struct.pack('<7I',*([0]*7))
                if address==0x1000: return struct.pack('<2I',0,0x800)
                if address==0x1100: return struct.pack('<4I',16,15,0x3000,0x4000)
                return struct.pack('<2I',address+32,0xDEADBEEF)
        remote=Reader(); s=snapshot(remote,p,0x2018,0x4008)
        self.assertEqual([n['address'] for n in s['headers']],[0x4000,0x4020,0x4040])
        self.assertNotIn((0x4060,8),remote.reads)
        self.assertNotIn((0xDEADBEE8,8),remote.reads)
        m.check_snapshot(s,p,0x2018)

    def test_invalid_pointer_rejected_before_any_read(self):
        from observe_heap import snapshot
        class Reader:
            def read(self,*args): raise AssertionError('Unexpected read')
        with self.assertRaises(ValueError): snapshot(Reader(),profile(),0x2018,0xC008)

    def test_snapshot_header_count_bound_is_enforced(self):
        from observe_heap import snapshot
        class Reader:
            def read(self,*args): raise AssertionError('Unexpected read')
        with self.assertRaises(ValueError):
            snapshot(Reader(),profile(),0x2018,seeds=[0x4000+8*i for i in range(25)])


if __name__ == '__main__':
    unittest.main()
