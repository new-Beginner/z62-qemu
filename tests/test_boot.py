"""Independent boot traces and native sparse-device positive/negative controls."""
from contextlib import contextmanager, redirect_stdout
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import analyze_boot as boot
import run_qemu as run
from test_qemu import PACKAGE, port, connect, rsp


class BootEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.traces = {role: boot.probe(role) for role in ('master', 'slave')}

    def test_both_original_roles_reach_poll_without_fabricated_response(self):
        for role, trace in self.traces.items():
            with self.subTest(role=role):
                self.assertEqual(trace['instruction_hooks'], 96241)
                self.assertEqual((trace['stop']['pc'], trace['stop']['address']),
                                 (boot.POLL_PC, boot.POLL_ADDRESS))
                self.assertFalse(trace['completion_response_supplied'])
                self.assertTrue(trace['rom_and_page_tables_unchanged'])
                writes = [v for v in trace['accesses'] if v['access'] == 'write']
                self.assertEqual(len(writes), 66)
                self.assertEqual(tuple((v['address'], v['value']) for v in writes[8:]), boot.SYSTEM_WRITES)

    def test_configuration_table_matches_board_and_excludes_status(self):
        self.assertEqual(len(boot.CONFIG_WORDS), 61)
        source = (ROOT / 'qemu/nikon-z6ii.c').read_text()
        table = re.search(r'config_addresses\[\] = \{(.*?)\};', source, re.S).group(1)
        addresses = tuple(int(v, 16) for v in re.findall(r'0x[0-9a-f]+', table))
        self.assertEqual(addresses, boot.CONFIG_WORDS)
        self.assertNotIn(boot.POLL_ADDRESS, addresses)

    def test_seeded_read_modify_write_preserves_unrelated_bits(self):
        for role in ('master', 'slave'):
            with self.subTest(role=role):
                trace = boot.probe(role, seeds={0x04281028: 0xA5A5FC00, 0x0428102C: 0xDAFEDC73})
                self.assertEqual(trace['final_configuration']['0x04281028'], 0xA5A5FC00 & ~0xC00)
                self.assertEqual(trace['final_configuration']['0x0428102C'],
                                 ((0xDAFEDC73 & ~(0x1FF << 16)) | (0x163 << 16)) & ~0x73)
                self.assertTrue(trace['seeded'])

    def test_z7ii_source_comparison_exposes_model_specific_values(self):
        comparison = boot.compare_reference(ROOT / 'third_party/z72-qemu')
        self.assertTrue(comparison['same_address_order'])
        self.assertTrue(comparison['matches_z7ii_slave_bit2_clear_sequence'])
        self.assertEqual([v['address'] for v in comparison['different_from_z7ii_master']],
                         [0x200300B8, 0x2002010C])

    def test_unknown_or_overflow_seed_is_rejected(self):
        for seeds in ({boot.POLL_ADDRESS: 1}, {0x04264000: 1 << 32}):
            with self.assertRaises(ValueError):
                boot.probe('master', seeds=seeds)


class NativeBootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (PACKAGE / 'build-manifest.json').is_file():
            if os.environ.get('Z6II_QEMU_REQUIRED') == '1':
                raise AssertionError('Required native QEMU package is absent')
            raise unittest.SkipTest('Build native QEMU before device checks')
        cls.binary, _ = run.verify_binary(PACKAGE)
        cls.payload_dir = ROOT / 'artifacts/z6ii-1.70'

    @contextmanager
    def debug(self, role='master', qmp=False, **options):
        number, control = port(), port() if qmp else 0
        while control == number:
            control = port()
        payload = self.payload_dir / run.PAYLOADS[role][0]
        options.setdefault('platform_config', False)
        args = run.command(self.binary, payload, role, paused=True,
                           gdb_port=number, qmp_port=control, **options)
        args.remove('-no-reboot')  # QMP reset must remain an actual reset.
        process = subprocess.Popen(args, cwd=payload.parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            with connect(number, process) as sock:
                yield process, sock, control
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate()

    def test_native_full_trace_matches_independent_unicorn(self):
        with redirect_stdout(io.StringIO()):
            report = run.run(PACKAGE, self.payload_dir, ['master', 'slave'],
                             trace_config=True, platform_config=False)
        for row in report['results']:
            with self.subTest(role=row['engine']):
                trace = boot.probe(row['engine'])
                self.assertEqual(row['status'], 'unmodeled_hardware')
                self.assertEqual(row['configuration_accesses'], trace['accesses'])
                self.assertEqual(row['events'][0]['registers'][:3], [boot.POLL_ADDRESS, 1, 40000000])
                self.assertTrue(row['boot']['config_reset_is_hypothesis'])
                self.assertFalse(row['boot']['completion_feedback_modeled'])

    def test_seeded_native_firmware_rmw_preserves_bits_and_original_page_table(self):
        for role in ('master', 'slave'):
            with self.subTest(role=role), self.debug(role) as (_, sock, _):
                seeds = {0x04281028: 0xA5A5FC00, 0x0428102C: 0xDAFEDC73}
                for address, value in seeds.items():
                    self.assertEqual(rsp(sock, f'M{address:x},4:' + value.to_bytes(4, 'little').hex()), 'OK')
                self.assertEqual(rsp(sock, 'Z1,100237a4,4'), 'OK')
                self.assertTrue(rsp(sock, 'c').startswith(('T05', 'S05')))
                values = {0x04281028: 0xA5A5FC00 & ~0xC00,
                          0x0428102C: ((0xDAFEDC73 & ~(0x1FF << 16)) | (0x163 << 16)) & ~0x73}
                for address, expected in values.items():
                    self.assertEqual(rsp(sock, f'm{address:x},4'), expected.to_bytes(4, 'little').hex())
                payload = (self.payload_dir / run.PAYLOADS[role][0]).read_bytes()
                ttbr = int.from_bytes(payload[0xBFCC:0xBFD0], 'little')
                self.assertEqual(ttbr, 0x10030000)
                for offset in range(0, 0x4000, 512):
                    actual = bytes.fromhex(rsp(sock, f'm{ttbr+offset:x},200'))
                    start = ttbr + offset - 0x10020000
                    self.assertEqual(actual, payload[start:start+512])

    def test_disabling_configuration_restores_previous_boundary(self):
        with redirect_stdout(io.StringIO()):
            report = run.run(PACKAGE, self.payload_dir, ['master', 'slave'],
                             boot_config=False, trace_config=True, platform_config=False)
        for row in report['results']:
            self.assertEqual(row['events'][0]['address'], 0x04264000)
            self.assertEqual(row['events'][0]['pc'], 0x1002BDA4)
            self.assertEqual(row['events'][0]['value'], 0x21)
            self.assertFalse(row['boot']['boot_config_enabled'])
            self.assertEqual(row['configuration_accesses'], [])

    def test_all_words_store_reset_and_reject_holes_widths_alignment(self):
        for role in ('master', 'slave'):
            with self.subTest(role=role), self.debug(role, qmp=True) as (process, sock, control):
                for i, address in enumerate(boot.CONFIG_WORDS):
                    self.assertEqual(rsp(sock, f'm{address:x},4'), '00000000')
                    value = (0xDEAD0000 + i).to_bytes(4, 'little').hex()
                    self.assertEqual(rsp(sock, f'M{address:x},4:{value}'), 'OK')
                    self.assertEqual(rsp(sock, f'm{address:x},4'), value)
                for address, size in ((0x04264004, 4), (boot.POLL_ADDRESS, 4),
                                      (0x04264000, 1), (0x04264000, 2),
                                      (0x04264000, 8), (0x04264001, 4), (0x0428202C, 4)):
                    self.assertTrue(rsp(sock, f'm{address:x},{size:x}').startswith('E'))
                    self.assertTrue(rsp(sock, f'M{address:x},{size:x}:' + 'ff' * size).startswith('E'))
                self.assertEqual(rsp(sock, 'm4264000,4'), '0000adde')
                with connect(control, process) as qsock, qsock.makefile('rwb') as stream:
                    self.assertIn('QMP', json.loads(stream.readline()))
                    for command in ('qmp_capabilities', 'system_reset'):
                        stream.write(json.dumps({'execute': command}).encode() + b'\n'); stream.flush()
                        while True:
                            response = json.loads(stream.readline())
                            if 'return' in response:
                                break
                            self.assertNotIn('error', response)
                for address in boot.CONFIG_WORDS:
                    self.assertEqual(rsp(sock, f'm{address:x},4'), '00000000')

    def test_guest_invalid_accesses_are_strictly_logged(self):
        for instruction, address, size in ((0xE5C10000, 0x04264000, 1),
                                            (0xE1C100B0, 0x04264000, 2),
                                            (0xE5810000, 0x04264004, 4)):
            with self.subTest(size=size), self.debug() as (process, sock, _):
                code = instruction.to_bytes(4, 'little').hex()
                self.assertEqual(rsp(sock, f'M4008000,4:{code}'), 'OK')
                registers = rsp(sock, 'g')
                replacements = {0: 0xA5, 1: address, 15: 0x04008000}
                for index, value in replacements.items():
                    registers = registers[:index*8] + value.to_bytes(4, 'little').hex() + registers[(index+1)*8:]
                self.assertEqual(rsp(sock, 'G' + registers), 'OK')
                sock.sendall(b'$c#63')
                output = process.communicate(timeout=10)[0].decode('utf-8', errors='replace')
                self.assertEqual(process.returncode, 2)
                fault = run.parse_output(output)[1][0]
                self.assertEqual((fault['address'], fault['size']), (address, size))
                self.assertFalse(fault['response_fabricated'])


if __name__ == '__main__':
    unittest.main()
