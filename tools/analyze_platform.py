"""Replay Z6II 1.70 dual-channel platform configuration without guest patches.

The synchronous command/status model is an experiment, NOT recovered silicon.
Addresses/commands/acknowledgements are checked against original Z6II execution;
zero reset, immediate completion and successful result words remain assumptions.
No donor Python or QEMU code is executed by this independent Unicorn probe.
"""
import argparse
import hashlib
import json
from pathlib import Path

import unicorn as uc
from unicorn import arm_const as arm
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from analyze_boot import EARLY_WORDS, REFERENCE_COMMIT
from debug_firmware import Debugger, BASE

ROOT = Path(__file__).resolve().parents[1]
# Exact first-channel words observed in both payloads. The second channel has
# the same address layout, not necessarily the same parameter values.
FIRST_WORDS = (
    0x20020000, 0x20020100, 0x2002010C, 0x20021004, 0x20021008, 0x2002100C,
    0x20021010, 0x20021014, 0x20021020, 0x20021024, 0x20021028, 0x2002102C,
    0x20021030, 0x20021038, 0x20022000, 0x20022100, 0x20022300, 0x20022408,
    0x20022414, 0x20023000, 0x20023100, 0x20023118, 0x20023300, 0x20023318,
    0x20023404, 0x20023408, 0x2002340C, 0x20023500, 0x20023504, 0x20023508,
    0x2002350C, 0x20023510, 0x20023514, 0x20023600, 0x20023604, 0x2002360C,
    0x20023610, 0x20023614, 0x20023618, 0x2002361C, 0x20023620, 0x20023624,
    0x20023628, 0x2002362C, 0x20023630, 0x20023634, 0x20023700, 0x20023708,
    0x2002370C, 0x20023800, 0x20023804, 0x20023808, 0x20023900, 0x20023904,
    0x20023A00, 0x20023A04, 0x20023B00, 0x20023B04, 0x20024000, 0x20024100,
    0x20024300, 0x20024400, 0x20024404, 0x20024408, 0x20028000, 0x20028010,
    0x20028030, 0x20028040, 0x20028800, 0x20028810, 0x20028830, 0x20028C00,
    0x20028C10, 0x20028C30, 0x20029000, 0x20029010, 0x20029030, 0x20029040,
    0x20029800, 0x20029810, 0x20029830, 0x20029C00, 0x20029C10, 0x20029C30,
    0x2002A000, 0x2002A010, 0x2002A030, 0x2002A040, 0x2002A800, 0x2002A810,
    0x2002A830, 0x2002AC00, 0x2002AC10, 0x2002AC30, 0x2002B000, 0x2002B010,
    0x2002B030, 0x2002B040, 0x2002B800, 0x2002B810, 0x2002B830, 0x2002BC00,
    0x2002BC10, 0x2002BC30, 0x2002C000, 0x2002C010, 0x2002C030, 0x2002C040,
    0x2002C800, 0x2002C810, 0x2002C830, 0x2002CC00, 0x2002CC10, 0x2002CC30,
    0x2002E000, 0x2002E100, 0x2002E300, 0x2002E400, 0x2002E600, 0x2002E604,
    0x2002E608, 0x2002E700, 0x2002E704, 0x2002E708, 0x2002E70C, 0x2002E710,
    0x20030010, 0x20030014, 0x20030018, 0x2003001C, 0x20030020, 0x20030024,
    0x20030030, 0x20030034, 0x20030040, 0x20030044, 0x20030048, 0x20030050,
    0x20030054, 0x20030058, 0x2003005C, 0x20030060, 0x20030074, 0x20030078,
    0x2003007C, 0x20030080, 0x20030094, 0x20030098, 0x2003009C, 0x200300A0,
    0x200300B8, 0x200300E4, 0x200300E8, 0x200300EC, 0x200300F0, 0x20030128,
    0x2003012C, 0x20030130, 0x20030134, 0x20030148, 0x2003014C, 0x20030150,
    0x20030154, 0x2003016C, 0x20030820, 0x20030824, 0x20030828, 0x2003082C,
    0x20030840, 0x20030850, 0x20030910,
)
WORDS = tuple(sorted((*EARLY_WORDS, *FIRST_WORDS, *(a + 0x20000 for a in FIRST_WORDS))))
FIRST_PAIRS = (
    (0x20022100, 0x20022300, 1, 0),
    (0x20023100, 0x20023300, 0x10001, 0),
    (0x20023118, 0x20023318, 1, 4),
    (0x20024100, 0x20024300, 1, 0),
    *((base + 0x10, base + 0x30, 1, 0) for base in (
        0x20028000, 0x20028800, 0x20028C00, 0x20029000, 0x20029800, 0x20029C00,
        0x2002A000, 0x2002A800, 0x2002AC00, 0x2002B000, 0x2002B800, 0x2002BC00,
        0x2002C000, 0x2002C800, 0x2002CC00)),
    (0x2002E100, 0x2002E300, 1, 0),
)
PAIRS = tuple((c + offset, s + offset, cmd, phase)
              for offset in (0, 0x20000) for c, s, cmd, phase in FIRST_PAIRS)
RESULTS = (0x2003016C, 0x2005016C)
RETURNS = (0x100203A8, 0x100203B0, 0x100203BC, 0x1002BDC4)
TRACE_SHA256 = '6e5001b255c84d7648fe45cd8170abc0d3349484c12b2e0e1f9cb8aa8ca64475'


def probe(role, directory=None, completion_result=0):
    if not isinstance(completion_result, int) or not 0 <= completion_result <= 0xFFFFFFFF:
        raise ValueError('Result must be uint32')
    d = Debugger(role, directory or ROOT / 'artifacts/z6ii-1.70')
    u = d.engine
    u.mem_map(0x04008000, 0x1000)
    for page in sorted({address & ~0xFFF for address in WORDS}):
        u.mem_map(page, 0x1000)
    values = dict.fromkeys(WORDS, 0)
    values.update(dict.fromkeys(RESULTS, completion_result))
    controls = {c: (s, cmd, phase) for c, s, cmd, phase in PAIRS}
    statuses = {s for _, s, _, _ in PAIRS}
    accesses, calls, stops = [], [], []

    def memory(engine, kind, address, size, value, _):
        if (0x04008000 <= address and address + size <= 0x04009000 or
                BASE <= address and address + size <= BASE + len(d.payload)):
            return
        pc = engine.reg_read(arm.UC_ARM_REG_PC)
        access = 'read' if kind == uc.UC_MEM_READ else 'write'
        if address not in values or size != 4:
            stops.append({'address': address, 'pc': pc, 'access': access,
                          'size': size, 'value': value})
            engine.emu_stop()
            return
        if access == 'read':
            value = values[address]
            engine.mem_write(address, value.to_bytes(4, 'little'))
        elif address in statuses:
            values[address] &= ~value  # W1C; writing a one cannot create ready.
        elif address not in RESULTS:
            values[address] = value
            if address in controls:
                status, command, phase = controls[address]
                valid = value == command if phase == 0 else value in [
                    command | (n << 16) for n in range(phase + 1)]
                values[status] = int(valid)
        accesses.append({'access': access, 'address': address, 'pc': pc,
                         'value': value, 'size': size})

    def instruction(engine, address, size, _):
        if address in RETURNS:
            calls.append({'pc': address, 'r0': engine.reg_read(arm.UC_ARM_REG_R0),
                          'sp': engine.reg_read(arm.UC_ARM_REG_SP)})

    u.hook_add(uc.UC_HOOK_MEM_READ | uc.UC_HOOK_MEM_WRITE, memory)
    u.hook_add(uc.UC_HOOK_CODE, instruction)
    snapshot = d.run(1_000_000, 10_000_000)
    if len(stops) != 1 or (stops[0]['address'], stops[0]['pc']) != (0x20016020, 0x1002BDD8):
        raise ValueError(f'Unexpected platform boundary: {stops}, {snapshot["fault"]}')
    if bytes(u.mem_read(BASE, len(d.payload))) != d.payload:
        raise ValueError('Original ROM changed')
    trace_sha = hashlib.sha256(json.dumps(accesses, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if completion_result == 0 and (trace_sha != TRACE_SHA256 or [c['r0'] for c in calls] != [0] * 4):
        raise ValueError('Original Z6II trace or configuration returns changed')
    if {v['address'] for v in accesses} != set(WORDS):
        raise ValueError('Register table is not exactly the observed access set')
    return {'engine': role, 'payload_sha256': d.sha256, 'backend': 'Unicorn ' + uc.__version__,
            'accesses': accesses, 'calls': calls, 'stop': stops[0],
            'instructions': snapshot['instruction_attempts'], 'rom_unchanged': True,
            'final_values': {f'0x{a:08X}': v for a, v in values.items()},
            'trace_sha256': trace_sha, 'auto_complete': True,
            'completion_result': completion_result, 'model_is_experimental': True,
            'menu_reached': False, 'inter_chip_ipc_modeled': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=ROOT / 'analysis/qemu-v0.4.0')
    args = parser.parse_args()
    report = {'words': WORDS, 'pairs': PAIRS, 'results': RESULTS,
              'reference': {'url': 'https://github.com/JKWTCN/z72-qemu', 'commit': REFERENCE_COMMIT,
                            'scope': 'Candidate command/status contracts only; no Z7II firmware executed'},
              'assumptions': ['zero reset', 'synchronous completion on supported command',
                              'W1C status', 'readonly zero success results', 'unsupported command clears ready'],
              'original_reset': [probe(role) for role in ('master', 'slave')],
              'result_failure': [probe(role, completion_result=1) for role in ('master', 'slave')]}
    args.destination.mkdir(parents=True, exist_ok=True)
    (args.destination / 'platform-evidence.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    cs = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    for role in ('master', 'slave'):
        d = Debugger(role, ROOT / 'artifacts/z6ii-1.70')
        lines = ['; Original Z6II 1.70 SHA-256 ' + d.sha256]
        for start, end in ((0x394, 0x3C8), (0x8D4, 0x918), (0x35D0, 0x4520), (0xBDB4, 0xBDF0)):
            lines.extend(f'{i.address:08x}  {i.bytes.hex():<8} {i.mnemonic:<8} {i.op_str}'
                         for i in cs.disasm(d.payload[start:end], BASE + start))
        (args.destination / f'{role}-platform.asm').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Verified both original roles: 346 exact words, 40 command/status pairs, 428 accesses, four returns')
    print('Experimental completion only; MENU and dual-chip transport are not modeled')


if __name__ == '__main__':
    main()
