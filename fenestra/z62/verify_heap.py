"""Recompute bounded heap observations; reject altered records, never certify flashing."""
import argparse
import copy
import json
from pathlib import Path
import re

from heap_calls import collect, analyze_events, summarize, FALSE_FIELDS, TOOL
from pool_calls import Ledger, REGISTERS, SYSTEM
from observe_heap import SOURCES
from observe_startup import QEMU_REL, QEMU_SHA, stopped_thread
from startup_contract import ROOT, BASE, require, read_inputs, sha
from verify_pool import check_command


def check_run(r, expected, images):
    require(r['schema'] == 1 and r['tool'] == TOOL and r['completed'] is True and
            r['owned_process_closed'] is True and r['exit_code'] == 0 and 'failure' not in r,
            'Incomplete heap observation')
    require(r['contract'] == expected and r['qemu_sha256'] == QEMU_SHA, 'Contract/QEMU identity differs')
    require(all(r[k] is False for k in FALSE_FIELDS), 'Observation scope changed')
    require(r['firmware_loaded'] is True and r['reset_pc_initialized_by_qemu_loader'] is True and
            r['breakpoint_timing_perturbed'] is True, 'Stock execution setup differs')
    require(r['owned_shutdown'] == 'QMP quit; NOT camera normal shutdown', 'Shutdown claim changed')
    require(r['sources'] == {n: sha((ROOT/n).read_bytes()) for n in SOURCES}, 'Current runtime source binding differs')
    check_command(r['command'])
    require(16 <= r['max_stops'] <= 6000 and r['drain_limit'] == 64 and
            10 <= r['wall_limit_seconds'] <= 300 and 0 <= r['wall_seconds'] <= r['wall_limit_seconds'] + 16,
            'Observation bounds differ')
    require(r['stop_reason'] in ('hard-stop-bound', 'wall-limit', 'no-breakpoint-within-bounded-receive',
                                 'soft-stop-bound-drained', 'bounded-sample-target'), 'Unknown stop reason')
    require(not r['ignored'] and 0 < len(r['events']) <= r['max_stops'] + 64 and
            len(r['steps']) == len(r['events']), 'Omitted/ignored event or step')
    require(type(r['quit_receipt']['acknowledged']) is bool and
            (r['quit_receipt']['acknowledged'] or r['quit_receipt'].get('transport_note')),
            'Missing real shutdown transport receipt')
    for role, image in images.items():
        require(r['page_tables'][role] == sha(image[0x10000:0x14000]), 'Original RAM page table differs')
    ledger = Ledger()
    permanent = {p[k] for p in expected['roles'].values() for k in ('allocate', 'release')}
    for event, step in zip(r['events'], r['steps']):
        regs, role = event['registers'], event['role']
        require(set(regs) == set(REGISTERS) and set(event['system_registers']) == set(SYSTEM) and
                all(type(regs[n]) is int and 0 <= regs[n] < 2**32 for n in REGISTERS), 'Missing register evidence')
        require(stopped_thread(event['stop'], event['previous_selected_thread']) == event['thread'],
                'Wrong stopped CPU identity')
        pc = regs['pc']
        require(BASE + 8 <= pc <= BASE + len(images[role]) - 16, 'Call site outside original ROM')
        require(event['rom_window'] == dict(address=pc-8,
                    bytes=images[role][pc-BASE-8:pc-BASE+16].hex()), 'Original instructions differ')
        if event['kind'] in ('allocate', 'release'):
            ledger.enter(event)
        else:
            found = ledger.match(event)
            require(found is not None, 'Unpaired return during step replay')
            ledger.returned(found, event)
        keep = pc in permanent | ledger.return_addresses()
        require(step['address'] == pc and step['requested_thread'] == event['thread'] and step['keep'] is keep,
                'Wrong breakpoint lifetime or step target')
        if keep:
            require(stopped_thread(step['reply'], 'QC00') == step['actual_thread'] == event['thread'],
                    'Step changed CPU')
            if event['kind'] in ('allocate', 'release'):
                require(step['registers']['pc'] == pc+4, 'Entry did not execute one original ARM instruction')
        else:
            require(step['reply'] is None, 'Unexpected step after removal')
    for cmd in r['rsp_commands']:
        require(cmd in ('g', 'c', 'qC', 'qfThreadInfo', 'qSupported:xmlRegisters=arm') or re.fullmatch(
            r'(?:Hg[0-9a-f]+|p[0-9a-f]+|m[0-9a-f]+,[0-9a-f]+|[Zz]1,[0-9a-f]+,2|'
            r'vCont;s:[0-9a-f]+|qXfer:features:read:[^:]+:[0-9a-f]+,[0-9a-f]+)', cmd),
            'Mutating or unexpected debugger command')
    require(any(c.startswith('vCont;s:') for c in r['rsp_commands']), 'No isolated CPU steps')
    replay, results = analyze_events(r['events'], expected)
    require(replay.calls == r['calls'] and results == r['results'], 'Recomputed pairing/results differ')
    require(sorted(replay.pending) == r['pending_ids'] == [], 'Unreturned calls remain')
    summary = summarize(replay.calls, results)
    require(summary == r['summary'], 'Recomputed summary differs')
    require(all(s['allocations'] >= 64 for s in summary.values()), 'Insufficient allocation observations')
    coverage = {}
    for role in images:
        calls = [c for c in replay.calls if c['entry']['role'] == role]
        coverage[role] = dict(summary=summary[role], cpus=sorted({c['entry']['thread'] for c in calls}),
            processor_modes=sorted({c['entry']['registers']['cpsr'] & 31 for c in calls}),
            descriptors=sorted({descriptor['descriptor'] for descriptor in results if descriptor['role'] == role}),
            request_bytes=sorted({c['entry']['registers']['r0'] for c in calls if c['entry']['kind'] == 'allocate'}),
            return_sites=sorted({c['entry']['registers']['lr'] for c in calls}),
            release_flags=sorted({c['entry']['registers']['r1'] for c in calls if c['entry']['kind'] == 'release'}))
    return coverage


def negative_checks(valid, expected, images):
    def omitted(r): r['events'].pop()
    def pointer(r): next(e for e in r['events'] if e['kind'] == 'return')['registers']['r0'] += 8
    def saved(r): next(e for e in r['events'] if e['kind'] == 'return')['registers']['r4'] ^= 1
    def stack(r): next(e for e in r['events'] if e['kind'] == 'return')['registers']['sp'] += 8
    def cpu(r): next(e for e in r['events'] if e['kind'] == 'return')['thread'] = '04'
    def irq(r): next(e for e in r['events'] if e['kind'] == 'return')['registers']['cpsr'] ^= 0x80
    def desc(r): r['events'][0]['registers']['r1'] += 8
    def header(r): next(e for e in r['events'] if e['kind'] == 'return')['heap']['headers'][0]['words'][1] ^= 1
    def summary(r): r['summary']['master']['release_metadata'] += 1
    def table(r): r['events'][0]['system_registers']['TTBR0_S'] ^= 0x4000
    def scope(r): r['firmware_integrated'] = True
    def config(r): r['command'].append('-drive')
    def rsp(r): r['rsp_commands'].append('P0=00000000')
    def step(r): r['steps'][0]['actual_thread'] = '04'
    def pending(r): r['pending_ids'] = [0]
    changes = (omitted, pointer, saved, stack, cpu, irq, desc, header, summary, table, scope, config, rsp, step, pending)
    rejected = []
    for change in changes:
        r = copy.deepcopy(valid)
        change(r)
        try:
            check_run(r, expected, images)
        except (ValueError, KeyError, IndexError, TypeError):
            rejected.append(change.__name__)
        else:
            raise ValueError('Altered heap receipt accepted: ' + change.__name__)
    return rejected


def verify(paths):
    require(len(paths) == 2 and len({p.resolve() for p in paths}) == 2, 'Use two independent run files')
    expected, images = collect(), read_inputs()
    require(sha((ROOT/QEMU_REL).read_bytes()) == QEMU_SHA, 'Current QEMU changed')
    runs, records = [], []
    for path in paths:
        data = path.read_bytes()
        r = json.loads(data)
        coverage = check_run(r, expected, images)
        require(sha(path.with_suffix('.qemu.log').read_bytes()) == r['log_sha256'], 'QEMU log differs')
        records.append(r)
        runs.append(dict(file=path.resolve().relative_to(ROOT).as_posix(), sha256=sha(data),
                         pid=r['owned_pid'], coverage=coverage, stop_reason=r['stop_reason'],
                         quit_receipt=r['quit_receipt'], handle_close_failures=r['handle_close_failures']))
    require(records[0]['owned_pid'] != records[1]['owned_pid'], 'Independent QEMU processes required')
    return dict(schema=1, tool=TOOL, bounded_natural_allocation_samples_verified=True, runs=runs,
                negative_receipt_checks=negative_checks(records[0], expected, images),
                sources={n: sha((ROOT/n).read_bytes()) for n in SOURCES},
                verifier_sha256=sha(Path(__file__).read_bytes()),
                natural_release_metadata_observed=all(r['summary'][role]['release_metadata'] > 0
                                                     for r in records for role in images),
                complete_byte_heap_abi_verified=False, allocation_lifetime_verified=False,
                free_list_membership_verified=False, synchronization_semantics_verified=False,
                failure_inputs_verified=False, firmware_integrated=False, flash_safety_verified=False,
                camera_accessed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT/'analysis') and not output.exists(), 'Use new analysis output')
    result = verify(args.run)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps({k: result[k] for k in ('bounded_natural_allocation_samples_verified',
          'natural_release_metadata_observed', 'negative_receipt_checks', 'firmware_integrated', 'flash_safety_verified')}, indent=2))
