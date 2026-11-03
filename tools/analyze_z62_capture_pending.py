"""Cross-check r76 callback snapshots against bounded original Thumb instructions."""
import argparse
import hashlib
import json
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from record_z62_action_evidence import require, workspace, digest

MASTER_SHA = 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4'
BASE = 0x10020000


def analyze(master, case, output):
    master, case, output = map(workspace, (master, case, output))
    data = master.read_bytes()
    require(hashlib.sha256(data).hexdigest() == MASTER_SHA, 'Not the original CRC-bearing C1.70 master')
    engine = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    ranges = {}
    for start, size in ((0x103F4CE0, 22), (0x103EC654, 30)):
        code = data[start-BASE:start-BASE+size]
        decoded = list(engine.disasm(code, start))
        require(sum(i.size for i in decoded) == size, 'Incomplete bounded Thumb decoding')
        ranges[hex(start)] = {'bytes': code.hex(), 'sha256': hashlib.sha256(code).hexdigest(),
            'instructions': [{'address': hex(i.address), 'mnemonic': i.mnemonic, 'operands': i.op_str}
                             for i in decoded]}
    instructions = {int(row['address'], 16): (row['mnemonic'], row['operands'])
                    for block in ranges.values() for row in block['instructions']}
    expected = {0x103F4CEE: ('ldr', 'r0, [r4, #0x14]'),
                0x103F4CF0: ('bics', 'r0, r3'), 0x103F4CF2: ('ands', 'r0, r2'),
                0x103EC656: ('movs', 'r3, #0x60'),
                0x103EC658: ('mvn', 'r2, #0x80000000'),
                0x103EC65E: ('bl', '#0x103f4ce0')}
    require(all(instructions.get(pc) == value for pc, value in expected.items()),
            'Callback mask instructions differ from the reviewed original sequence')
    result = json.loads((case/'result.json').read_text(encoding='utf-8'))
    rows = []
    for sample in result['samples']:
        flow = sample['capture_flow']
        if flow['callback'] != '0x103ec627':
            continue
        pending = flow['raw_words'][5]
        rows.append({'virtual_time_ns': sample['virtual_time_ns'], 'label': sample['label'],
            'active_word': flow['active_word'], 'stage': flow['stage'], 'pending': hex(pending),
            'non_exempt_pending': hex(pending & ~0x60 & 0x7fffffff),
            'queue_count': sample['capture_work_queue'].get('count'),
            'callback_result_observed': False})
    require(rows, 'No current run snapshot has this original callback')
    record = {'schema': 1, 'master_sha256': MASTER_SHA, 'case_sha256': digest(case/'result.json'),
        'tool_sha256': digest(Path(__file__)), 'code': ranges, 'samples': rows,
        'callback_pointer_sampled': '0x103ec627', 'thumb_instruction_entry': '0x103ec626',
        'non_exempt_pending_values': sorted({row['non_exempt_pending'] for row in rows}),
        'interpretation': 'Original callback tests active pending bits outside 0x60; sampled 0x4080 is not exempt.',
        'actual_callback_return_observed': False, 'specific_missing_device_identified': False,
        'factory_capture_verified': False, 'camera_accessed': False}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in record.items() if k not in ('code', 'samples')}, ensure_ascii=False))
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--master', type=Path, required=True)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    analyze(args.master, args.case, args.output)
