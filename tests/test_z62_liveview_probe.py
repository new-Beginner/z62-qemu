import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import probe_z62_liveview as probe


class LiveviewObservationTests(unittest.TestCase):
    def fixture(self, accepted=True, armed=True):
        calls = []
        counts = {'raw-accepted': 0, 'raw-bytes': 0, 'raw-last-reason': 'reset'}
        def words(address, count):
            values = {0x20068008: [0x200], 0x20068260: [0x80 if armed else 0],
                      0x20068280: [0x100 if armed else 0],
                      0x20069F00: [0x11], 0x20068200: [0x79],
                      0x20069A3C: [0], 0x20069A50: [0x82C00000, 0x8448DC00, 0x85D1B800, 0x875A9400]}
            return values[address]
        def qtest(command):
            calls.append(command)
            if command.endswith('raw-submit 0 1') and accepted:
                counts['raw-accepted'] += 1
                counts['raw-bytes'] += 4*2285632
                counts['raw-last-reason'] = 'success'
            return 'OK 0x00'
        def query(command, arguments):
            if command == 'qom-list':
                return [{'name': 'config', 'type': 'child<nikon-z72-boot-config>'}]
            if arguments['property'] == 'master-role':
                return True
            return counts[arguments['property']]
        return SimpleNamespace(_words=words, _qtest=qtest,
                               wire_file=SimpleNamespace(
                                   write=lambda data: calls.append(data.decode().strip()),
                                   flush=lambda: None,
                                   readline=lambda: b'OK 0x'+probe.expected_raw_prefix().hex().encode()+b'\n'),
                               qmp=SimpleNamespace(command=query)), calls

    def test_failed_dma_never_gets_a_boundary(self):
        machine, calls = self.fixture(accepted=False)
        result = probe.raw_boundary_transaction(machine)
        self.assertFalse(result['boundary_supplied'])
        self.assertTrue(all('input-event' not in call for call in calls))

    def test_boundary_requires_real_dma_accounting_and_readback(self):
        machine, calls = self.fixture()
        result = probe.raw_boundary_transaction(machine)
        self.assertTrue(result['boundary_supplied'])
        self.assertEqual(result['byte_delta'], 9142528)
        self.assertLess(calls.index('read 0x82c00000 0x20'),
                        calls.index('set_irq_in /machine/unattached/config input-event 103 1'))

    def test_unarmed_path_does_not_request_dma(self):
        machine, calls = self.fixture(armed=False)
        self.assertFalse(probe.raw_boundary_transaction(machine)['submitted'])
        self.assertEqual(calls, [])

    def test_raw_channel2_selects_its_own_mask_and_boundary(self):
        machine, calls = self.fixture()
        result = probe.raw_boundary_transaction(machine, 136)
        self.assertTrue(result['boundary_supplied'])
        self.assertIn('set_irq_in /machine/unattached/config input-event 136 1', calls)
        self.assertTrue(all('input-event 103' not in call for call in calls))

    def test_metadata_experiment_requires_a_completed_channel2_transfer(self):
        machine, calls = self.fixture()
        self.assertFalse(probe.metadata_after_transaction(machine, {})['supplied'])
        self.assertEqual(calls, [])
        transaction = probe.raw_boundary_transaction(machine, 136)
        self.assertTrue(probe.metadata_after_transaction(machine, transaction)['supplied'])
        self.assertIn('set_irq_in /machine/unattached/config input-event 6 1', calls)

    def test_debugger_zeros_do_not_verify_isp_layout(self):
        machine = SimpleNamespace(_words=lambda address, count: [0] * count)
        rows = probe.registers(machine)
        self.assertTrue(rows['isp_control_reference']['read_succeeded'])
        self.assertFalse(rows['isp_control_reference']['layout_verified'])
        self.assertTrue(rows['lcd_scanout']['layout_verified'])

    def test_read_failures_are_unknown_not_zero(self):
        def fail(*args):
            raise ValueError('unmapped')
        rows = probe.registers(SimpleNamespace(_words=fail))
        self.assertTrue(all(not row['read_succeeded'] for row in rows.values()))
        self.assertTrue(all('words' not in row for row in rows.values()))

    def test_collects_cleanup_logs_and_refuses_changed_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)/'work'
            output = Path(folder)/'evidence'
            (work/'runs').mkdir(parents=True)
            output.mkdir()
            for name in ('console.txt', 'command.json'):
                (work/'runs'/('last-'+name)).write_bytes(b'owned evidence')
            result = probe.collect_logs(work, output)
            self.assertEqual(result['console.txt']['bytes'], 14)
            (output/'console.txt').write_bytes(b'preserve earlier evidence')
            with self.assertRaisesRegex(ValueError, 'Refusing changed'):
                probe.collect_logs(work, output)
            self.assertEqual((output/'console.txt').read_bytes(), b'preserve earlier evidence')


if __name__ == '__main__':
    unittest.main()
