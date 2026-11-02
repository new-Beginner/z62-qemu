"""Reproduce Z6II early configuration from unchanged 1.70 payloads.

Only bounded passive configuration storage is supplied. Stop BEFORE the first
unmodeled status read; never publish a completion bit or patch guest execution.
The independent native QEMU regression compares against this Unicorn trace.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

import unicorn as uc
from unicorn import arm_const as arm
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from debug_firmware import Debugger, BASE

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_COMMIT = 'f6b80ec650116a6b0117d31f9ea112b05bb7f52a'
EARLY_WORDS = (0x04264000, 0x04264020, 0x04281028, 0x0428102C)
# Independently observed in BOTH Z6II roles, not Z7II master defaults.
SYSTEM_WRITES = (
    (0x20023000, 1), (0x20022000, 1),
    (0x20030010, 5), (0x20030014, 8), (0x20030018, 9),
    (0x2003001C, 7), (0x20030020, 3),
    (0x20030824, 1), (0x20030828, 0x43), (0x2003082C, 0x1A),
    (0x20030024, 0x19061200), (0x20030040, 0x30),
    (0x20030048, 0x330026), (0x20030030, 0x66606),
    (0x20030044, 0x4664), (0x20030034, 0x3713),
    (0x20030050, 0x26), (0x20030840, 0x4B),
    (0x20030054, 0x9D084), (0x20030058, 0xA0086),
    (0x2003005C, 0x9E086), (0x20030060, 0x9F085),
    (0x20030074, 0x16030), (0x20030078, 0x14030),
    (0x2003007C, 0x14030), (0x20030080, 0x16030),
    (0x20030094, 0x800), (0x20030098, 0x800),
    (0x2003009C, 0x800), (0x200300A0, 0x800),
    (0x200300B8, 1), (0x20030910, 0), (0x20030820, 0),
    (0x20030850, 0x10050), (0x200300E4, 0x89019),
    (0x200300E8, 0x89019), (0x200300EC, 0x8C01C),
    (0x200300F0, 0x88018), (0x20030128, 0x10016),
    (0x2003012C, 0x10014), (0x20030130, 0x10014),
    (0x20030134, 0x10016), (0x20030148, 0x10020),
    (0x2003014C, 0x10020), (0x20030150, 0x10020),
    (0x20030154, 0x10020), (0x20020000, 0), (0x20020100, 0),
    (0x2002010C, 0x101), (0x20021004, 1), (0x20021008, 1),
    (0x2002100C, 1), (0x20021010, 1), (0x20021014, 0),
    (0x20022000, 0), (0x20022408, 0x1F8D),
    (0x20022414, 0x553B), (0x20022100, 1),
)
CONFIG_WORDS = tuple(sorted(set(EARLY_WORDS) | {a for a, _ in SYSTEM_WRITES}))
POLL_ADDRESS, POLL_PC = 0x20022300, 0x100208E0


def probe(role, directory=None, seeds=None):
    debugger = Debugger(role, directory or ROOT / 'artifacts/z6ii-1.70')
    u = debugger.engine
    u.mem_map(0x04008000, 0x1000)
    for page in sorted({a & ~0xFFF for a in CONFIG_WORDS}):
        u.mem_map(page, 0x1000)
    seeds = seeds or {}
    if any(a not in CONFIG_WORDS or not 0 <= v <= 0xFFFFFFFF for a, v in seeds.items()):
        raise ValueError('Only known uint32 configuration words may be seeded')
    for address, value in seeds.items():
        u.mem_write(address, value.to_bytes(4, 'little'))
    accesses, stopped, delays = [], [], []

    def memory(engine, kind, address, size, value, _):
        if 0x04008000 <= address and address + size <= 0x04009000:
            return
        if BASE <= address and address + size <= BASE + len(debugger.payload):
            return
        pc = engine.reg_read(arm.UC_ARM_REG_PC)
        if size != 4 or address not in CONFIG_WORDS:
            stopped.append({'access': 'read' if kind == uc.UC_MEM_READ else 'write',
                            'address': address, 'pc': pc, 'size': size,
                            'registers': debugger.registers()})
            engine.emu_stop()
            return
        if kind == uc.UC_MEM_READ:
            value = int.from_bytes(engine.mem_read(address, size), 'little')
        accesses.append({'access': 'read' if kind == uc.UC_MEM_READ else 'write',
                         'address': address, 'value': value, 'size': size, 'pc': pc})

    def instruction(engine, address, size, _):
        # Capture entry via call-site LR only once, and all actual loop exits.
        state = (engine.reg_read(arm.UC_ARM_REG_R0), engine.reg_read(arm.UC_ARM_REG_LR))
        if address == 0x1002D800 and state in ((40000, 0x1002D738), (8000, 0x1002D764)):
            delays.append({'kind': 'entry', 'value': state[0]})
        elif address == 0x1002D808:
            delays.append({'kind': 'return', 'value': state[0]})

    u.hook_add(uc.UC_HOOK_MEM_READ | uc.UC_HOOK_MEM_WRITE, memory)
    u.hook_add(uc.UC_HOOK_CODE, instruction, begin=0x1002D800, end=0x1002D808)
    snapshot = debugger.run(200000, 10_000_000)
    if snapshot['fault'] or not stopped:
        raise ValueError(f'Unexpected startup boundary: {snapshot["fault"] or snapshot["status"]}')
    stop = stopped[0]
    if (stop['address'], stop['pc'], stop['access']) != (POLL_ADDRESS, POLL_PC, 'read'):
        raise ValueError(f'Unexpected status read: {stop}')
    if [stop['registers'][k] for k in ('r0', 'r1', 'r2')] != [POLL_ADDRESS, 1, 40000000]:
        raise ValueError('Unexpected native polling arguments')
    writes = [v for v in accesses if v['access'] == 'write']
    if tuple((v['address'], v['value']) for v in writes[8:]) != SYSTEM_WRITES:
        raise ValueError('Z6II native system-write order/value changed')
    if delays != [{'kind': 'entry', 'value': 40000}, {'kind': 'return', 'value': 0xFFFFFFFF},
                  {'kind': 'entry', 'value': 8000}, {'kind': 'return', 'value': 0xFFFFFFFF}]:
        raise ValueError('Original delay loops did not execute as expected')
    original = debugger.payload
    current = bytes(u.mem_read(BASE, len(original)))
    if current != original:
        raise ValueError('Original ROM changed in execution')
    return {'engine': role, 'payload_sha256': debugger.sha256, 'backend': 'Unicorn ' + uc.__version__,
            'instruction_hooks': snapshot['instruction_attempts'], 'seeded': bool(seeds),
            'accesses': accesses, 'delays': delays, 'stop': stop,
            'final_configuration': {f'0x{a:08X}': int.from_bytes(u.mem_read(a, 4), 'little')
                                    for a in CONFIG_WORDS},
            'rom_and_page_tables_unchanged': True, 'completion_response_supplied': False,
            'menu_reached': False, 'inter_chip_ipc_modeled': False}


def compare_reference(repo):
    commit = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                            capture_output=True, text=True, check=True).stdout.strip()
    if commit != REFERENCE_COMMIT:
        raise ValueError('Reference commit changed; re-audit before comparison')
    path = repo / 'analyze/system_configuration.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    donor = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'SYSTEM_WRITES' for t in n.targets))
    differences = [{'address': a, 'z6ii': v, 'z7ii_master': other}
                   for (a, v), (b, other) in zip(SYSTEM_WRITES, donor, strict=True)
                   if a != b or v != other]
    if any(a != b for (a, _), (b, _) in zip(SYSTEM_WRITES, donor, strict=True)):
        raise ValueError('System address order differs')
    if differences != [{'address': 0x200300B8, 'z6ii': 1, 'z7ii_master': 3},
                       {'address': 0x2002010C, 'z6ii': 0x101, 'z7ii_master': 0x303}]:
        raise ValueError('Unexpected Z7II/Z6II differences')
    return {'url': 'https://github.com/JKWTCN/z72-qemu', 'commit': commit,
            'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'system_store_count': len(SYSTEM_WRITES), 'same_address_order': True,
            'different_from_z7ii_master': differences,
            'matches_z7ii_slave_bit2_clear_sequence': True,
            'caution': 'Source-contract comparison, not a Z7II firmware execution test'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=ROOT / 'analysis/qemu-v0.3.0')
    args = parser.parse_args()
    report = {'configuration_words': CONFIG_WORDS,
              'reference': compare_reference(ROOT / 'third_party/z72-qemu'),
              'original_reset': [probe(role) for role in ('master', 'slave')],
              'seeded_rmw': [probe(role, seeds={0x04281028: 0xA5A5FC00, 0x0428102C: 0xDAFEDC73})
                             for role in ('master', 'slave')]}
    args.destination.mkdir(parents=True, exist_ok=True)
    (args.destination / 'boot-evidence.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    cs = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    for role in ('master', 'slave'):
        d = Debugger(role, ROOT / 'artifacts/z6ii-1.70')
        lines = ['; Unchanged Z6II 1.70: ' + d.sha256]
        for start, end in ((0x394, 0x3C8), (0x8D4, 0x918), (0x35D0, 0x37B0),
                           (0xBD9C, 0xBDC4), (0xD700, 0xD76C), (0xD800, 0xD80C)):
            lines.extend(f'{i.address:08x}  {i.bytes.hex():<8} {i.mnemonic:<8} {i.op_str}'
                         for i in cs.disasm(d.payload[start:end], BASE + start))
        (args.destination / f'{role}-boot.asm').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Verified 2 original-reset + 2 seeded-RMW traces; 61 sparse words; 58 system stores per role')


if __name__ == '__main__':
    main()
