"""Revalidate bounded natural pool-call evidence; not an ABI or flash certificate."""
import argparse
import copy
import json
from pathlib import Path
import re
import subprocess

from pool_calls import (collect, analyze_events, summarize, FALSE_FIELDS, SYSTEM, REGISTERS, Ledger)
from startup_contract import ROOT, BASE, read_inputs, sha, require
from observe_startup import QEMU_REL, QEMU_SHA, stopped_thread

RUNTIME_SOURCES = ('fenestra/z62/observe_pool.py', 'fenestra/z62/pool_calls.py',
                   'fenestra/z62/observe_startup.py', 'third_party/z62-qemu/analyze/qemu_display.py',
                   'tools/probe_reference_devices.py', 'tools/probe_z62_functional_raw.py')


def check_command(command):
    require(len(command) == 28, 'Unexpected QEMU argument count')
    gdb, qmp = command[15], command[19]
    require(re.fullmatch(r'tcp:127\.0\.0\.1:[0-9]+,server=on,wait=off', qmp) is not None, 'Nonlocal QMP')
    require(re.fullmatch(r'tcp:127\.0\.0\.1:[0-9]+', gdb) is not None, 'Nonlocal GDB')
    require(qmp.split(':')[2].split(',')[0] != gdb.split(':')[2], 'Shared port')
    root = Path('Q:/')
    expected = [str(root / QEMU_REL), '-M',
                'nikon-z62-dual-lab,'
                f'master-boot-image={root}/artifacts/z62-reference-1.70/master.bin,'
                f'slave-boot-image={root}/artifacts/z62-reference-1.70/slave.bin',
                '-smp', '4,maxcpus=5', '-S', '-display', 'none', '-serial', 'none',
                '-monitor', 'none', '-nic', 'none', '-gdb', gdb,
                '-icount', 'shift=0,sleep=off', '-qmp', qmp]
    for cpu in range(4):
        expected += ['-device', f'loader,addr={BASE:#x},cpu-num={cpu}']
    require(command == expected, 'QEMU configuration changed')


def coverage(calls, results):
    by_id = {r['id']: r for r in results}
    report = {}
    for role in ('master', 'slave'):
        allocations = [c for c in calls if c['entry']['role'] == role and c['entry']['kind'] == 'allocate']
        releases = [c for c in calls if c['entry']['role'] == role and c['entry']['kind'] == 'release']
        # A bounded allocation stream, NOT global ownership/lifecycle certification.
        extents = sorted((by_id[c['id']]['pointer'], by_id[c['id']]['blocks'] * 0x800)
                         for c in allocations if by_id[c['id']].get('successful'))
        nonoverlap = all(a + n <= b for (a, n), (b, _) in zip(extents, extents[1:]))
        if not releases:
            require(nonoverlap, 'Observed allocations overlap without observed release')
        report[role] = dict(
            allocate_calls=len(allocations), release_calls=len(releases),
            allocate_failures=sum(not by_id[c['id']].get('successful', False) for c in allocations),
            request_blocks=sorted({c['entry']['registers']['r0'] for c in allocations}),
            flags=sorted({c['entry']['registers']['r1'] for c in allocations}),
            cpus=sorted({c['entry']['thread'] for c in allocations + releases}),
            processor_modes=sorted({c['entry']['registers']['cpsr'] & 31 for c in allocations + releases}),
            return_addresses=sorted({c['entry']['registers']['lr'] for c in allocations + releases}),
            overlaps=sum(bool(c['overlaps']) for c in allocations + releases),
            total_observed_requested_bytes=sum(n for _, n in extents),
            lowest_allocation=min((a for a, _ in extents), default=None),
            highest_end=max((a + n for a, n in extents), default=None),
            bounded_extents_nonoverlapping_without_releases=nonoverlap if not releases else None)
    return report


def check_run(r, expected, images):
    require(r['schema'] == 1 and r['completed'] is True and r['owned_process_closed'] is True and
            r['exit_code'] == 0 and 'failure' not in r, 'Incomplete observation')
    require(r['contract'] == expected, 'Current contract differs')
    require(r['qemu_sha256'] == QEMU_SHA, 'QEMU identity differs')
    require(all(r[n] is False for n in FALSE_FIELDS), 'Observation scope changed')
    require(r['firmware_loaded'] is True and r['reset_pc_initialized_by_qemu_loader'] is True and
            r['breakpoint_timing_perturbed'] is True, 'Missing stock execution setup')
    require(r['owned_shutdown'] == 'QMP quit; NOT camera normal shutdown', 'Shutdown scope changed')
    check_command(r['command'])
    require(set(r['sources']) == set(RUNTIME_SOURCES), 'Missing runtime source binding')
    require(8 <= r['max_stops'] <= 1000 and 10 <= r['wall_limit_seconds'] <= 300, 'Invalid bounds')
    require(0 <= r['wall_seconds'] <= r['wall_limit_seconds'] + 16, 'Unbounded observation')
    require(r['stop_reason'] in ('max-stops', 'wall-limit', 'no-breakpoint-within-bounded-receive',
                                 'bounded-sample-target'), 'Unknown observation limit')
    require(not r['ignored'], 'Unmatched breakpoint hits require separate investigation')
    require(0 < len(r['events']) <= r['max_stops'], 'Invalid event count')
    require(len(r['steps']) == len(r['events']), 'Missing breakpoint-step record')
    require(isinstance(r['quit_receipt']['acknowledged'], bool), 'Missing quit receipt')
    if not r['quit_receipt']['acknowledged']:
        require(bool(r['quit_receipt'].get('transport_note')), 'Unreported quit transport problem')
    for role, image in images.items():
        require(r['page_tables'][role] == sha(image[0x10000:0x14000]), 'Original RAM table digest changed')
    step_ledger = Ledger()
    permanent = {p['observed_api'][kind] for p in expected['roles'].values() for kind in ('allocate', 'release')}
    for event, step in zip(r['events'], r['steps']):
        role, regs = event['role'], event['registers']
        require(set(event['system_registers']) == set(SYSTEM), 'System register evidence incomplete')
        require(all(isinstance(regs[n], int) and 0 <= regs[n] < 2**32 for n in REGISTERS), 'Invalid register')
        require(stopped_thread(event['stop'], event['previous_selected_thread']) == event['thread'], 'Wrong stopped CPU')
        pc = regs['pc']
        require(BASE + 8 <= pc <= BASE + len(images[role]) - 16, 'Call site outside ROM')
        require(event['rom_window'] == dict(address=pc - 8,
                    bytes=images[role][pc - BASE - 8:pc - BASE + 16].hex()), 'Original instruction bytes differ')
        if event['kind'] in ('allocate', 'release'):
            step_ledger.enter(event)
        else:
            call_id = step_ledger.match(event)
            require(call_id is not None, 'Unmatched return in step replay')
            step_ledger.returned(call_id, event)
        keep = pc in (permanent | step_ledger.return_addresses())
        require(step['address'] == pc and step['requested_thread'] == event['thread'] and
                step['keep'] is keep, 'Wrong step target/lifetime')
        if keep:
            require(stopped_thread(step['reply'], 'QC00') == event['thread'] == step['actual_thread'], 'Wrong single-step CPU')
            if event['kind'] in ('allocate', 'release'):
                require(step['registers']['pc'] == pc + 4, 'Entry did not advance one original ARM instruction')
        else:
            require(step['reply'] is None, 'Unexpected step after breakpoint removal')
    # Independently constrain the recorded RSP stream to reads/execution control.
    simple = {'g', 'c', 'qC', 'qfThreadInfo', 'qSupported:xmlRegisters=arm'}
    for cmd in r['rsp_commands']:
        require(cmd in simple or re.fullmatch(
            r'(?:Hg[0-9a-f]+|p[0-9a-f]+|m[0-9a-f]+,[0-9a-f]+|[Zz]1,[0-9a-f]+,2|'
            r'vCont;s:[0-9a-f]+|qXfer:features:read:[^:]+:[0-9a-f]+,[0-9a-f]+)', cmd),
            'Unexpected or mutating debugger command')
    require(any(cmd.startswith('vCont;s:') for cmd in r['rsp_commands']), 'No isolated CPU stepping')
    ledger, results = analyze_events(r['events'], expected)
    require(ledger.calls == r['calls'] and results == r['results'], 'Replayed calls/results differ')
    require(sorted(ledger.pending) == r['pending_ids'] == [], 'Unreturned calls remain')
    require(summarize(results) == r['summary'], 'Summary differs')
    require(all(r['summary'][role]['allocate']['isolated_success'] >= 8 for role in images), 'Insufficient allocation sample')
    return coverage(ledger.calls, results)


def negative_checks(valid, expected, images):
    def omitted(r): r['events'].pop()
    def ret_pc(r): next(e for e in r['events'] if e['kind'] == 'return')['registers']['pc'] += 4
    def thread(r): next(e for e in r['events'] if e['kind'] == 'return')['thread'] = '02'
    def stack(r): next(e for e in r['events'] if e['kind'] == 'return')['registers']['sp'] += 4
    def saved(r): next(e for e in r['events'] if e['kind'] == 'return')['registers']['r4'] ^= 1
    def count(r): next(e for e in r['events'] if e['kind'] == 'return')['pool']['state'][1] += 1
    def header(r): next(e for e in r['events'] if e['kind'] == 'return')['pool']['headers'][1]['words'][0] ^= 2
    def table(r): r['events'][0]['system_registers']['TTBR0_S'] ^= 0x4000
    def fault(r): r['events'][0]['system_registers']['IFSR_S'] = 1
    def scope(r): r['allocator_call_abi_verified'] = True
    def pending(r): r['pending_ids'] = [0]
    def ledger(r): r['calls'].pop()
    def summary(r): r['summary']['master']['allocate']['paired'] -= 1
    def instruction(r): r['events'][0]['rom_window']['bytes'] = '00' * 24
    def rsp_write(r): r['rsp_commands'].append('P0=00000000')
    def config(r): r['command'].append('-drive')
    def step(r): r['steps'][0]['actual_thread'] = '03'
    rejected = []
    for mutate in (omitted, ret_pc, thread, stack, saved, count, header, table, fault, scope,
                   pending, ledger, summary, instruction, rsp_write, config, step):
        r = copy.deepcopy(valid)
        mutate(r)
        try:
            check_run(r, expected, images)
        except ValueError:
            rejected.append(mutate.__name__)
        else:
            raise ValueError('Altered receipt accepted: ' + mutate.__name__)
    return rejected


def verify(paths):
    expected, images = collect(), read_inputs()
    require(len(paths) >= 2, 'Two independent processes required')
    receipts, negatives = [], []
    for path in paths:
        path = path.resolve()
        require(path.is_relative_to(ROOT / 'analysis'), 'Run escaped analysis')
        r = json.loads(path.read_text(encoding='utf-8'))
        covered = check_run(r, expected, images)
        for name, digest in r['sources'].items():
            require(sha((ROOT / name).read_bytes()) == digest, 'Runtime source changed: ' + name)
        require(sha((ROOT / QEMU_REL).read_bytes()) == QEMU_SHA, 'QEMU changed')
        require(sha(path.with_suffix('.qemu.log').read_bytes()) == r['log_sha256'], 'QEMU log changed')
        if not negatives:
            negatives = negative_checks(r, expected, images)
        receipts.append(dict(file=path.relative_to(ROOT).as_posix(), sha256=sha(path.read_bytes()),
                             pid=r['owned_pid'], coverage=covered, summary=r['summary'],
                             quit_receipt=r['quit_receipt'], handle_close_failures=r['handle_close_failures']))
    require(len({r['pid'] for r in receipts}) == len(receipts), 'Process reused')
    baseline = json.loads((ROOT / 'analysis/fenestra-feasibility/source-check.json').read_text(encoding='utf-8'))
    for row in baseline['original_inputs']:
        data = (ROOT / row['file']).read_bytes()
        require(len(data) == row['size'] and sha(data) == row['sha256'], 'Original input changed')
    repo = ROOT / 'third_party/z62-qemu'
    require(subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip() ==
            '4f4389944fc339d107f22f5f7ca3f90cc34b78de', 'Z62 source commit changed')
    require(not subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain'], text=True).strip(), 'Z62 source dirty')
    return dict(schema=1, bounded_natural_allocation_samples_verified=True, runs=receipts,
                negative_receipt_checks=negatives, original_inputs_unchanged=4, qemu_unchanged=True,
                verifier_sha256=sha(Path(__file__).read_bytes()),
                allocator_call_abi_verified=False, allocation_lifetime_verified=False,
                natural_release_verified=False, failure_path_verified=False,
                all_flags_verified=False, concurrency_safety_verified=False,
                plugin_execution_in_heap_verified=False, firmware_integrated=False,
                flash_safety_verified=False, camera_accessed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT / 'analysis') and not output.exists(), 'Use new analysis output')
    result = verify(args.run)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps(result, indent=2))
