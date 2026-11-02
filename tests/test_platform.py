"""v0.4 platform handshake evidence and optional native-QEMU regressions."""
from contextlib import contextmanager, redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import analyze_platform as platform
import run_qemu as run
import test_boot as boot_tests
from test_qemu import PACKAGE, connect, rsp

ROLES = ('master', 'slave')
RETURNS = (0x100203A8, 0x100203B0, 0x100203BC, 0x1002BDC4)
RESULTS = (0x2003016C, 0x2005016C)
STOP = (0x20016020, 0x1002BDD8, 'write', 4, 0x40000000)


def stop_fields(stop):
    return tuple(stop[key] for key in ('address', 'pc', 'access', 'size', 'value'))


class PlatformToolTests(unittest.TestCase):
    def test_launcher_exposes_independent_negative_controls(self):
        args = run.command(Path('qemu.exe'), Path('firmware.bin'), 'master',
                           platform_config=False, auto_complete=False,
                           blocked_control=0x20024100, completion_result=0xFFFFFFFF)
        machine = args[args.index('-machine') + 1].split(',')
        self.assertIn('platform-config=off', machine)
        self.assertIn('auto-complete=off', machine)
        # QEMU accepts decimal and hexadecimal uint properties.
        properties = dict(item.split('=', 1) for item in machine[1:])
        self.assertEqual(int(properties['blocked-control'], 0), 0x20024100)
        self.assertEqual(int(properties['completion-result'], 0), 0xFFFFFFFF)
        default = run.command(Path('qemu.exe'), Path('firmware.bin'), 'master')
        self.assertNotIn('platform-config=off', default[default.index('-machine') + 1])
        self.assertNotIn('auto-complete=off', default[default.index('-machine') + 1])


class PlatformEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.traces = {role: platform.probe(role) for role in ROLES}

    def test_sparse_contract_has_346_words_40_pairs_and_two_results(self):
        self.assertIsInstance(platform.WORDS, tuple)
        self.assertEqual(len(platform.WORDS), 346)
        self.assertEqual(len(set(platform.WORDS)), 346)
        self.assertEqual(len(platform.PAIRS), 40)
        self.assertEqual(len({pair[0] for pair in platform.PAIRS}), 40)
        self.assertEqual(len({pair[1] for pair in platform.PAIRS}), 40)
        self.assertEqual(platform.RESULTS, RESULTS)
        self.assertEqual(platform.RETURNS, RETURNS)
        self.assertTrue(set(boot_tests.boot.CONFIG_WORDS).issubset(platform.WORDS))
        self.assertNotIn(STOP[0], platform.WORDS)
        controls = {pair[0] for pair in platform.PAIRS}
        statuses = {pair[1] for pair in platform.PAIRS}
        self.assertFalse(controls & statuses)
        self.assertFalse((controls | statuses) & set(RESULTS))
        for control, status, command, max_phase in platform.PAIRS:
            self.assertIn(control, platform.WORDS)
            self.assertIn(status, platform.WORDS)
            self.assertGreater(command, 0)
            self.assertGreaterEqual(max_phase, 0)
        self.assertTrue(set(RESULTS).issubset(platform.WORDS))

    def test_both_original_roles_have_exact_trace_counts_and_boundary(self):
        statuses = {pair[1] for pair in platform.PAIRS}
        for role, trace in self.traces.items():
            with self.subTest(role=role):
                accesses = trace['accesses']
                reads = [row for row in accesses if row['access'] == 'read']
                self.assertEqual(len(accesses), 428)
                self.assertEqual(sum(row['access'] == 'write' for row in accesses), 368)
                self.assertEqual(len(reads), 60)
                self.assertEqual(sum(row['address'] in statuses for row in reads), 48)
                self.assertEqual(sum(row['address'] in RESULTS for row in reads), 6)
                self.assertEqual(sum(row['address'] not in statuses | set(RESULTS)
                                     for row in reads), 6)
                self.assertEqual(trace['instructions'], 97660)
                self.assertEqual(stop_fields(trace['stop']), STOP)
                self.assertTrue(trace['auto_complete'])
                self.assertTrue(trace['rom_unchanged'])

    def test_four_real_returns_and_final_state(self):
        for role, trace in self.traces.items():
            with self.subTest(role=role):
                self.assertEqual([call['pc'] for call in trace['calls']], list(RETURNS))
                self.assertEqual([call['r0'] for call in trace['calls']], [0, 0, 0, 0])
                self.assertTrue(all(call['sp'] & 3 == 0 for call in trace['calls']))
                self.assertEqual(set(trace['final_values']),
                                 {f'0x{address:08X}' for address in platform.WORDS})
                for address in RESULTS:
                    self.assertEqual(trace['final_values'][f'0x{address:08X}'], 0)


class NativePlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        boot_tests.NativeBootTests.setUpClass.__func__(cls)

    @contextmanager
    def debug(self, role='master', qmp=False, **options):
        options.setdefault('platform_config', True)
        options.setdefault('trace_config', False)
        with boot_tests.NativeBootTests.debug(self, role, qmp=qmp, **options) as state:
            state[1].settimeout(60)  # Real 40,000,000-iteration timeout loops.
            yield state

    def read_word(self, sock, address):
        value = rsp(sock, f'm{address:x},4')
        self.assertEqual(len(value), 8, value)
        return int.from_bytes(bytes.fromhex(value), 'little')

    def write_word(self, sock, address, value):
        self.assertEqual(rsp(sock, f'M{address:x},4:' + value.to_bytes(4, 'little').hex()), 'OK')

    def registers(self, sock):
        raw = rsp(sock, 'g')
        self.assertGreaterEqual(len(raw), 16 * 8)
        return [int.from_bytes(bytes.fromhex(raw[index*8:(index+1)*8]), 'little')
                for index in range(16)]

    def resume_at(self, sock, pc):
        self.assertEqual(rsp(sock, f'Z1,{pc:x},4'), 'OK')
        self.assertTrue(rsp(sock, 'c').startswith(('T05', 'S05')))
        registers = self.registers(sock)
        self.assertEqual(registers[15], pc)
        self.assertEqual(rsp(sock, f'z1,{pc:x},4'), 'OK')
        return registers

    def reset(self, process, control):
        with connect(control, process) as sock, sock.makefile('rwb') as stream:
            self.assertIn('QMP', json.loads(stream.readline()))
            for command in ('qmp_capabilities', 'system_reset'):
                stream.write(json.dumps({'execute': command}).encode() + b'\n')
                stream.flush()
                while True:
                    response = json.loads(stream.readline())
                    self.assertNotIn('error', response)
                    if 'return' in response:
                        break

    def test_default_native_traces_match_independent_probe_item_for_item(self):
        with redirect_stdout(io.StringIO()):
            report = run.run(PACKAGE, self.payload_dir, list(ROLES), trace_config=True)
        self.assertEqual([row['engine'] for row in report['results']], list(ROLES))
        for row in report['results']:
            with self.subTest(role=row['engine']):
                trace = platform.probe(row['engine'])
                self.assertEqual(row['status'], 'unmodeled_hardware')
                self.assertEqual(row['qemu_exit_code'], 2)
                self.assertEqual(row['configuration_accesses'], trace['accesses'])
                self.assertEqual(len(row['events']), 1)
                self.assertEqual(stop_fields(row['events'][0]), STOP)
                self.assertFalse(row['events'][0]['response_fabricated'])
                self.assertFalse(row['menu_reached'])

    def test_real_return_registers_final_words_and_original_executed_rom(self):
        for role in ROLES:
            with self.subTest(role=role), self.debug(role) as (_, sock, _):
                trace = platform.probe(role)
                for expected in trace['calls']:
                    registers = self.resume_at(sock, expected['pc'])
                    self.assertEqual(registers[0], 0)
                    self.assertEqual(registers[13], expected['sp'])
                for address in platform.WORDS:
                    self.assertEqual(self.read_word(sock, address),
                                     trace['final_values'][f'0x{address:08X}'], hex(address))
                # All executed reset/platform code is in the first 64 KiB.
                # The existing legacy test separately checks the original page table.
                payload = (self.payload_dir / run.PAYLOADS[role][0]).read_bytes()
                for offset in range(0, 0x10000, 512):
                    actual = bytes.fromhex(rsp(sock, f'm{0x10020000+offset:x},200'))
                    self.assertEqual(actual, payload[offset:offset+512], hex(offset))

    def test_all_40_pairs_valid_invalid_phases_w1c_and_channel_isolation(self):
        statuses = [pair[1] for pair in platform.PAIRS]
        for role in ROLES:
            with self.subTest(role=role), self.debug(role) as (_, sock, _):
                for control, status, command, max_phase in platform.PAIRS:
                    with self.subTest(control=hex(control)):
                        self.assertEqual(self.read_word(sock, status), 0)
                        peer_control = control + (0x20000 if control < 0x20040000 else -0x20000)
                        peer = next(pair for pair in platform.PAIRS if pair[0] == peer_control)
                        self.write_word(sock, peer_control, peer[2])
                        self.assertEqual(self.read_word(sock, peer[1]), 1)
                        # Status is W1C, not writable completion storage.
                        self.write_word(sock, status, 0xFFFFFFFF)
                        self.assertEqual(self.read_word(sock, status), 0)
                        for value in (0, command ^ 0x80, command + ((max_phase + 1) << 16),
                                      0x80000000 | command):
                            self.write_word(sock, control, value)
                            self.assertEqual(self.read_word(sock, status), 0, hex(value))
                            self.assertEqual(self.read_word(sock, peer[1]), 1)
                        for phase in range(max_phase + 1):
                            self.write_word(sock, control, command | (phase << 16))
                            for other in statuses:
                                self.assertEqual(self.read_word(sock, other),
                                                 int(other in (status, peer[1])))
                            self.write_word(sock, status, 0)
                            self.assertEqual(self.read_word(sock, status), 1)
                            self.write_word(sock, status, 2)
                            self.assertEqual(self.read_word(sock, status), 1)
                            self.write_word(sock, status, 1)
                            self.assertEqual(self.read_word(sock, status), 0)
                        self.write_word(sock, control, command)
                        self.assertEqual(self.read_word(sock, status), 1)
                        self.write_word(sock, control, 0)
                        self.assertEqual(self.read_word(sock, status), 0)
                        self.assertEqual(self.read_word(sock, peer[1]), 1)
                        self.write_word(sock, peer[1], 1)
                        self.assertEqual(self.read_word(sock, peer[1]), 0)

    def test_all_words_reset_and_passive_storage(self):
        statuses = {pair[1] for pair in platform.PAIRS}
        for role in ROLES:
            with self.subTest(role=role), self.debug(role, qmp=True) as (process, sock, control):
                for index, address in enumerate(platform.WORDS):
                    self.assertEqual(self.read_word(sock, address), 0, hex(address))
                    if address not in statuses | set(RESULTS):
                        value = 0xDEAD0000 + index
                        self.write_word(sock, address, value)
                        self.assertEqual(self.read_word(sock, address), value, hex(address))
                for address, status, command, _ in platform.PAIRS:
                    self.write_word(sock, address, command)
                    self.assertEqual(self.read_word(sock, status), 1)
                self.reset(process, control)
                for address in platform.WORDS:
                    self.assertEqual(self.read_word(sock, address), 0, hex(address))

    def test_result_words_are_readonly_and_reset_keeps_configured_result(self):
        for value in (1, 0xFFFFFFFF):
            with self.subTest(value=value), self.debug(qmp=True, completion_result=value) as (process, sock, control):
                for address in RESULTS:
                    self.assertEqual(self.read_word(sock, address), value)
                    response = rsp(sock, f'M{address:x},4:78563412')
                    self.assertTrue(response == 'OK' or response.startswith('E'), response)
                    self.assertEqual(self.read_word(sock, address), value)
                self.reset(process, control)
                for address in RESULTS:
                    self.assertEqual(self.read_word(sock, address), value)

    def test_new_sparse_holes_widths_and_alignment_are_strict(self):
        address = 0x20024100
        self.assertIn(address, platform.WORDS)
        hole = next(status + 4 for _, status, _, _ in platform.PAIRS
                    if status + 4 not in platform.WORDS)
        for role in ROLES:
            with self.subTest(role=role), self.debug(role) as (_, sock, _):
                for target, size in ((STOP[0], 4), (hole, 4), (address, 1),
                                     (address, 2), (address, 8), (address + 1, 4)):
                    with self.subTest(address=hex(target), size=size):
                        self.assertTrue(rsp(sock, f'm{target:x},{size:x}').startswith('E'))
                        self.assertTrue(rsp(sock, f'M{target:x},{size:x}:' + 'ff' * size).startswith('E'))
                self.assertEqual(self.read_word(sock, address), 0)

    def test_guest_new_invalid_accesses_emit_real_strict_faults(self):
        for instruction, address, size in ((0xE5C10000, 0x20024100, 1),
                                            (0xE1C100B0, 0x20024100, 2),
                                            (0xE5810000, STOP[0], 4)):
            with self.subTest(size=size), self.debug() as (process, sock, _):
                self.write_word(sock, 0x04008000, instruction)
                raw = rsp(sock, 'g')
                for index, value in {0: 0xA5, 1: address, 15: 0x04008000}.items():
                    raw = raw[:index*8] + value.to_bytes(4, 'little').hex() + raw[(index+1)*8:]
                self.assertEqual(rsp(sock, 'G' + raw), 'OK')
                sock.sendall(b'$c#63')
                output = process.communicate(timeout=10)[0].decode('utf-8', errors='replace')
                self.assertEqual(process.returncode, 2)
                events = run.parse_output(output)[1]
                self.assertEqual(len(events), 1)
                self.assertEqual(stop_fields(events[0]), (address, 0x04008000, 'write', size, 0xA5))
                self.assertFalse(events[0]['response_fabricated'])

    def test_blocked_control_only_blocks_selected_channel(self):
        blocked = 0x20024100
        with self.debug(blocked_control=blocked) as (_, sock, _):
            for control, status, command, _ in platform.PAIRS:
                self.write_word(sock, control, command)
                self.assertEqual(self.read_word(sock, status), int(control != blocked))
                self.write_word(sock, status, 1)
                self.assertEqual(self.read_word(sock, status), 0)

    def test_blocked_control_executes_original_40000000_iteration_poll(self):
        blocked = 0x20024100
        status = next(pair[1] for pair in platform.PAIRS if pair[0] == blocked)
        for role in ROLES:
            with self.subTest(role=role), self.debug(role, blocked_control=blocked) as (_, sock, _):
                self.assertEqual(rsp(sock, 'Z1,100208d4,4'), 'OK')
                for pc in RETURNS:
                    self.assertEqual(rsp(sock, f'Z1,{pc:x},4'), 'OK')
                actual, seen_blocked = [], False
                # No register/PC writes, no shortened polling counter, no trace flood.
                for _ in range(64):
                    self.assertTrue(rsp(sock, 'c').startswith(('T05', 'S05')))
                    registers = self.registers(sock)
                    pc = registers[15]
                    if pc == 0x100208D4:
                        self.assertEqual(rsp(sock, 'z1,100208d4,4'), 'OK')
                        if registers[0] == status:
                            self.assertEqual(registers[1:3], [1, 40000000])
                            self.assertEqual(self.read_word(sock, status), 0)
                            seen_blocked = True
                        else:
                            # RSP continue alone re-hits a live hardware breakpoint.
                            # Execute the original cmp, then observe the next call.
                            self.assertTrue(rsp(sock, 's').startswith(('T05', 'S05')))
                            self.assertEqual(self.registers(sock)[15], 0x100208D8)
                            self.assertEqual(rsp(sock, 'Z1,100208d4,4'), 'OK')
                    else:
                        self.assertEqual(pc, RETURNS[len(actual)])
                        actual.append(registers[0])
                        self.assertEqual(rsp(sock, f'z1,{pc:x},4'), 'OK')
                        if len(actual) == 4:
                            break
                self.assertTrue(seen_blocked)
                self.assertEqual(actual, [0, 0x4000, 0, 0])

    def test_completion_result_one_takes_original_firmware_error_returns(self):
        for role in ROLES:
            with self.subTest(role=role), self.debug(role, completion_result=1) as (_, sock, _):
                actual = [self.resume_at(sock, pc)[0] for pc in RETURNS]
                self.assertEqual(actual, [7, 0, 0x70000, 0])
                for address in RESULTS:
                    self.assertEqual(self.read_word(sock, address), 1)

    def test_auto_complete_off_retains_words_but_original_first_return_times_out(self):
        for role in ROLES:
            with self.subTest(role=role), self.debug(role, auto_complete=False) as (_, sock, _):
                for address in platform.WORDS:
                    self.assertEqual(self.read_word(sock, address), 0, hex(address))
                registers = self.resume_at(sock, 0x100208D4)
                self.assertEqual(registers[:3], [0x20022300, 1, 40000000])
                self.assertEqual(self.read_word(sock, 0x20022300), 0)
                # Deliberately execute the untouched real timeout path to its return.
                self.assertEqual(self.resume_at(sock, RETURNS[0])[0], 0x4000)


if __name__ == '__main__':
    unittest.main()
