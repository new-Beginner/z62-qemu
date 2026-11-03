"""Interpret only reviewed, fixed control frames; keep all other links unknown."""
import struct
import z62_statistics_control_snapshot as control


class OriginalMemory:
    def __init__(self, firmware): self.firmware = firmware

    def read(self, address, size):
        offset = address-control.BASE
        if offset < 0 or offset+size > len(self.firmware):
            raise ValueError('Outside original ROM image')
        return self.firmware[offset:offset+size]


def parent_frames(snapshot, firmware):
    result = {'frames': [], 'complete_call_chain_verified': False,
              'frame_layout_scope': 'reviewed-C1.70-only', 'outer_code_live_read': False}
    stack = snapshot.get('stack', {})
    call = snapshot.get('caller', {})
    write = snapshot.get('write_candidate') or {}
    if not (snapshot.get('source_instruction_matches') is True and stack.get('captured') is True and
            write.get('base_matches') is True and write.get('value') == 0x10 and call.get('known') is True):
        return {**result, 'reason': 'missing-verified-control-store-or-stack'}
    raw = bytes.fromhex(stack['raw'])
    if len(raw) != 64: raise ValueError('Require exactly the bounded 64-byte stack')
    stop = snapshot['pc'] == '0x1020a832' and call.get('callsite') == '0x1023c610' and call.get('target') == '0x1020c820'
    start = snapshot['pc'] == '0x1020aafe' and call.get('callsite') == '0x1023c806' and call.get('target') == '0x1020c802'
    if not (stop or start): return {**result, 'reason': 'unreviewed-parent-frame'}
    entry = 0x1023c5a6 if stop else 0x1023c7a8
    expected = bytes.fromhex('70b50546' if stop else '70b588b0')
    if firmware[entry-control.BASE:entry-control.BASE+4] != expected:
        return {**result, 'reason': 'frame-prologue-differs'}
    memory = OriginalMemory(firmware)
    def append(offset, target, owner):
        link = struct.unpack_from('<I', raw, offset)[0]
        decoded = control.caller(memory, {'lr': link}, firmware)
        matches = decoded['known'] and decoded.get('target') == hex(target) and decoded.get('kind') == 'thumb-bl'
        result['frames'].append({'saved_lr_offset': offset, 'frame_owner': hex(owner),
            'saved_lr': hex(link), 'caller': decoded, 'expected_target': hex(target),
            'expected_target_matches': matches, 'provenance': 'observed-stack-reviewed-static-frame'})
        return matches
    if stop:
        # C5A6 pushes r4,r5,r6,lr (16 bytes); the C820/AE72/A830
        # tail wrappers do not change SP. No broader unwinding is attempted.
        if append(12, 0x1023c5a6, entry):
            first = result['frames'][0]['caller']
            if first.get('callsite') == '0x1023889e':
                # C3881E pushes 16 and allocates 32. Its saved LR is at
                # child SP+16+44=60, still inside the captured 64 bytes.
                parent_entry = 0x1023881e
                if firmware[parent_entry-control.BASE:parent_entry-control.BASE+4] == bytes.fromhex('70b588b0'):
                    append(60, parent_entry, parent_entry)
    else:
        # C7A8 pushes 16 and allocates 32. C802 restores its own frame
        # before the tail branch to AE3E, so saved LR remains at +44.
        append(44, 0x1023c7a8, entry)
    return result
