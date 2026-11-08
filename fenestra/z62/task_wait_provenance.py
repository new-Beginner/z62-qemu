"""Stock wait-record provenance from bounded r7 frames; not public RTOS ABI."""
import argparse
from collections import Counter
import json
from pathlib import Path

from startup_contract import ROOT, BASE, PROFILES, read_inputs, require, sha, instructions, arm_branch
from task_context import collect as context_collect, check_event, words
from verify_task_context import check_run

TOOL = 'fenestra-z62-task-wait-provenance/0.1.0'


def unique(image, pattern):
    raw = bytes.fromhex(pattern)
    at = image.find(raw)
    require(at >= 0 and image.find(raw, at + 1) < 0, 'Original anchor is missing/ambiguous')
    return BASE + at


def collect():
    contexts, images = context_collect(), read_inputs()
    roles = {}
    for role, image in images.items():
        bit = unique(image, 'f04f2de90cd04de20090a0e10000a0e303a0a0e10260a0e10170a0e1')
        receive = unique(image, 'f74f2de908d04de20090a0e10000a0e301b0a0e100008de5')
        registrar = unique(image, '080094e5051196e7340081e5') - 0x18
        wrapper = unique(image, 'b02f10ee50319fe5032002e2022193e7303092e570c092e5')
        require(image[registrar - BASE:registrar - BASE + 12] == bytes.fromhex('70402de90120a0e10040a0e1'),
                'Original registration prologue changed')
        require(arm_branch(image, wrapper - BASE + 0x44) == registrar, 'Wait wrapper registration branch changed')
        result = dict(context=contexts['roles'][role], wait_object_handle_tcb_offset=0x34,
            caller_stack_tcb_offset=0x40, registrar=registrar, wrapper=wrapper,
            registration_instructions=instructions(image, registrar, 0xA8, False),
            wrapper_instructions=instructions(image, wrapper, 0x54, False))
        for kind, entry, svc_offset, size in (('bit_test', bit, 0x340, 0x364),
                                               ('linked_receive', receive, 0x2A0, 0x2C4)):
            svc = entry + svc_offset
            require(image[svc - BASE:svc - BASE + 8] == bytes.fromhex('0800000f0100000a'),
                    'Conditional SVC #8/resume branch changed')
            body = image[entry - BASE:entry - BASE + size]
            if kind == 'bit_test':
                require(bytes.fromhex('447080e5') in body and bytes.fromhex('486080e5') in body and
                        bytes.fromhex('4ca080e5') in body and bytes.fromhex('40d081e5') in body,
                        'Bit-test saved-argument stores changed')
            else:
                require(bytes.fromhex('44b080e5') in body and bytes.fromhex('40d081e5') in body,
                        'Receive saved-argument stores changed')
            result[kind] = dict(entry=entry, svc=svc, resume=svc + 4,
                                instructions=instructions(image, entry, size, False))
        roles[role] = result
    return dict(schema=1, tool=TOOL, inputs=PROFILES, roles=roles,
        imports_equivalent='Raw ARM/Thumb: original conditional SVC #8, saved-argument STRs, object+8 to current TCB+34 and original wait-list insertion. No conventional import table.',
        public_task_abi_verified=False, task_identity_verified=False, hardware_root_cause_identified=False)


def analyze_event(event, p):
    context = check_event(event, p['context'])
    pc = context['resume_pc_candidate']
    kind = next((k for k in ('bit_test', 'linked_receive') if pc == p[k]['resume']), None)
    result = dict(sequence=event['sequence'], role=event['role'], thread=event['thread'],
        control_block=context['control_block'], resume_pc=pc, kind=kind,
        association_verified=False, hardware_root_cause_identified=False,
        task_identity_verified=False, reason='unmapped-resume-path')
    if kind is None:
        return result
    frame = words(bytes.fromhex(event['frame']), 96)
    block = words(bytes.fromhex(event['tcb']), 256)
    # These are same-pause relations to the original stores, not a claim that
    # every context switch is blocked or that later TCB addresses remain alive.
    same_call = (block[0x40 // 4] == event['frame_address'] + 76 and
                 frame[15] == pc and frame[16] & 0x3F == 0x13)
    if kind == 'bit_test':
        same_args = (block[0x34 // 4] == frame[9] and block[0x44 // 4] == frame[7] and
                     block[0x48 // 4] == frame[6] and block[0x4C // 4] == frame[10])
        args = dict(mask=block[0x44 // 4], options=block[0x48 // 4], output_pointer=block[0x4C // 4])
    else:
        # Original prologue pushes r0..r2 then reserves 8 bytes: the saved r0
        # argument is caller-SP+8, i.e. frame+84. r9 is later clobbered.
        same_args = (block[0x34 // 4] == frame[21] and block[0x44 // 4] == frame[11] == frame[22])
        args = dict(output_pointer=block[0x44 // 4])
    if not same_call or not same_args:
        result['reason'] = 'saved-arguments-disagree'
        return result
    result.update(association_verified=True, reason='same-pause-original-stores-match',
        object_handle=block[0x34 // 4], arguments=args,
        semantic_limit='Recorded handle/arguments only; no object RAM contents, business name, physical source or lifecycle proof')
    return result


def summarize(record, contract):
    rows = [analyze_event(e, contract['roles'][e['role']]) for e in record['events']]
    groups = Counter()
    for row in rows:
        if row['association_verified']:
            args = row['arguments']
            groups[(row['role'], row['kind'], row['object_handle'], args.get('mask'), args.get('options'))] += 1
    return dict(event_count=len(rows), associated_events=sum(r['association_verified'] for r in rows),
        unassociated_events=sum(not r['association_verified'] for r in rows),
        groups=[dict(role=k[0], kind=k[1], object_handle=k[2], mask=k[3], options=k[4], count=n)
                for k, n in sorted(groups.items())], events=rows,
        task_identity_verified=False, waiting_root_cause_identified=False,
        final_saved_interpreted_as_same_lifetime=False, firmware_integrated=False, flash_safety_verified=False)


def analyze(paths, output):
    require(not output.exists() and output.resolve().is_relative_to(ROOT / 'analysis'), 'Use new analysis output')
    contract = collect()
    runs = []
    for path in paths:
        record = json.loads(path.read_text(encoding='utf-8'))
        check_run(record)
        require(sha(path.with_suffix('.qemu.log').read_bytes()) == record['log_sha256'], 'QEMU log changed')
        row = summarize(record, contract)
        row.update(path=path.relative_to(ROOT).as_posix(), sha256=sha(path.read_bytes()), pid=record['owned_pid'])
        runs.append(row)
    result = dict(schema=1, tool=TOOL, contract=contract, runs=runs,
        source_sha256=sha(Path(__file__).read_bytes()),
        replay_verifier_sha256=sha((ROOT / 'fenestra/z62/verify_task_context.py').read_bytes()),
        task_identity_verified=False, waiting_root_cause_identified=False,
        firmware_integrated=False, flash_safety_verified=False)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    analyze([p.resolve() for p in args.run], args.output.resolve())
