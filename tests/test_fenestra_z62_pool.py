"""Synthetic observer tests; these do not exercise firmware allocation failures."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fenestra/z62'))
import pool_calls as m
from observe_pool import ReadOnlyRemote
from observe_startup import Remote


def profile():
    return dict(geometry=dict(start=0x2000, pool_end=0x4000, end=0xC000, count=16, block_bytes=0x800),
                copied_table=0x10000, vector=0x8000, observed_api=dict(allocate=0x1100, release=0x1200))


def pool(free, ptr=None, blocks=None, used=False, flags=0):
    g = profile()['geometry']
    i = m.header_index(g, ptr)
    rows = []
    for j in m.sample_indices(g, ptr, blocks):
        words = [0, 0]
        if used and j == i:
            words = [2 | int(blocks > 1), (i << 2) | int(bool(flags & 0x10000))]
        if used and blocks > 1 and j == i + 1:
            words = [(blocks << 2) | 3, 0]
        rows.append(dict(index=j, address=g['start'] + j * 8, words=words))
    return dict(state=[16, free, 0x2000, 0x4000], headers=rows)


def event(kind, sequence=0, role='master', thread='01', sp=0xF000, pc=None, lr=0x1300, r0=2, flags=0):
    p = profile()
    regs = {n: 0 for n in m.REGISTERS}
    regs.update(sp=sp, pc=pc if pc is not None else p['observed_api'].get(kind, lr & ~1),
                lr=lr, cpsr=0x13 | (32 if kind == 'return' and lr & 1 else 0), r0=r0, r1=flags)
    return dict(kind=kind, sequence=sequence, role=role, thread=thread, registers=regs,
                system_registers=dict(TTBR0_S=0x10000, TTBCR_S=0, DACR_S=0x55555555,
                                      SCTLR_EL1_S=0x1005, VBAR_EL1_S=0x8000,
                                      DFSR_S=0, IFSR_S=0, DFSR=0, IFSR=0))


def allocation(blocks=2, flags=0, thumb=False):
    e = event('allocate', r0=blocks, flags=flags, lr=0x1301 if thumb else 0x1300)
    r = event('return', sequence=1, r0=0x4000, lr=e['registers']['lr'])
    e['pool'] = pool(16)
    r['pool'] = pool(16 - blocks, 0x4000, blocks, True, flags)
    return [e, r]


class PoolTests(unittest.TestCase):
    def setUp(self):
        self.contract = dict(roles={r: profile() for r in ('master', 'slave')})

    def test_allocation_block_count_tag_and_thumb_return(self):
        for n in (1, 2, 5):
            for flags in (0, 0x10000):
                for thumb in (False, True):
                    with self.subTest(n=n, flags=flags, thumb=thumb):
                        ledger, results = m.analyze_events(allocation(n, flags, thumb), self.contract)
                        self.assertFalse(ledger.pending)
                        self.assertTrue(results[0]['isolated_observed'])
                        self.assertEqual(results[0]['blocks'], n)

    def test_return_identity_rejects_cpu_role_stack_pc_and_isa(self):
        ledger = m.Ledger()
        e, r = allocation()
        ledger.enter(e)
        for field, value in [('thread', '02'), ('role', 'slave')]:
            altered = copy.deepcopy(r)
            altered[field] = value
            self.assertIsNone(ledger.match(altered))
        for field, value in [('sp', 0xF100), ('pc', 0x1304), ('cpsr', 0x33)]:
            altered = copy.deepcopy(r)
            altered['registers'][field] = value
            self.assertIsNone(ledger.match(altered))
        self.assertEqual(ledger.match(r), 0)

    def test_same_cpu_shared_lr_nested_stacks_are_not_confused(self):
        ledger = m.Ledger()
        e, r = allocation()
        ledger.enter(e)
        nested = copy.deepcopy(e)
        nested['registers']['sp'] -= 0x40
        ledger.enter(nested)
        self.assertEqual(ledger.match(r), 0)
        self.assertEqual(ledger.calls[0]['overlaps'], [1])
        self.assertEqual(ledger.calls[1]['overlaps'], [0])
        self.assertEqual(len(ledger.return_addresses()), 1)
        ledger.returned(0, r)
        self.assertEqual(len(ledger.return_addresses()), 1)

    def test_independent_roles_do_not_mark_overlap(self):
        ledger = m.Ledger()
        e, _ = allocation()
        ledger.enter(e)
        other = copy.deepcopy(e)
        other.update(role='slave', thread='03')
        ledger.enter(other)
        self.assertEqual([c['overlaps'] for c in ledger.calls], [[], []])

    def test_ambiguous_return_fails_closed(self):
        ledger = m.Ledger()
        e, r = allocation()
        ledger.enter(e)
        ledger.enter(copy.deepcopy(e))
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            ledger.match(r)

    def test_unreturned_call_remains_pending(self):
        ledger, results = m.analyze_events(allocation()[:1], self.contract)
        self.assertEqual(list(ledger.pending), [0])
        self.assertFalse(results[0]['paired'])

    def test_isolated_release_uses_pre_release_extent(self):
        e = event('release', r0=0x4000)
        r = event('return', sequence=1, r0=0)
        e['pool'] = pool(13, 0x4000, 3, True)
        r['pool'] = pool(16, 0x4000, 3)
        _, result = m.analyze_events([e, r], self.contract)
        self.assertEqual(result[0]['blocks'], 3)
        self.assertTrue(result[0]['successful'])

    def test_bad_deltas_headers_and_registers_are_rejected(self):
        for mutate in ('delta', 'length', 'tag', 'saved', 'mode', 'sequence', 'fault', 'table'):
            rows = allocation(flags=0x10000)
            e, r = rows
            if mutate == 'delta': r['pool']['state'][1] += 1
            elif mutate == 'length': r['pool']['headers'][2]['words'][0] += 4
            elif mutate == 'tag': r['pool']['headers'][1]['words'][1] ^= 1
            elif mutate == 'saved': r['registers']['r4'] += 1
            elif mutate == 'mode': r['registers']['cpsr'] ^= 1
            elif mutate == 'sequence': r['sequence'] += 1
            elif mutate == 'fault': r['system_registers']['DFSR_S'] = 1
            elif mutate == 'table': r['system_registers']['TTBR0_S'] ^= 0x4000
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                m.analyze_events(rows, self.contract)

    def test_bounded_pointer_sampling_never_leaves_metadata(self):
        g = profile()['geometry']
        for ptr in (None, -1, 0, 0x4001, 0xC000, 2**32):
            self.assertIsNone(m.header_index(g, ptr))
            self.assertEqual(m.sample_indices(g, ptr, 2**32), [0, 1, 2, 16])
        self.assertEqual(m.header_index(g, 0xB800), 16)
        self.assertTrue(all(0 <= i <= 16 for i in m.sample_indices(g, 0xB800, 16)))

    def test_read_only_rsp_guard_rejects_mutations_before_delivery(self):
        remote = object.__new__(ReadOnlyRemote)
        with patch.object(Remote, 'command', return_value='OK') as deliver:
            for payload in ('G0000', 'P0=0000', 'M1000,4:00000000', 'X1000,4:test',
                            'Z0,1000,2', 'c1000', 'qRcmd,00', 'vRun', 's', 'Hc-1'):
                with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, 'Forbidden'):
                    remote.command(payload)
            deliver.assert_not_called()
            for payload in ('g', 'c', 'vCont;s:03', 'Hg1', 'm1000,10', 'p10', 'Z1,1000,2', 'z1,1000,2'):
                self.assertEqual(remote.command(payload), 'OK')
            self.assertEqual(deliver.call_count, 8)


    def test_step_resumes_only_requested_cpu(self):
        import observe_pool as observer
        class Fake:
            def __init__(self): self.operations = []
            def breakpoint(self, address, add=True): self.operations.append((address, add))
            def command(self, payload):
                self.operations.append(payload)
                if payload == 'vCont;s:03': return 'T05thread:03;'
                if payload == 'qC': return 'QC01'  # Deliberately stale Hg selection.
                raise AssertionError('Must not resume other CPUs: ' + payload)
        fake = Fake()
        self.assertEqual(observer.advance_isolated(fake, 0x1000, '03', True), 'T05thread:03;')
        self.assertEqual(fake.operations, [(0x1000, False), 'vCont;s:03', 'qC', (0x1000, True)])
        fake = Fake()
        self.assertIsNone(observer.advance_isolated(fake, 0x1000, '03', False))
        self.assertEqual(fake.operations, [(0x1000, False)])


    def test_close_failure_does_not_prevent_other_handles_or_receipt(self):
        import observe_pool as observer
        class Handle:
            def __init__(self, fail=False): self.closed = False; self.fail = fail
            def close(self):
                self.closed = True
                if self.fail: raise ConnectionResetError('peer reset')
        first, second = Handle(True), Handle()
        failures = observer.close_handles((None, first, second))
        self.assertTrue(first.closed and second.closed)
        self.assertEqual(len(failures), 1)
        self.assertIn('peer reset', failures[0])


    def test_quit_records_reset_but_requires_real_exit_zero(self):
        import observe_pool as observer
        class Session:
            def __init__(self): self.calls = 0
            def query(self, command):
                self.calls += 1
                if command != 'quit': raise AssertionError(command)
                raise ConnectionResetError('peer exited before acknowledgement')
        class Process:
            def __init__(self, code): self.returncode = code; self.waited = False
            def wait(self, timeout): self.waited = True; return self.returncode
        session, process = Session(), Process(0)
        receipt = observer.quit_owned(session, process)
        self.assertFalse(receipt['acknowledged'])
        self.assertTrue(process.waited)
        self.assertEqual(session.calls, 1)
        with self.assertRaisesRegex(ValueError, 'exit'):
            observer.quit_owned(Session(), Process(1))


    def test_overlapped_calls_do_not_claim_isolated_count_deltas(self):
        first, first_return = allocation(2)
        second, second_return = allocation(3)
        second.update(sequence=1, thread='02')
        second['registers']['sp'] = 0xF800
        second['pool'] = pool(14)
        second_return.update(sequence=2, thread='02')
        second_return['registers'].update(sp=0xF800, r0=0x5000)
        second_return['pool'] = pool(11, 0x5000, 3, True)
        first_return['sequence'] = 3
        first_return['pool'] = pool(11, 0x4000, 2, True)
        ledger, results = m.analyze_events([first, second, second_return, first_return], self.contract)
        self.assertFalse(ledger.pending)
        self.assertTrue(all(r['paired'] and not r['isolated_observed'] for r in results))

    def test_synthetic_zero_return_preserves_count_without_claiming_success(self):
        entry, ret = allocation(2)
        ret['registers']['r0'] = 0
        ret['pool'] = pool(16)
        _, results = m.analyze_events([entry, ret], self.contract)
        self.assertFalse(results[0]['successful'])

    def test_synthetic_invalid_release_retains_unknown_extent(self):
        entry = event('release', r0=0x4001)
        ret = event('return', sequence=1, r0=0xFFFFFFFF)
        entry['pool'] = pool(16, 0x4001)
        ret['pool'] = pool(16, 0x4001)
        _, results = m.analyze_events([entry, ret], self.contract)
        self.assertIsNone(results[0]['blocks'])
        self.assertFalse(results[0]['successful'])


if __name__ == '__main__':
    unittest.main()
