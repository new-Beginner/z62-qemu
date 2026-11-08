"""Replay bounded boot diagnostics, not native boot/Fenestra/flash certification."""
import argparse
import copy
import json
from pathlib import Path
import re

import observe_boot_wait as observer
from startup_contract import ROOT, BASE, PROFILES, require, read_inputs, sha
from pool_calls import REGISTERS, SYSTEM

EXPERIMENTAL = ('functional-raw-completion', 'laboratory-init-completion',
                'laboratory-mode-completion', 'laboratory-frame-completion',
                'functional-continuous-stats', 'functional-finite-stats', 'functional-raw',
                'laboratory-metadata-completion', 'frame-sync', 'frame-start',
                'input-command-completion')
DEFAULT_COMPLETIONS = ('gate-completion', 'transfer-reset-completion', 'sequencer-completion')


def flags(tree, name):
    return re.findall(r'^\s*' + re.escape(name) + r' = (true|false)\s*$', tree, re.M)


def check_run(record):
    r = record
    require(r['schema'] == 1 and r['tool'] == observer.TOOL and r['completed'] is True,
            'Incomplete/current diagnostic required')
    require(r['exit_code'] == 0 and r['owned_process_closed'] is True and
            'failure' not in r and 'cleanup_failure' not in r, 'Runtime/cleanup failed')
    require(all(r.get(n) is False for n in observer.FALSE_FIELDS), 'Scope assertion changed')
    profile = r['profile']
    windows = observer.check_windows(r['windows'])
    require(r['inputs'] == PROFILES and r['qemu_sha256'] == observer.QEMU_SHA and
            r['controller_sha256'] == observer.CONTROLLER_SHA, 'Input identities changed')
    require(sha((ROOT / observer.QEMU_REL).read_bytes()) == observer.QEMU_SHA, 'Current QEMU changed')
    require(r['sources'] == {n: sha((ROOT / n).read_bytes()) for n in observer.SOURCES}, 'Observer sources changed')
    require(r['firmware_loaded'] is True and r['reset_pc_initialized_by_qemu_loader'] is True and
            r['observation_pauses_perturb_timing'] is True, 'Boot/timing scope changed')
    require(r['controller_loaded'] is (profile != 'minimal') and
            r['controller_link_enabled'] is (profile == 'controller-link'), 'Controller scope changed')
    cmd = r['command']
    require(len(cmd) == 28, 'Command length changed')
    g = re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+)', cmd[15])
    q = re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+),server=on,wait=off', cmd[19])
    require(g is not None and q is not None, 'Loopback endpoints required')
    require(cmd == observer.build_command(Path('Q:/'), profile, int(g[1]), int(q[1])), 'Command changed')
    for name in EXPERIMENTAL:
        require(flags(r['model_tree'], name) == ['false', 'false'], 'Experimental model flag: ' + name)
    for name in DEFAULT_COMPLETIONS:
        require(flags(r['model_tree'], name) == ['true', 'true'], 'Default completion scope changed: ' + name)
    require(len(r['samples']) == len(windows), 'Omitted diagnostic sample')
    commands = r['rsp_commands']
    require(sum(c == 'c' for c in commands) == len(windows), 'Run-window commands differ')
    for c in commands:
        ok = (c in ('g', 'qfThreadInfo') or c == 'c' or
              c.startswith(('qSupported:', 'qXfer:features:read:')) or
              re.fullmatch(r'Hg[0-9a-f]+|p[0-9a-f]+|m[0-9a-f]+,[0-9a-f]+', c))
        require(bool(ok), 'Non-read-only diagnostic RSP: ' + c)
    require(r['rsp_controls'] == ['interrupt'] * len(windows), 'Interrupt coverage changed')
    expected_qmp = [dict(command='qmp_capabilities', arguments={}),
                    dict(command='human-monitor-command', arguments={'command-line': 'info qtree'})]
    for _ in windows:
        expected_qmp.extend([dict(command='query-status', arguments={}),
            dict(command='query-cpus-fast', arguments={}),
            dict(command='human-monitor-command', arguments={'command-line': 'info cpus'}),
            dict(command='human-monitor-command', arguments={'command-line': 'info registers -a'})])
    expected_qmp.append(dict(command='quit', arguments={}))
    require(r['qmp_commands'] == expected_qmp, 'QMP command stream changed')
    require(r['quit_receipt'].get('acknowledged') is True, 'This diagnostic requires actual quit receipt')
    images, previous, rows = read_inputs(), {}, []
    for sequence, (seconds, s) in enumerate(zip(windows, r['samples'])):
        require(s['requested_host_seconds'] == seconds and s['interrupted'] is True and
                s['stop'].startswith(('T02', 'S02')), 'Unexpected run-window stop')
        require(seconds * 0.95 <= s['elapsed_host_seconds'] <= seconds + 15,
                'Host timing outside recorded bounds')
        require(s['status'] == {'status': 'paused', 'running': False}, 'Not paused')
        expected_cpu_count = 4 if profile == 'minimal' else 5
        require([c['cpu-index'] for c in s['qmp_cpus']] == list(range(expected_cpu_count)), 'CPU topology changed')
        hmp = s['all_cpu_registers'].replace('\r', '')
        require(re.findall(r'^CPU#(\d+)', hmp, re.M) == [str(i) for i in range(expected_cpu_count)],
                'Incomplete HMP CPU registers')
        require(len(s['cpus']) == 4, 'Missing engine CPU sample')
        idle_count = 0
        role_arrays = {}
        for index, c in enumerate(s['cpus']):
            role = 'master' if index < 2 else 'slave'
            require(c['thread'] == f'{index + 1:02x}' and c['role'] == role, 'CPU/role changed')
            regs, image = c['registers'], images[role]
            require(set(regs) == set(REGISTERS) and all(type(v) is int and 0 <= v < 2**32 for v in regs.values()),
                    'Bad general register packet')
            require(c['image_head'] == image[:0x6C].hex(), 'Wrong engine image head')
            system = c['system']
            require(set(system) == set(SYSTEM) and all(system[n] == 0 for n in ('DFSR_S', 'IFSR_S', 'DFSR', 'IFSR')),
                    'Fault/unknown system registers in accepted sample')
            require(system['SCTLR_EL1_S'] == 0xC5107D and system['DACR_S'] == 0x55555555 and
                    system['TTBR0_S'] == {'master': 0xC2B54000, 'slave': 0xC18D4000}[role], 'MMU state changed')
            code = c['code']
            require(code == observer.code_window(image, regs['pc'], bool(regs['cpsr'] & 32),
                    bytes.fromhex(code['bytes'])), 'Saved ROM decode differs')
            points = observer.scheduler_points(image, role)
            require(c['scheduler']['points'] == points, 'Scheduler literal address changed')
            arrays = c['scheduler']['current'], c['scheduler']['ready']
            require(all(len(a) == 2 and all(type(v) is int and 0 <= v < 2**32 for v in a) for a in arrays),
                    'Bad bounded scheduler arrays')
            if role in role_arrays:
                require(arrays == role_arrays[role], 'Paused CPU views of same scheduler differ')
            role_arrays[role] = arrays
            idle = points['loop'] + 16 <= regs['pc'] <= points['loop'] + 0x34
            if idle and c['scheduler']['ready'][index % 2] == 0:
                idle_count += 1
            stack = c['stack']
            require(stack['address'] == regs['sp'] and len(stack['words']) == 32 and
                    all(type(w) is int and 0 <= w < 2**32 for w in stack['words']), 'Stack sample changed')
            ticks = c['model_clock_ticks']
            require(type(ticks) is int and ticks > previous.get(index, -1), 'Model clock did not advance')
            previous[index] = ticks
            block = re.search(r'^CPU#' + str(index) + r'\n(.*?)(?=^CPU#|\Z)', hmp, re.M | re.S)
            require(block is not None and f'R15={regs["pc"]:08x}' in block[1], 'HMP/RSP PC mismatch')
        rows.append(dict(sequence=sequence, idle_engine_cpus=idle_count,
                         engine_seconds=[c['model_clock_ticks'] / 48000000 for c in s['cpus']],
                         scheduler_arrays_zero=all(not any(a) for arrays in role_arrays.values() for a in arrays)))
    return dict(profile=profile, pid=r['owned_pid'], samples=rows,
                default_completion_logic_present=True, exact_model_source_recovered=False,
                firmware_integrated=False, flash_safety_verified=False,
                waiting_task_objects_identified=False, allocator_lifetime_verified=False)


def mutations(record):
    variants = {}
    def changed(name):
        variants[name] = copy.deepcopy(record)
        return variants[name]
    changed('sample')['samples'].pop()
    changed('window')['windows'][0] = 121
    changed('pc')['samples'][0]['cpus'][0]['registers']['pc'] += 4
    changed('scheduler')['samples'][0]['cpus'][0]['scheduler']['points']['ready'] += 4
    changed('array')['samples'][-1]['cpus'][0]['scheduler']['ready'][0] ^= 1
    changed('fault')['samples'][0]['cpus'][0]['system']['DFSR_S'] = 1
    changed('scope')['firmware_integrated'] = True
    changed('command')['command'].extend(['-global', 'nikon-z72-boot-config.frame-sync=on'])
    changed('rsp')['rsp_commands'].append('M10020000,1:00')
    changed('qmp')['qmp_commands'].append(dict(command='system_reset', arguments={}))
    changed('clock')['samples'][-1]['cpus'][0]['model_clock_ticks'] = 0
    changed('model')['model_tree'] = record['model_tree'].replace('frame-sync = false', 'frame-sync = true')
    return variants


def verify(paths, output):
    require(not output.exists() and output.resolve().is_relative_to(ROOT / 'analysis'), 'Use new analysis output')
    checked, records = [], []
    for path in paths:
        r = json.loads(path.read_text(encoding='utf-8'))
        row = check_run(r)
        require(sha(path.with_suffix('.qemu.log').read_bytes()) == r['qemu_log_sha256'], 'QEMU log changed')
        row.update(path=path.relative_to(ROOT).as_posix(), sha256=sha(path.read_bytes()))
        checked.append(row)
        records.append(r)
    require({r['profile'] for r in checked} == {'minimal', 'controller', 'controller-link'}, 'Missing profile')
    require(len({r['pid'] for r in checked}) == len(checked), 'Processes were not independent')
    for profile in ('minimal', 'controller-link'):
        require(any(r['profile'] == profile and r['samples'][-1]['engine_seconds'][0] >= 9 for r in checked),
                'Missing extended guest-time window: ' + profile)
    rejected = []
    for name, bad in mutations(records[0]).items():
        try:
            check_run(bad)
        except (ValueError, KeyError, TypeError, IndexError):
            rejected.append(name)
        else:
            raise ValueError('Mutation accepted: ' + name)
    result = dict(schema=1, tool='fenestra-z62-boot-wait-verifier/0.1.0',
                  verifier_sha256=sha(Path(__file__).read_bytes()), runs=checked,
                  record_mutations_rejected=rejected, bounded_diagnostics_replayed=True,
                  **{n: False for n in observer.FALSE_FIELDS})
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    verify([p.resolve() for p in args.run], args.output.resolve())
