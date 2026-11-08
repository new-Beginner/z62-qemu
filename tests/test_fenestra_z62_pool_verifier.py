"""Synthetic verification tests; no firmware, QEMU or physical device is invoked."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fenestra/z62'))
import verify_pool as v


def command():
    root = Path('Q:/')
    result = [str(root / v.QEMU_REL), '-M',
              'nikon-z62-dual-lab,'
              f'master-boot-image={root}/artifacts/z62-reference-1.70/master.bin,'
              f'slave-boot-image={root}/artifacts/z62-reference-1.70/slave.bin',
              '-smp', '4,maxcpus=5', '-S', '-display', 'none', '-serial', 'none',
              '-monitor', 'none', '-nic', 'none', '-gdb', 'tcp:127.0.0.1:12001',
              '-icount', 'shift=0,sleep=off', '-qmp', 'tcp:127.0.0.1:12002,server=on,wait=off']
    for cpu in range(4):
        result += ['-device', f'loader,addr={v.BASE:#x},cpu-num={cpu}']
    return result


def allocation(call_id, pointer, blocks):
    call = dict(id=call_id, entry=dict(role='master', kind='allocate', thread='01',
                registers=dict(r0=blocks, r1=0, cpsr=0x13, lr=0x1000)), overlaps=[])
    result = dict(id=call_id, successful=True, paired=True, pointer=pointer, blocks=blocks)
    return call, result


class PoolVerifierTests(unittest.TestCase):
    def test_exact_local_model_command(self):
        v.check_command(command())

    def test_changed_model_device_network_or_reset_pc_rejected(self):
        for kind in ('extra', 'model', 'pc', 'gdb', 'qmp', 'port_collision'):
            cmd = command()
            if kind == 'extra': cmd += ['-drive', 'file=card.raw']
            elif kind == 'model': cmd[2] += ',unexpected-property=on'
            elif kind == 'pc': cmd[-1] = 'loader,addr=0x10021000,cpu-num=3'
            elif kind == 'gdb': cmd[15] = 'tcp:0.0.0.0:12001'
            elif kind == 'qmp': cmd[19] = 'tcp:0.0.0.0:12002,server=on,wait=off'
            elif kind == 'port_collision': cmd[19] = 'tcp:127.0.0.1:12001,server=on,wait=off'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                v.check_command(cmd)

    def test_coverage_marks_absent_release_and_failures(self):
        call, result = allocation(0, 0x4000, 2)
        covered = v.coverage([call], [result])
        self.assertEqual(covered['master']['allocate_calls'], 1)
        self.assertEqual(covered['master']['release_calls'], 0)
        self.assertEqual(covered['master']['allocate_failures'], 0)
        self.assertEqual(covered['master']['total_observed_requested_bytes'], 4096)
        self.assertEqual(covered['slave']['allocate_calls'], 0)

    def test_allocation_ranges_must_not_overlap_without_releases(self):
        first, a = allocation(0, 0x4000, 2)
        second, b = allocation(1, 0x4800, 2)
        with self.assertRaisesRegex(ValueError, 'overlap'):
            v.coverage([first, second], [a, b])
        b['pointer'] = 0x5000
        self.assertTrue(v.coverage([first, second], [a, b])['master']['bounded_extents_nonoverlapping_without_releases'])

    def test_verification_demands_two_independent_runs(self):
        # Reject before reading input images or processes; only exercise length gate.
        from unittest.mock import patch
        with patch.object(v, 'collect', return_value={}), patch.object(v, 'read_inputs', return_value={}):
            with self.assertRaisesRegex(ValueError, 'Two independent'):
                v.verify([])


if __name__ == '__main__':
    unittest.main()
