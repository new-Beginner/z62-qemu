"""Reproduce bounded, manually selected Z6II 1.70 DUALEG static evidence.

No camera access, firmware execution, patching, or automatic symbol recovery.
Addresses and fragment boundaries are analyst-selected, not vendor symbols.
Run from any directory: python tools/analyze_dual_expeed.py
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import capstone
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
from capstone.arm import ARM_OP_MEM, ARM_REG_PC

from prepare_firmware import write_identical_or_new

ROOT = Path(__file__).resolve().parents[1]
BASE = 0x10020000
SPECS = {
    'master': {
        'file': 'eg1850_mas_01700.payload.bin',
        'sha256': '7b85aa96ea25d6b23481627313082476619ccb4dd3634a585de4ed896d350071',
        'getters': (0x10200F74, 0x10200F78),
        'id_load': 0x10437730, 'id': 0x10089,
        'task_callback': 0x103E3116, 'initializer': 0x103E3140,
        'receive_handler': 0x103E315C, 'tx_wrapper': 0x10206168,
        'tx_ring_literal_load': 0x1038A736,
        'fragments': [
            ('task_table_getters', 0x10200F74, 0x10200F7C),
            ('task_lookup_second_namespace', 0x103D655A, 0x103D6570),
            ('dualeg_task_binding', 0x10437728, 0x1043774E),
            ('dualeg_commands', 0x103E30B4, 0x103E31BA),
            ('tx_wrapper', 0x10206168, 0x1020617C),
            ('transport_ring_initialization', 0x1038A210, 0x1038A23A),
            ('notification_wrappers', 0x1038A2A2, 0x1038A316),
            ('receive_ring_and_dispatch', 0x1038A38C, 0x1038A488),
            ('notification_callback', 0x1038A488, 0x1038A4EC),
            ('transport_open_and_handshake', 0x1038A666, 0x1038A72E),
            ('transmit_ring', 0x1038A72E, 0x1038A86A),
            ('register_receive_callback', 0x1038A86A, 0x1038A884),
            ('notification_register_writes', 0x102E0812, 0x102E0830),
            ('banked_mmio_access', 0x102E11A0, 0x102E11CA),
            ('event_set_clear_wrappers', 0x1035D374, 0x1035D382),
            ('event_wait_wrapper', 0x1035D43A, 0x1035D45A),
            ('copy_bytes', 0x1035D254, 0x1035D2C8, 'arm'),
            ('read_write_64bit', 0x10439540, 0x10439554, 'arm'),
        ],
    },
    'slave': {
        'file': 'eg1850_sla_01700.payload.bin',
        'sha256': 'ed7be55b90024270c9e8227fa2effd66a0eb8f32e96de23e3d1a7a196cdaf676',
        'getters': (0x10053C18, 0x10053C1C),
        'id_load': 0x1016480C, 'id': 0x10029,
        'task_callback': 0x10054F50, 'initializer': 0x10054FBA,
        'receive_handler': 0x10054FD6, 'tx_wrapper': 0x1005E878,
        'tx_ring_literal_load': 0x100611EE,
        'fragments': [
            ('task_table_getters', 0x10053C18, 0x10053C20),
            ('task_lookup_second_namespace', 0x1005EBF2, 0x1005EC08),
            ('dualeg_task_binding', 0x10164804, 0x1016482A),
            ('dualeg_task_and_initializer', 0x10054F50, 0x10054FD6),
            ('dualeg_receive_switch', 0x10054FD6, 0x10054FE0),
            ('dualeg_receive_case_bodies', 0x10054FEA, 0x1005501A),
            ('tx_wrapper', 0x1005E878, 0x1005E88C),
            ('transport_ring_initialization', 0x10060CC8, 0x10060CF2),
            ('receive_ring_and_dispatch', 0x10060E44, 0x10060F40),
            ('transport_open_and_handshake', 0x1006111E, 0x100611E6),
            ('transmit_ring', 0x100611E6, 0x10061322),
            ('register_receive_callback', 0x10061322, 0x1006133C),
        ],
    },
}


class FirmwareView:
    def __init__(self, role, data):
        self.role, self.data, self.spec = role, data, SPECS[role]
        self.sha256 = hashlib.sha256(data).hexdigest()
        if self.sha256 != self.spec['sha256']:
            raise ValueError(f'{role}: SHA-256 mismatch')
        self.copy_source, self.copy_destination, self.copy_length = struct.unpack_from('<3I', data, 0xC018)
        self.thumb = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
        self.thumb.detail = True
        self.arm = Cs(CS_ARCH_ARM, CS_MODE_ARM)
        self.arm.detail = True

    def offset(self, address, size=1):
        if size < 0:
            raise ValueError('Negative size')
        if self.copy_destination <= address < self.copy_destination + self.copy_length:
            if address + size > self.copy_destination + self.copy_length:
                raise ValueError('Access crosses initialized-data copy boundary')
            address = self.copy_source + address - self.copy_destination
        offset = address - BASE
        if offset < 0 or offset + size > len(self.data):
            raise ValueError(f'Address outside file-backed image: {address:#x}')
        return offset

    def read(self, address, size):
        offset = self.offset(address, size)
        return self.data[offset:offset + size]

    def word(self, address):
        return struct.unpack('<I', self.read(address, 4))[0]

    def instruction(self, address):
        return next(self.thumb.disasm(self.read(address, 4), address, count=1))

    def literal(self, address):
        insn = self.instruction(address)
        if not insn.mnemonic.startswith('ldr') or len(insn.operands) < 2:
            raise ValueError(f'Not a literal load: {address:#x}')
        op = insn.operands[1]
        if op.type != ARM_OP_MEM or op.mem.base != ARM_REG_PC:
            raise ValueError(f'Not PC-relative: {address:#x}')
        location = ((address + 4) & ~3) + op.mem.disp
        return location, self.word(location)

    def record(self, table, index):
        address = table + index * 28
        data = self.read(address, 28)
        name = data[16:28].split(b'\0', 1)[0].decode('ascii')
        return {'index': index, 'runtime_address': address,
                'file_offset': self.offset(address, 28),
                'config_words': list(struct.unpack_from('<4I', data)), 'name': name}

    def disassemble(self, fragment):
        label, start, end, *mode = fragment
        md = self.arm if mode else self.thumb
        lines = [f'; {label}; analyst-selected bounds; mode={"ARM" if mode else "Thumb"}']
        insns = list(md.disasm(self.read(start, end - start), start))
        if not insns or insns[-1].address + insns[-1].size != end:
            raise ValueError(f'Incomplete fragment decoding: {label}')
        for insn in insns:
            note = ''
            if not mode and insn.mnemonic.startswith('ldr') and len(insn.operands) > 1:
                op = insn.operands[1]
                if op.type == ARM_OP_MEM and op.mem.base == ARM_REG_PC:
                    location, value = self.literal(insn.address)
                    note = f' ; [{location:#010x}] = {value:#010x}'
            lines.append(f'{insn.address:08x}: {insn.bytes.hex():8s}  {insn.mnemonic:10s} {insn.op_str}{note}')
        return '\n'.join(lines)


def require_instruction(view, address, mnemonic, operands):
    insn = view.instruction(address)
    actual = (insn.mnemonic, insn.op_str)
    expected = (mnemonic, operands)
    if actual != expected:
        raise ValueError(f'{view.role} {address:#x}: {actual!r} != {expected!r}')
    return {'role': view.role, 'address': address, 'instruction': ' '.join(actual), 'passed': True}


def build_evidence(payload_dir):
    views = {role: FirmwareView(role, (payload_dir / spec['file']).read_bytes())
             for role, spec in SPECS.items()}
    evidence = {'schema_version': 1, 'method': 'bounded static disassembly with analyst-selected anchors',
                'capstone_version': capstone.__version__, 'load_base_hypothesis': BASE,
                'firmware_executed': False, 'hardware_link_verified': False,
                'roles': {}, 'instruction_checks': []}
    texts = {}
    for role, view in views.items():
        spec = view.spec
        first, second = [view.literal(a)[1] for a in spec['getters']]
        delta = second - first
        if delta <= 0 or delta % 28:
            raise ValueError(f'{role}: inconsistent task table spacing')
        task_id = view.literal(spec['id_load'])[1]
        if task_id != spec['id']:
            raise ValueError(f'{role}: unexpected DUALEG ID')
        index = task_id - 0x10000
        record = view.record(second, index)
        if record['name'] != 'DUALEG':
            raise ValueError(f'{role}: task ID does not point to DUALEG')
        first_records = [view.record(first, i) for i in range(delta // 28)]
        prefix = [view.record(second, i) for i in range(index + 1)]
        evidence['roles'][role] = {
            'payload': spec['file'], 'sha256': view.sha256, 'size': len(view.data),
            'initialized_data_copy': {'source': view.copy_source, 'destination': view.copy_destination,
                                      'length': view.copy_length},
            'first_task_table': first, 'second_task_table': second,
            'first_task_records': first_records,
            'second_task_records_through_dualeg_only': prefix,
            'dualeg': {'task_id': task_id, 'record': record, 'initializer': spec['initializer'],
                       'task_callback': spec['task_callback'], 'receive_handler': spec['receive_handler']},
            'tx_ring_local_virtual_address': view.literal(spec['tx_ring_literal_load'])[1],
        }
        texts[f'{role}.asm'] = '\n\n'.join(view.disassemble(f) for f in spec['fragments']) + '\n'
    # Confirm concrete instructions, not just strings or apparent numeric matches.
    checks = {
        'master': [
            (0x10437732, 'bl', '#0x103d655a'), (0x10437736, 'bl', '#0x103e3140'),
            (0x103E3146, 'movs', 'r2, #3'), (0x103E314C, 'bl', '#0x1035c95e'),
            (0x103E319A, 'movs', 'r0, #1'), (0x103E319C, 'b.w', '#0x1038a86a'),
            (0x10206168, 'cmp.w', 'r1, #0x100'), (0x10206174, 'movs', 'r0, #1'),
            (0x10206176, 'b.w', '#0x1038a72e'),
            (0x103E30C2, 'movs', 'r0, #5'), (0x103E30C8, 'bl', '#0x10206168'),
            (0x103E30D0, 'movs', 'r1, #2'), (0x103E30D2, 'movw', 'r3, #0x1b58'),
            (0x103E30D6, 'bl', '#0x1035d43a'),
            (0x103E30E8, 'movs', 'r0, #8'), (0x103E30EE, 'bl', '#0x10206168'),
            (0x103E30F6, 'movs', 'r1, #4'), (0x103E30FC, 'bl', '#0x1035d43a'),
            (0x103E3120, 'movs', 'r0, #1'), (0x103E3124, 'bl', '#0x10206168'),
            (0x103E3164, 'cmp', 'r2, #2'), (0x103E3168, 'cmp', 'r2, #6'),
            (0x103E316C, 'cmp', 'r2, #9'), (0x103E3170, 'movs', 'r1, #4'),
            (0x103E317E, 'movs', 'r2, #0xa'), (0x103E3180, 'blx', '#0x1035d254'),
            (0x103E3192, 'movs', 'r1, #2'),
            (0x1038A7D0, 'add.w', 'r0, r0, r0, lsl #5'),
            (0x1038A7DA, 'str', 'r2, [r0, #0x18]'),
            (0x1038A7DC, 'strb.w', 'sb, [r0, #0x1c]'),
            (0x1038A7E4, 'strb', 'r2, [r0, #0x1d]'),
            (0x1038A7F2, 'strh', 'r7, [r0, #0x1e]'),
            (0x1038A812, 'cmp', 'r0, #0xc0'),
            (0x1038A808, 'dmb', 'sy'), (0x1038A45E, 'blx', 'r1'),
        ],
        'slave': [
            (0x1016480E, 'bl', '#0x1005ebf2'), (0x10164812, 'bl', '#0x10054fba'),
            (0x10054FC0, 'movs', 'r2, #0x1f'), (0x10054FC6, 'bl', '#0x1005ea02'),
            (0x1005500C, 'movs', 'r0, #1'), (0x1005500E, 'b.w', '#0x10061322'),
            (0x1005E884, 'movs', 'r0, #1'), (0x1005E886, 'b.w', '#0x100611e6'),
            (0x10054F68, 'movs', 'r0, #2'), (0x10054F66, 'movs', 'r1, #0xa'),
            (0x10054F64, 'ldr', 'r2, [pc, #0xb4]'),
            (0x10054F88, 'movs', 'r0, #4'), (0x10054F94, 'bl', '#0x10053f64'),
            (0x10054F9A, 'movs', 'r0, #6'), (0x10054FA6, 'bl', '#0x10053f3c'),
            (0x10054FB0, 'movs', 'r0, #9'), (0x10054FB4, 'b.w', '#0x1005e878'),
            (0x10054FDC, 'tbb', '[pc, r0]'),
            (0x10054FEA, 'movs', 'r1, #1'), (0x10054FEE, 'movs', 'r1, #4'),
            (0x10054FF2, 'movs', 'r1, #8'), (0x10054FFE, 'movs', 'r1, #0x10'),
            (0x10060F16, 'blx', 'r1'),
        ],
    }
    for role, rows in checks.items():
        for address, mnemonic, operands in rows:
            evidence['instruction_checks'].append(require_instruction(views[role], address, mnemonic, operands))
    targets = [0x10054FE0 + 2 * x for x in views['slave'].read(0x10054FE0, 9)]
    expected = [0x10055008, 0x10054FEA, 0x10055008, 0x10054FEE, 0x10055008,
                0x10054FF2, 0x10055008, 0x10054FF6, 0x10054FFE]
    if targets != expected:
        raise ValueError('Unexpected slave receive switch table')
    evidence['slave_receive_jump_table'] = {str(i): a for i, a in enumerate(targets)}
    evidence['protocol_static_interpretation'] = {
        'logical_channel': 1, 'slots': 192, 'slot_stride': 264, 'header_bytes': 8,
        'maximum_payload_bytes': 256, 'ring_records_offset': 24,
        'header_fields': ['u32 message', 'u8 channel', 'u8 counter_low_byte', 'u16 payload_length'],
        'handshake_words': [0x00C00108, 0xAA550001],
        'observed_master_requests': [1, 5, 7, 8],
        'slave_reply_ids': [2, 4, 6, 9],
        'master_handled_reply_ids': [2, 6, 9],
        'unknowns': ['physical interconnect', 'remote window translation', 'real scheduling and time units',
                     'meaning of the ten-byte payload', 'AF/ISP/codec workload allocation'],
    }
    # Named communication strings are leads only; do not infer a transport from presence.
    evidence['string_leads_not_transport_proof'] = {}
    for role, view in views.items():
        leads = {}
        for needle in (b'TwoChipConfKey\0', b'CA7_CPU0_COM_RX', b'CA7_CPU1_COM_RX',
                       b'Arm926IpcuService', b'PCIE_OWN', b'PCIE_EP'):
            off = view.data.find(needle)
            leads[needle.rstrip(b'\0').decode()] = BASE + off if off >= 0 else None
        evidence['string_leads_not_transport_proof'][role] = leads
    return evidence, texts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload-dir', type=Path, default=ROOT / 'artifacts/z6ii-1.70')
    parser.add_argument('--output', type=Path, default=ROOT / 'analysis/dual-expeed6')
    args = parser.parse_args()
    evidence, texts = build_evidence(args.payload_dir)
    texts['evidence.json'] = json.dumps(evidence, ensure_ascii=False, indent=2) + '\n'
    texts['SHA256SUMS.txt'] = ''.join(f'{hashlib.sha256(text.encode()).hexdigest()}  {name}\n'
                                   for name, text in sorted(texts.items()))
    # Preflight the entire batch; refuse to clobber any existing, different artifact.
    for name, text in texts.items():
        target = args.output / name
        if target.exists() and target.read_bytes() != text.encode():
            raise ValueError(f'Refusing to overwrite different evidence: {target}')
    for name, text in texts.items():
        write_identical_or_new(args.output / name, text.encode())
    print(f'Verified 2 payload hashes, 2 DUALEG task bindings, {len(evidence["instruction_checks"])} instruction anchors.')
    print(f'Evidence: {args.output.resolve()}')
    print('Static evidence only; no real IPC, hardware link, or camera boot verified.')


if __name__ == '__main__':
    main()
