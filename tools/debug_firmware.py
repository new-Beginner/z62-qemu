"""Strict Windows/Linux ARM startup probe, NOT a complete Z6II/menu emulator."""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import shlex

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
import unicorn as uc
from unicorn import arm_const as arm

ROOT = Path(__file__).resolve().parents[1]
BASE = 0x10020000
PAYLOADS = {
    'master': ('eg1850_mas_01700.payload.bin', '7b85aa96ea25d6b23481627313082476619ccb4dd3634a585de4ed896d350071'),
    'slave': ('eg1850_sla_01700.payload.bin', 'ed7be55b90024270c9e8227fa2effd66a0eb8f32e96de23e3d1a7a196cdaf676')}
REGISTERS = {f'r{i}': getattr(arm, f'UC_ARM_REG_R{i}') for i in range(13)}
REGISTERS.update(sp=arm.UC_ARM_REG_SP, lr=arm.UC_ARM_REG_LR,
                 pc=arm.UC_ARM_REG_PC, cpsr=arm.UC_ARM_REG_CPSR)
ACCESS_NAMES = {uc.UC_MEM_READ_UNMAPPED: 'read', uc.UC_MEM_WRITE_UNMAPPED: 'write',
                uc.UC_MEM_FETCH_UNMAPPED: 'fetch', uc.UC_MEM_WRITE_PROT: 'write_protected',
                uc.UC_MEM_READ_PROT: 'read_protected', uc.UC_MEM_FETCH_PROT: 'fetch_protected'}


class Debugger:
    """One isolated engine/core0. No shared memory, IPC, GIC, LCD or invented MMIO."""
    def __init__(self, role, directory):
        name, expected = PAYLOADS[role]
        self.payload = (directory / name).read_bytes()
        actual = hashlib.sha256(self.payload).hexdigest()
        if actual != expected:
            raise ValueError(f'{role} payload SHA-256 mismatch; run prepare_firmware.py')
        self.role, self.sha256 = role, actual
        self.engine = uc.Uc(uc.UC_ARCH_ARM, uc.UC_MODE_ARM)
        # Family execution choice, not a claim about physical EXPEED silicon.
        self.engine.ctl_set_cpu_model(arm.UC_CPU_ARM_CORTEX_A15)
        self.engine.mem_map(BASE, (len(self.payload) + 4095) & ~4095)
        self.engine.mem_write(BASE, self.payload)
        self.engine.mem_protect(BASE, (len(self.payload) + 4095) & ~4095,
                                uc.UC_PROT_READ | uc.UC_PROT_EXEC)
        self.engine.reg_write(arm.UC_ARM_REG_CPSR, 0x1D3)
        self.engine.reg_write(arm.UC_ARM_REG_PC, BASE)
        self.attempts = 0
        self.trace = deque(maxlen=128)
        self.breakpoints = set()
        self.status = 'paused'
        self.fault = None
        self.error = None
        self.engine.hook_add(uc.UC_HOOK_CODE, self._instruction)
        self.engine.hook_add(uc.UC_HOOK_MEM_INVALID, self._invalid_memory)

    def registers(self):
        return {name: self.engine.reg_read(reg) for name, reg in REGISTERS.items()}

    def disassemble(self, address=None, count=12):
        address = self.engine.reg_read(arm.UC_ARM_REG_PC) if address is None else address
        thumb = bool(self.engine.reg_read(arm.UC_ARM_REG_CPSR) & 0x20)
        mode = CS_MODE_THUMB if thumb else CS_MODE_ARM
        raw = bytes(self.engine.mem_read(address & ~1, count * 4))
        return [f'{i.address:08x}  {i.bytes.hex():<12} {i.mnemonic:<9} {i.op_str}'
                for i in list(Cs(CS_ARCH_ARM, mode).disasm(raw, address & ~1))[:count]]

    def _instruction(self, engine, address, size, _):
        if address in self.breakpoints:
            self.status = 'breakpoint'
            engine.emu_stop()
            return
        self.attempts += 1
        self.trace.append({'address': address, 'size': size,
                           'bytes': bytes(engine.mem_read(address, size)).hex(),
                           'thumb': bool(engine.reg_read(arm.UC_ARM_REG_CPSR) & 0x20)})

    def _invalid_memory(self, engine, kind, address, size, value, _):
        self.fault = {'access': ACCESS_NAMES.get(kind, str(kind)), 'address': address,
                      'size': size, 'value': value,
                      'pc': engine.reg_read(arm.UC_ARM_REG_PC)}
        self.status = 'unmodeled_memory_access'
        return False  # Deliberately do not fabricate RAM or device responses.

    def run(self, count=100000, timeout_us=2_000_000):
        if count < 1 or count > 10_000_000:
            raise ValueError('Instruction count must be 1..10000000')
        if self.fault:
            raise ValueError('Faulted session: start a new session; no hardware model is installed')
        self.status = 'running'
        before = self.attempts
        pc = self.engine.reg_read(arm.UC_ARM_REG_PC)
        thumb = bool(self.engine.reg_read(arm.UC_ARM_REG_CPSR) & 0x20)
        try:
            self.engine.emu_start(pc | int(thumb), BASE + len(self.payload),
                                  count=count, timeout=timeout_us)
        except uc.UcError as exc:
            self.error = str(exc)
            if not self.fault:
                self.status = 'emulator_exception'
        if self.status == 'running':
            self.status = 'instruction_limit' if self.attempts - before >= count else 'paused_or_timeout'
        return self.snapshot()

    def snapshot(self):
        return {'lab_version': '0.1.0', 'role': self.role, 'payload_sha256': self.sha256,
                'backend': f'Unicorn {uc.__version__}', 'cpu_model': 'cortex-a15 (execution hypothesis)',
                'candidate_load_base': BASE, 'core_id': 0,
                'status': self.status, 'instruction_attempts': self.attempts,
                'count_semantics': 'pre-instruction hooks; faulting instruction is included',
                'registers': self.registers(), 'fault': self.fault, 'error': self.error,
                'recent_trace': list(self.trace),
                'full_machine_booted': False, 'menu_reached': False,
                'dual_engine_ipc_modeled': False,
                'limits': 'One engine/core0; ROM only. No RAM, IRQ, timer, peripheral, LCD or IPC model.'}

    def repl(self):
        print('Commands: regs | disasm [address] | step [n] | run [n] | break addr | delete addr | mem addr size | quit')
        print('Numeric addresses: use 0x prefix. Unknown memory stops execution, not emulated.')
        while True:
            try:
                words = shlex.split(input(f'z6ii-{self.role}> '))
                if not words:
                    continue
                cmd, *args = words
                if cmd in ('quit', 'q', 'exit'):
                    return
                if cmd == 'regs':
                    print(' '.join(f'{k}={v:08x}' for k, v in self.registers().items()))
                elif cmd == 'disasm':
                    print('\n'.join(self.disassemble(int(args[0], 0) if args else None)))
                elif cmd in ('step', 'run'):
                    n = int(args[0], 0) if args else (1 if cmd == 'step' else 100000)
                    snapshot = self.run(n)
                    print(snapshot['status'], f'pc={snapshot["registers"]["pc"]:08x}', snapshot['fault'])
                elif cmd == 'break':
                    address = int(args[0], 0)
                    self.breakpoints.add(address & ~1)
                    print(f'Breakpoint set: {address & ~1:08x}; delete it before stepping past it')
                elif cmd == 'delete':
                    self.breakpoints.discard(int(args[0], 0) & ~1)
                elif cmd == 'mem':
                    address, length = (int(x, 0) for x in args)
                    if not 1 <= length <= 4096:
                        raise ValueError('Read size must be 1..4096')
                    print(bytes(self.engine.mem_read(address, length)).hex(' '))
                else:
                    print('Unknown command')
            except (ValueError, IndexError, uc.UcError) as exc:
                print('error:', exc)
            except (EOFError, KeyboardInterrupt):
                print()
                return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=PAYLOADS, default='master')
    parser.add_argument('--artifacts', type=Path, default=ROOT / 'artifacts/z6ii-1.70')
    parser.add_argument('--instructions', type=int, default=100000)
    parser.add_argument('--interactive', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        debugger = Debugger(args.role, args.artifacts)
        if args.interactive:
            debugger.repl()
        else:
            debugger.run(args.instructions)
        result = debugger.snapshot()
        if args.report:
            report = args.report.resolve()
            if report.exists():
                raise ValueError(f'Report already exists: {report}; choose a new path')
            if report.is_relative_to(args.artifacts.resolve()):
                raise ValueError('Keep diagnostic reports outside immutable firmware artifacts')
            report.parent.mkdir(parents=True, exist_ok=True)
            with report.open('x', encoding='utf-8') as stream:
                json.dump(result, stream, indent=2)
                stream.write('\n')
        print(json.dumps({k: v for k, v in result.items() if k != 'recent_trace'}, indent=2))
        print('Startup probe only: original menu NOT reached.')
    except (OSError, ValueError, uc.UcError) as exc:
        parser.exit(1, f'error: {exc}\n')


if __name__ == '__main__':
    main()
