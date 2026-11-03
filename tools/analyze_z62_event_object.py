"""Validate the opaque kernel argument boundary; do not treat it as flag bits."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_ARM
from probe_z62_capture_submit import MASTER_SHA
from record_z62_action_evidence import workspace, digest, require


def analyze(master, control, output):
    master, control, output = map(workspace, (master, control, output))
    data = master.read_bytes(); require(digest(master) == MASTER_SHA, 'Original master required')
    blocks = []
    for pc, mode, length in ((0x1035D43A, CS_MODE_THUMB, 32), (0x10104A14, CS_MODE_ARM, 32)):
        raw = data[pc-0x10020000:pc-0x10020000+length]
        decoded = list(Cs(CS_ARCH_ARM, mode).disasm(raw, pc))
        require(sum(i.size for i in decoded) == length, 'Incomplete instruction decoding')
        blocks.append({'start': hex(pc), 'mode': 'Thumb' if mode == CS_MODE_THUMB else 'ARM',
            'bytes': raw.hex(), 'sha256': hashlib.sha256(raw).hexdigest(),
            'instructions': [{'pc': hex(i.address), 'mnemonic': i.mnemonic, 'operands': i.op_str} for i in decoded]})
    insns = {int(row['pc'], 16): (row['mnemonic'], row['operands'])
             for block in blocks for row in block['instructions']}
    require(insns[0x1035D446] == ('ldr', 'r0, [r0]') and
            insns[0x1035D448] == ('mov', 'r3, r2') and
            insns[0x1035D44A] == ('movs', 'r2, #0') and
            insns[0x1035D44C] == ('blx', '#0x10104a14') and
            insns[0x10104A24] == ('svc', '#6'), 'Reviewed kernel argument boundary differs')
    trace = json.loads(control.read_text(encoding='utf-8'))
    rows = [hit for hit in trace['hits'] if hit['label'] == 'input-ready-wait-call']
    require(len(rows) == 3 and all(hit['registers']['r0'] == '0xc188808c' for hit in rows), 'Wrong wait object')
    record = {'schema': 1, 'master_sha256': MASTER_SHA, 'control_sha256': digest(control),
        'analyzer_sha256': digest(Path(__file__)), 'blocks': blocks,
        'kernel_stub_literal': hex(struct.unpack_from('<I', data, 0x10104A34-0x10020000)[0]),
        'object_address': '0xc188808c',
        'sampled_object_first_words': sorted({hit['input_words']['0xc188808c'] for hit in rows}),
        'required_mask': '0x5b00000', 'object_first_word_is_event_pattern_proven': False,
        'kernel_event_pattern_read': False,
        'interpretation': 'The wrapper dereferences the object pointer and passes the stored first word to an ARM kernel stub. This opaque kernel argument is not a verified event pattern.',
        'invalid_inference': 'Do not compare 0x01000111 with 0x05B00000 to claim particular readiness bits are present or missing.',
        'wait_timeouts_still_observed': True, 'camera_accessed': False}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in record.items() if k != 'blocks'}, ensure_ascii=False))
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--master', type=Path, required=True)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); analyze(args.master, args.control, args.output)
