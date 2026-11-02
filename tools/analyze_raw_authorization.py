"""Offline NikonUnlock lead verification against original Z6II C1.70 code.

Never imports/executes the downloaded reference, accesses USB, or patches ROM.
This is isolated function execution, NOT boot, PTP, persistence or RAW recording.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from unicorn import arm_const as arm
import unicorn as uc

from debug_firmware import BASE, Debugger, ROOT

REFERENCE_COMMIT = 'edf2274143f25f3d159efeffa2bc70ef3002e34e'
REFERENCE_SHA256 = '87a042818366f9a88252d9dd4cb5124e0cab445d51fdd60f1fcb8d0698f2a1ab'
REFERENCE_URL = 'https://github.com/summershrimp/NikonUnlock'
KEY_FUNCTIONS = {'HDMIARAW.KEY': 0x10437D6C, 'SRF_FUNC.KEY': 0x10437DA0}
GETTER, SETTER, SYNC = 0x103C3114, 0x103C313E, 0x103C221E
MAGIC_CHECK, MAGIC_ACCEPT, MAGIC_REJECT = 0x10779488, 0x1077949A, 0x107794E8
SCRATCH, RETURN = 0x04008000, 0x04009000


def reference_constants(source):
    """Whitelist just literal assignments; never eval/import the reference."""
    nodes = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ('MAGIC', 'KEYS'):
                if name in nodes:
                    raise ValueError('Duplicate reference constant')
                nodes[name] = node.value
    magic = ast.literal_eval(nodes['MAGIC'])
    if type(magic) is not int or not 0 <= magic <= 0xFFFFFFFF:
        raise ValueError('Reference MAGIC must be uint32')
    table = nodes['KEYS']
    if not isinstance(table, ast.Dict):
        raise ValueError('Reference KEYS must be a literal dictionary')
    keys = {}
    for name, value in zip(table.keys, table.values):
        name = ast.literal_eval(name)
        if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                and isinstance(value.func.value, ast.Name) and value.func.value.id == 'bytes'
                and value.func.attr == 'fromhex' and len(value.args) == 1 and not value.keywords):
            raise ValueError('Only bytes.fromhex(literal) is allowed')
        data = bytes.fromhex(ast.literal_eval(value.args[0]))
        if name in keys or len(data) != 32:
            raise ValueError('Duplicate/wrong-size reference KEY')
        keys[name] = data
    if set(keys) != set(KEY_FUNCTIONS):
        raise ValueError('Unexpected reference KEY names')
    return magic, keys


class FunctionSandbox:
    """Explicit host-selected ABI inputs, original instructions, bounded calls."""
    def __init__(self, directory):
        self.debugger = Debugger('master', directory)
        self.u = self.debugger.engine
        self.payload = self.debugger.payload
        self.u.mem_map(SCRATCH, 0x2000)
        self.config = self.word(0x103C31F4)
        if self.config != 0xC20D2954:
            raise ValueError('Unexpected original configuration pointer')
        self.u.mem_map(self.config & ~0xFFF, 0x1000)
        self.stops = set()
        self.executed = []
        self.u.hook_add(uc.UC_HOOK_CODE, self.instruction)

    def word(self, address):
        return struct.unpack_from('<I', self.payload, address - BASE)[0]

    def instruction(self, u, address, size, _):
        if address in self.stops:
            u.emu_stop()
        else:
            self.executed.append(address)

    def call(self, address, args=(), stops=(), registers=None):
        # Function harness, not an attempt to resume the firmware's boot state.
        for i in range(13):
            self.u.reg_write(getattr(arm, f'UC_ARM_REG_R{i}'), 0)
        self.u.reg_write(arm.UC_ARM_REG_CPSR, 0x1D3)
        self.u.reg_write(arm.UC_ARM_REG_SP, SCRATCH + 0xFF0)
        self.u.reg_write(arm.UC_ARM_REG_LR, RETURN | 1)
        for i, value in enumerate(args):
            self.u.reg_write(getattr(arm, f'UC_ARM_REG_R{i}'), value)
        for name, value in (registers or {}).items():
            self.u.reg_write(getattr(arm, 'UC_ARM_REG_' + name.upper()), value)
        self.stops, self.executed = set(stops), []
        self.u.emu_start(address | 1, RETURN, timeout=1_000_000, count=10_000)
        pc = self.u.reg_read(arm.UC_ARM_REG_PC)
        if pc not in self.stops | {RETURN}:
            raise ValueError(f'Function did not reach its bounded stop: {pc:#x}')
        return {'r0': self.u.reg_read(arm.UC_ARM_REG_R0), 'stop_pc': pc,
                'executed_instructions': len(self.executed)}

    def key(self, function, data, length=None):
        self.u.mem_write(SCRATCH + 0x100, data + b'\0' * 64)
        return self.call(function, (SCRATCH + 0x100, len(data) if length is None else length))

    def original_unchanged(self):
        return bytes(self.u.mem_read(BASE, len(self.payload))) == self.payload


def probe(source, directory=None):
    raw = Path(source).read_bytes()
    if hashlib.sha256(raw).hexdigest() != REFERENCE_SHA256:
        raise ValueError('Reference source does not match the reviewed pinned version')
    magic, keys = reference_constants(raw.decode('utf-8-sig'))
    s = FunctionSandbox(directory or ROOT / 'artifacts/z6ii-1.70')
    if magic != s.word(0x10779558):
        raise ValueError('Reference and original authorization magic disagree')
    # Original initialized-data relocation, not a guessed direct ROM address.
    source_base, destination, length = struct.unpack_from('<III', s.payload, 0xC018)
    filenames = {}
    for name, pointer in (('HDMIARAW.KEY', 0x10779348), ('SRF_FUNC.KEY', 0x10779550)):
        runtime = s.word(pointer)
        if not destination <= runtime <= destination + length - 16:
            raise ValueError('Filename outside initialized-data relocation')
        stored = source_base + runtime - destination
        encoded = s.payload[stored - BASE:stored - BASE + 16]
        decoded = bytes(x ^ 255 for x in encoded).split(b'\0', 1)[0].decode('ascii')
        if decoded != 'A:\\' + name:
            raise ValueError('Original KEY filename mismatch')
        filenames[name] = {'runtime_address': runtime, 'stored_address': stored, 'decoded_path': decoded}
    key_results = {}
    for name, function in KEY_FUNCTIONS.items():
        data = keys[name]
        good = s.key(function, data)
        if good['r0'] != 1:
            raise ValueError('Public KEY rejected by original verifier: ' + name)
        flips = []
        for offset in range(32):
            bad = bytearray(data)
            bad[offset] ^= 1
            result = s.key(function, bytes(bad))
            if result['r0'] != 0:
                raise ValueError('Mutated KEY unexpectedly accepted')
            flips.append(result['r0'])
        wrong_lengths = [s.key(function, data, n)['r0'] for n in (0, 31, 33)]
        other = keys[next(k for k in keys if k != name)]
        swapped = s.key(function, other)['r0']
        if wrong_lengths != [0, 0, 0] or swapped != 0:
            raise ValueError('Original verifier negative control failed')
        key_results[name] = {'function': function, 'sha256': hashlib.sha256(data).hexdigest(),
                             'valid': good, 'single_byte_bit0_flips': flips,
                             'wrong_lengths': wrong_lengths, 'swapped_key': swapped}
    records = {}
    expected = ((0xC051, 0x10779167, 0x10779227), (0xC052, 0x10779259, 0x10779319),
                (0xC101, 0x10779363, 0x10779423), (0xC102, 0x10779455, 0x10779519))
    for index, (command, pre, handler) in enumerate(expected):
        address = 0x119F5C20 + index * 28
        record = struct.unpack_from('<7I', s.payload, address - BASE)
        if record[:6] != (command, 0, 0, 0, pre, handler):
            raise ValueError('PTP command table changed')
        records[hex(command)] = {'record_address': address, 'precondition': pre, 'handler': handler}
    magic_results = []
    for value in (magic, 0, magic ^ 1, 0x548B3FBA):
        result = s.call(MAGIC_CHECK, stops=(MAGIC_ACCEPT, MAGIC_REJECT), registers={'r5': value})
        accepted = value in (magic, 0)
        if result['stop_pc'] != (MAGIC_ACCEPT if accepted else MAGIC_REJECT):
            raise ValueError('Original magic comparison control failed')
        if not accepted and result['r0'] != 0x201D:
            raise ValueError('Unexpected magic rejection response')
        magic_results.append({'argument': value, 'accepted_at_comparison_only': accepted, **result})
    flag_results = []
    for selector, offset, enabled in ((0x12, 4, 0xB2), (0x14, 5, 0x6A)):
        for requested in (0, 1, 2, 255):
            baseline = b'\xA5' * 32
            s.u.mem_write(s.config, baseline)
            setter = s.call(SETTER, (selector, requested), stops=(SYNC,))
            after = bytes(s.u.mem_read(s.config, 32))
            target = enabled if requested == 1 else 0
            expected_bytes = bytearray(baseline)
            expected_bytes[offset] = target
            if after != expected_bytes or setter['stop_pc'] != SYNC:
                raise ValueError('Unexpected setter mutation or sync boundary')
            getter = s.call(GETTER, (selector,))
            if getter['r0'] != int(requested == 1):
                raise ValueError('Original getter did not decode the written state')
            flag_results.append({'selector': selector, 'requested': requested,
                                 'changed_offset': offset, 'stored_value': target,
                                 'setter': setter, 'getter': getter})
    if not s.original_unchanged():
        raise ValueError('Original ROM changed')
    return {'reference': {'url': REFERENCE_URL, 'commit': REFERENCE_COMMIT,
                          'file': 'unlock_hdmi_raw_ii.py', 'sha256': REFERENCE_SHA256},
            'payload_sha256': s.debugger.sha256, 'backend': 'Unicorn ' + uc.__version__,
            'key_filenames': filenames, 'keys': key_results, 'ptp_table': records,
            'magic_comparisons': magic_results, 'state_functions': flag_results,
            'rom_unchanged': True, 'reference_code_executed': False,
            'camera_accessed': False, 'ptp_executed': False, 'persistence_verified': False,
            'raw_recording_verified': False, 'menu_reached': False,
            'scope': 'Isolated original master functions. ABI registers/RAM supplied by host; no boot. '
                     'Setter stops BEFORE synchronization. No filesystem, transport, service mode or commit executed.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, default=ROOT / 'analysis/xiaohongshu-research')
    args = parser.parse_args()
    result = probe(args.reference_source)
    args.destination.mkdir(parents=True, exist_ok=True)
    (args.destination / 'raw-authorization-evidence.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    d = Debugger('master', ROOT / 'artifacts/z6ii-1.70')
    cs = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    lines = ['; Original Z6II C1.70 master SHA256 ' + d.sha256,
             '; Isolated-function evidence, not full boot or hardware authorization.']
    for start, end in ((0x10437D6C, 0x10437D9C), (0x10437DA0, 0x10437DD0),
                       (GETTER, 0x103C316E), (0x10779476, MAGIC_ACCEPT)):
        lines += [f'{i.address:08x} {i.bytes.hex():<10} {i.mnemonic:<8} {i.op_str}'
                  for i in cs.disasm(d.payload[start - BASE:end - BASE], start)]
    (args.destination / 'original-authorization.asm').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('PASS: 2 original KEY verifiers; 64 mutations, 6 length and 2 swap rejections; 4 magic cases; 8 state cases.')
    print('No camera/USB/PTP/commit. Original ROM unchanged. RAW recording, persistence and MENU NOT verified.')


if __name__ == '__main__':
    main()
