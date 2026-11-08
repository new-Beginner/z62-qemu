"""r14 ablation command/trace tests; synthetic logs are tool tests only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fenestra/z62'))
import observe_completion_ablation as observer


class CompletionCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ['PI_SCRATCH_DIR'])
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def test_default_and_disabled_profiles_are_exact(self):
        args = (Path('Q:/'), 'default', (10001, 10002), Path('Q:/trace.log'))
        default = observer.command(*args)
        self.assertNotIn('-global', default)
        off = observer.command(args[0], 'three-off', args[2], args[3])
        self.assertEqual(off[:28], default[:28])
        self.assertEqual(off[28:34], [item for name in observer.DEFAULT_COMPLETIONS
                                    for item in ('-global', 'nikon-z72-boot-config.' + name + '=off')])
        self.assertEqual(off[34:], default[28:])
        self.assertEqual(default[13], 'none')

    def test_single_property_profiles_do_not_enable_another_helper(self):
        for profile in ('gate-off', 'transfer-off', 'sequencer-off'):
            command = observer.command(Path('Q:/'), profile, (10001, 10002), Path('Q:/trace.log'))
            self.assertEqual(command.count('-global'), 1)
            properties = [command[i + 1] for i, value in enumerate(command) if value == '-global']
            self.assertTrue(all(value.endswith('=off') for value in properties))

    def test_source_contract_matches_compiled_model_and_keeps_limitations(self):
        result = observer.source_contract()
        self.assertEqual(result['transfer_reset'], '0x20100004 == 0')
        self.assertEqual(result['sequencer_commands'], ['0x04251028', '0x04251058', '0x04251088', '0x042510b8'])
        self.assertTrue(result['other_success_assumptions_still_present'])
        self.assertIn('all_completion_logic_disabled', observer.FALSE_FIELDS)

    def test_trace_exact_request_classification_not_success(self):
        lines = []
        for cpu, address, value in ((0, 0x04287010, 0xA1), (2, 0x20100004, 0),
                                    (0, 0x04251028, 0x10000003), (0, 0x04251028, 3)):
            lines.append("memory_region_ops_write cpu %d mr 0x1234 addr 0x%x value 0x%x size 4 name 'fixture'" %
                         (cpu, address, value))
        path = self.folder / 'trace.log'
        path.write_text('\n'.join(lines))
        result = observer.trace_summary(path)
        self.assertEqual(result['attempted_mmio_writes'], 4)
        self.assertEqual({n: len(v) for n, v in result['matching_request_attempts'].items()},
                         {'gate': 1, 'sequencer': 1, 'transfer_reset': 1})
        self.assertFalse(result['accepted_writes_proven'])
        self.assertFalse(result['all_helper_dependencies_exercised'])

    def test_malformed_known_trace_event_rejected(self):
        path = self.folder / 'trace.log'
        path.write_text('memory_region_ops_write malformed\n')
        with self.assertRaisesRegex(ValueError, 'Malformed'):
            observer.trace_summary(path)

    def test_trace_size_limit_refuses_instead_of_truncating(self):
        path = self.folder / 'trace.log'
        path.write_bytes(b'0123456789')
        with patch.object(observer, 'TRACE_LIMIT', 1), self.assertRaisesRegex(ValueError, 'bounded size'):
            observer.trace_summary(path)
        self.assertEqual(path.read_bytes(), b'0123456789')

    def test_invalid_profile_rejected_before_any_launch(self):
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            observer.command(Path('Q:/'), 'unapproved', (10001, 10002), Path('Q:/trace.log'))


class CompletionReplayTests(unittest.TestCase):
    def test_seven_independent_saved_observations_replay(self):
        import json
        pids = set()
        for name in ('default-1', 'default-2', 'three-off-1', 'three-off-2',
                     'gate-off-1', 'transfer-off-1', 'sequencer-off-1'):
            output = observer.ROOT / 'analysis/fenestra-z62-model-r14' / (name + '.json')
            record = json.loads(output.read_text())
            result = observer.check(record, output)
            self.assertTrue(result['limited_ablation_observed'])
            self.assertFalse(result['complete_native_boot_verified'])
            self.assertFalse(result['all_completion_logic_disabled'])
            pids.add(result['pid'])
        self.assertEqual(len(pids), 7)

    def test_targeted_record_errors_rejected(self):
        import copy
        import json
        output = observer.ROOT / 'analysis/fenestra-z62-model-r14/default-1.json'
        saved = json.loads(output.read_text())
        changes = [
            lambda r: r['samples'].pop(),
            lambda r: r.update(profile='three-off'),
            lambda r: r.update(debugger_guest_state_written=True),
            lambda r: r.update(qemu_sha256='0' * 64),
            lambda r: r['command'].__setitem__(13, 'user'),
            lambda r: r['sources'].update({'fenestra/z62/observe_completion_ablation.py': '0' * 64}),
            lambda r: r['source_contract'].update(other_success_assumptions_still_present=False),
            lambda r: r['samples'][0]['completion_registers']['master']['transfer'].update(address=0),
            lambda r: r['samples'][0]['cpus'][0]['system'].update(DFSR_S=1),
            lambda r: r['samples'][0]['cpus'][0]['code'].update(matches_original=False),
            lambda r: r['samples'][1]['cpus'][0].update(model_clock_ticks=0),
            lambda r: r['rsp_commands'].append('M10020000,4:00000000'),
            lambda r: r['qmp_commands'].append({'command': 'write', 'arguments': {}}),
            lambda r: r['trace'].update(trace_sha256='0' * 64),
            lambda r: r['trace']['matching_request_attempts']['gate'].pop(),
            lambda r: r.update(trace_budget_exceeded=True),
            lambda r: r['quit_receipt'].update(acknowledged=False),
        ]
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                record = copy.deepcopy(saved)
                change(record)
                with self.assertRaises(ValueError):
                    observer.check(record, output)


if __name__ == '__main__':
    unittest.main()
