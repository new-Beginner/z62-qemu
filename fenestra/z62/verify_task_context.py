"""Replay pinned r7 context traces. Does not certify task ABI, boot or flashing."""
import argparse
import copy
import json
import math
from pathlib import Path
import re

import observe_task_context as observer
import observe_boot_wait as boot
from verify_boot_wait import EXPERIMENTAL, DEFAULT_COMPLETIONS, flags
from startup_contract import ROOT, BASE, require, read_inputs, sha
from observe_startup import stopped_thread
from pool_calls import REGISTERS, SYSTEM
from task_context import TOOL, collect, bounded_ram, words, check_event, summarize

TOOL_VERIFY = 'fenestra-z62-task-context-verifier/0.1.0'


def check_regs(regs):
    require(set(regs) == set(REGISTERS) and all(type(v) is int and 0 <= v < 2**32 for v in regs.values()),
            'Invalid general register packet')


def check_system(system, role):
    require(set(system) == set(SYSTEM) and all(type(v) is int and 0 <= v < 2**32 for v in system.values()),
            'Invalid system-register packet')
    require(all(system[n] == 0 for n in ('DFSR_S', 'IFSR_S', 'DFSR', 'IFSR')), 'Recorded engine fault')
    require(system['SCTLR_EL1_S'] == 0xC5107D and system['DACR_S'] == 0x55555555 and
            system['TTBR0_S'] == {'master': 0xC2B54000, 'slave': 0xC18D4000}[role] and
            system['TTBCR_S'] == 0 and system['VBAR_EL1_S'] == {'master': 0x10100000, 'slave': 0x10034100}[role],
            'Original active MMU/vector state changed')


def check_final_cpus(cpus, images, contract, final_ticks):
    require(len(cpus) == 4, 'Missing final engine CPU')
    arrays = {}
    idle = 0
    for index, c in enumerate(cpus):
        role = 'master' if index < 2 else 'slave'
        require(c['thread'] == f'{index + 1:02x}' and c['role'] == role, 'Final CPU/role mismatch')
        regs, image = c['registers'], images[role]
        check_regs(regs)
        check_system(c['system'], role)
        require(c['image_head'] == image[:0x6C].hex(), 'Final engine identity mismatch')
        code = c['code']
        require(code == boot.code_window(image, regs['pc'], bool(regs['cpsr'] & 32), bytes.fromhex(code['bytes'])),
                'Final ROM window changed')
        points = boot.scheduler_points(image, role)
        require(c['scheduler']['points'] == points, 'Final scheduler literals changed')
        values = c['scheduler']['current'], c['scheduler']['ready']
        require(all(len(a) == 2 and all(type(v) is int and 0 <= v < 2**32 for v in a) for a in values),
                'Bad bounded final scheduler slots')
        require(role not in arrays or arrays[role] == values, 'Paused scheduler views disagree')
        arrays[role] = values
        require(type(c['model_clock_ticks']) is int and 0 <= c['model_clock_ticks'] <= final_ticks and
                (role != 'master' or c['model_clock_ticks'] == final_ticks) and
                (index % 2 == 0 or c['model_clock_ticks'] == cpus[index - 1]['model_clock_ticks']),
                'Final paused role clocks disagree')
        stack = c['stack']
        require(stack['address'] == regs['sp'] and len(stack['words']) == 32 and
                all(type(w) is int and 0 <= w < 2**32 for w in stack['words']), 'Bad final bounded stack')
        if points['loop'] + 16 <= regs['pc'] <= points['loop'] + 0x34 and not any(a[index % 2] for a in values):
            idle += 1
    return idle


def check_commands(r, contract):
    cmd = r['command']
    require(len(cmd) == 28, 'Command length changed')
    g = re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+)', cmd[15])
    q = re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]+),server=on,wait=off', cmd[19])
    require(g is not None and q is not None and 1024 <= int(g[1]) <= 65535 and 1024 <= int(q[1]) <= 65535,
            'Bounded loopback endpoints required')
    require(cmd == boot.build_command(Path('Q:/'), 'minimal', int(g[1]), int(q[1])), 'Minimal command changed')
    commands = r['rsp_commands']
    for c in commands:
        ok = (c in ('g', 'c', 'qC', 'qfThreadInfo') or
              c.startswith(('qSupported:', 'qXfer:features:read:')) or
              re.fullmatch(r'Hg[0-4]|p[0-9a-f]+|m[0-9a-f]+,[0-9a-f]+|[Zz]1,[0-9a-f]+,2|vCont;s:0[1-4]', c))
        require(bool(ok), 'Forbidden RSP operation: ' + c)
    points = sorted(p['checkpoint'] for p in contract['roles'].values())
    expected = [f'Z1,{pc:x},2' for pc in points]
    expected_reads = []
    for e in r['events']:
        pc, tid = e['registers']['pc'], e['thread']
        expected.extend(['c', f'z1,{pc:x},2', 'vCont;s:' + tid, f'Z1,{pc:x},2'])
        p = contract['roles'][e['role']]
        expected_reads.extend([f'm{BASE:x},6c', f'm{e["registers"]["r8"]:x},100',
            f'm{e["frame_address"]:x},60', f'm{p["current"]:x},8', 'm4266008,8', f'm{pc - 16:x},20'])
    expected.extend(['c'] * sum(p['phase'] == 'trace' for p in r['pauses']))
    expected.extend(f'z1,{pc:x},2' for pc in points)
    expected.extend(['c'] * sum(p['phase'] == 'untraced' for p in r['pauses']))
    actual = [c for c in commands if c == 'c' or c.startswith(('Z', 'z', 'vCont;'))]
    require(actual == expected, 'Breakpoint lifecycle/isolated step sequence changed')
    reads = [c for c in commands if c.startswith('m')]
    require(reads[:len(expected_reads)] == expected_reads, 'Context read windows/order changed')
    tail = []
    for c in r['final_cpus']:
        p = contract['roles'][c['role']]
        tail.extend([f'm{BASE:x},6c', f'm{p["current"]:x},8', f'm{p["ready"]:x},8',
                     'm4266008,8', f'm{c["registers"]["pc"] - 16:x},40', f'm{c["registers"]["sp"]:x},80'])
    for role in ('master', 'slave'):
        for s in r['final_saved'][role]:
            tail.append(f'm{s["pointer"]:x},100')
            if 'frame' in s:
                tail.append(f'm{s["frame_address"]:x},60')
    require(reads[-len(tail):] == tail, 'Final read windows/order changed')
    middle = reads[len(expected_reads):-len(tail)]
    require(middle and all(c == 'm4266008,8' for c in middle), 'Unexpected intermediate memory read')
    require(commands.count('g') == 2 * len(r['events']) + 4 and commands.count('qC') == 2 * len(r['events']),
            'Register/stop CPU coverage differs')
    require(r['rsp_controls'] == ['interrupt'] * len(r['pauses']), 'Interrupt coverage differs')
    require(r['qmp_commands'] == [dict(command='qmp_capabilities', arguments={}),
        dict(command='human-monitor-command', arguments={'command-line': 'info qtree'}),
        dict(command='query-status', arguments={}), dict(command='quit', arguments={})], 'QMP sequence differs')


def check_run(r):
    require(r['schema'] == 1 and r['tool'] == TOOL and r['completed'] is True, 'Incomplete original r7 trace')
    require(r['exit_code'] == 0 and r['owned_process_closed'] is True and 'failure' not in r and
            'quit_failure' not in r and r['close_notes'] == [], 'Trace/process/close failure')
    require(r['quit_receipt'] == {'acknowledged': True}, 'Actual QMP quit acknowledgement required')
    require(all(r.get(n) is False for n in boot.FALSE_FIELDS), 'Scope changed')
    for n in ('firmware_loaded', 'reset_pc_initialized_by_qemu_loader', 'breakpoint_timing_perturbed'):
        require(r[n] is True, 'Boot/timing assertion changed')
    require(r['controller_loaded'] is False and r['controller_link_enabled'] is False, 'Minimal scope changed')
    require(r['owned_shutdown'] == 'QMP quit; NOT camera normal shutdown', 'Shutdown claim changed')
    require(type(r['owned_pid']) is int and r['owned_pid'] > 0, 'Missing owned PID')
    require(r['qemu_sha256'] == observer.QEMU_SHA and sha((ROOT / observer.QEMU_REL).read_bytes()) == observer.QEMU_SHA,
            'Pinned QEMU changed')
    require(r['sources'] == {n: sha((ROOT / n).read_bytes()) for n in observer.SOURCES}, 'Observer sources changed')
    contract, images = collect(), read_inputs()
    require(r['contract'] == contract, 'Original static context contract changed')
    for n in EXPERIMENTAL:
        require(flags(r['model_tree'], n) == ['false', 'false'], 'Experimental model flag: ' + n)
    for n in DEFAULT_COMPLETIONS:
        require(flags(r['model_tree'], n) == ['true', 'true'], 'Default completion scope changed: ' + n)
    require(type(r['max_stops']) is int and 16 <= r['max_stops'] <= 1000 and
            math.isfinite(r['guest_target_seconds']) and 1 <= r['guest_target_seconds'] <= 10 and
            30 <= r['wall_limit_seconds'] <= 180 and math.isfinite(r['wall_seconds']) and
            0 < r['wall_seconds'] <= r['wall_limit_seconds'] + 30, 'Invalid bounded observation limits')
    events, steps = r['events'], r['steps']
    require(16 <= len(events) <= r['max_stops'] and len(steps) == len(events), 'Event/step omitted')
    previous = -1
    for index, (e, s) in enumerate(zip(events, steps)):
        require(e['sequence'] == index, 'Event sequence omitted/reordered')
        p, regs = contract['roles'][e['role']], e['registers']
        check_regs(regs)
        check_system(e['system_registers'], e['role'])
        require(e['stop'].startswith('T05') and stopped_thread(e['stop'], e['previous_selected_thread']) == e['thread'],
                'Stop packet CPU mismatch')
        require(e['image_head'] == images[e['role']][:0x6C].hex(), 'Original role head changed')
        rom = e['rom_window']
        address = regs['pc'] - 16
        require(rom == dict(address=address, bytes=images[e['role']][address - BASE:address - BASE + 32].hex()),
                'Original context ROM changed')
        require(e['analysis'] == check_event(e, p), 'Context analysis changed')
        require(type(e['model_ticks']) is int and previous <= e['model_ticks'], 'Trace clock regressed')
        previous = e['model_ticks']
        require(s['address'] == regs['pc'] and s['thread'] == e['thread'] and s['reply'].startswith('T05') and
                stopped_thread(s['reply'], 'QC' + e['thread']) == e['thread'], 'Isolated step CPU changed')
        check_regs(s['registers'])
        expected = dict(regs, pc=regs['pc'] + 4, sp=p['system_stack'])
        require(s['registers'] == expected, 'Original single LDR SP changed other registers')
    require(r['summary'] == summarize(events, contract), 'Context summary changed')
    require(all(any(e['role'] == role for e in events) for role in ('master', 'slave')), 'Missing engine role')
    reason = r['trace_stop_reason']
    require(reason in ('context-sample-bound', 'wall-bound', 'quiet-window-switch-to-untraced-guest-deadline'),
            'Unknown trace stop reason')
    if reason == 'context-sample-bound':
        require(len(events) == r['max_stops'], 'Sample bound not reached')
    require(type(r['trace_end_ticks']) is int and r['trace_end_ticks'] >= previous, 'Trace end clock regressed')
    previous = r['trace_end_ticks']
    trace_pauses = 0
    for pause in r['pauses']:
        require(pause['phase'] in ('trace', 'untraced') and pause['stop'].startswith('T02'), 'Bad pause')
        if pause['phase'] == 'trace':
            trace_pauses += 1
            require(pause['ticks'] == r['trace_end_ticks'], 'Trace pause end differs')
        else:
            require(type(pause['ticks']) is int and pause['ticks'] > previous, 'Untraced guest clock stalled')
            previous = pause['ticks']
    require(trace_pauses == int(reason == 'quiet-window-switch-to-untraced-guest-deadline'), 'Trace pause mismatch')
    require(type(r['final_ticks']) is int and r['final_ticks'] >= previous and
            r['guest_target_reached'] is (r['final_ticks'] >= r['guest_target_seconds'] * 48000000),
            'Guest-time coverage assertion changed')
    require(r['guest_target_reached'] is True, 'Requested guest window not reached; keep as diagnostic only')
    require(r['final_status'] == {'status': 'paused', 'running': False}, 'Final CPUs not paused')
    idle = check_final_cpus(r['final_cpus'], images, contract, r['final_ticks'])
    require(set(r['final_saved']) == {'master', 'slave'}, 'Final snapshot roles differ')
    for role, p in contract['roles'].items():
        addresses = sorted({e['registers']['r8'] for e in events if e['role'] == role})
        require([s['pointer'] for s in r['final_saved'][role]] == addresses, 'Final snapshot address omitted/reordered')
        for s in r['final_saved'][role]:
            require(bounded_ram(p, s['pointer'], 256), 'Final control block out of bounds')
            block = words(bytes.fromhex(s['tcb']), 256)
            require(s['frame_address'] == block[0xBC // 4], 'Final saved-SP relation changed')
            if bounded_ram(p, s['frame_address'], 96):
                words(bytes.fromhex(s['frame']), 96)
                require('unresolved' not in s, 'Bounded frame unexpectedly unresolved')
            else:
                require('frame' not in s and s['unresolved'] ==
                    'Saved pointer is not a bounded original-heap frame; no lifetime inference', 'Invalid unresolved frame')
    check_commands(r, contract)
    return dict(pid=r['owned_pid'], events=len(events), isolated_steps=len(steps), summary=r['summary'],
        trace_model_seconds=r['trace_end_ticks'] / 48000000, final_model_seconds=r['final_ticks'] / 48000000,
        guest_target_reached=True, final_idle_engine_cpus=idle,
        **{n: False for n in boot.FALSE_FIELDS}, complete_task_abi_verified=False,
        task_names_mapped=False, waiting_root_cause_identified=False)


def mutations(record):
    variants = {}
    def changed(name):
        variants[name] = copy.deepcopy(record)
        return variants[name]
    changed('omitted')['events'].pop()
    changed('sequence')['events'][0]['sequence'] = 9
    changed('saved-sp')['events'][0]['frame_address'] += 4
    changed('slot')['events'][0]['current'] = [0, 0]
    changed('cpu')['events'][0]['thread'] = '05'
    changed('rom')['events'][0]['rom_window']['bytes'] = '00' * 32
    changed('frame')['events'][0]['frame'] = record['events'][0]['frame'][:-2]
    changed('analysis')['events'][0]['analysis']['saved_call_lr'] ^= 4
    changed('step')['steps'][0]['registers']['r0'] ^= 1
    changed('step-cpu')['steps'][0]['thread'] = '01' if record['steps'][0]['thread'] != '01' else '04'
    changed('fault')['events'][0]['system_registers']['DFSR_S'] = 1
    changed('summary')['summary']['master']['events'] += 1
    changed('clock')['final_ticks'] = 0
    changed('scope')['firmware_integrated'] = True
    changed('command')['command'].extend(['-global', 'nikon-z72-boot-config.frame-sync=on'])
    changed('rsp-write')['rsp_commands'].append('M10020000,1:00')
    changed('traditional-step')['rsp_commands'].append('s')
    bad = changed('breakpoint-lifecycle')
    bad['rsp_commands'].remove(next(c for c in bad['rsp_commands'] if c.startswith('z1,')))
    changed('qmp')['qmp_commands'].append(dict(command='system_reset', arguments={}))
    changed('model')['model_tree'] = record['model_tree'].replace('frame-sync = false', 'frame-sync = true')
    changed('final-saved')['final_saved']['master'].pop()
    changed('source')['sources']['fenestra/z62/task_context.py'] = '0' * 64
    return variants


def verify(paths, output):
    require(not output.exists() and output.resolve().is_relative_to(ROOT / 'analysis'), 'Use new analysis output')
    runs, records = [], []
    for path in paths:
        r = json.loads(path.read_text(encoding='utf-8'))
        result = check_run(r)
        require(sha(path.with_suffix('.qemu.log').read_bytes()) == r['log_sha256'], 'QEMU log changed')
        result.update(path=path.relative_to(ROOT).as_posix(), sha256=sha(path.read_bytes()))
        records.append(r)
        runs.append(result)
    require(len(runs) >= 2 and len({r['pid'] for r in runs}) == len(runs), 'Two independent processes required')
    rejected = []
    for name, bad in mutations(records[0]).items():
        try:
            check_run(bad)
        except (ValueError, KeyError, TypeError, IndexError):
            rejected.append(name)
        else:
            raise ValueError('Mutation accepted: ' + name)
    result = dict(schema=1, tool=TOOL_VERIFY, verifier_sha256=sha(Path(__file__).read_bytes()), runs=runs,
        record_mutations_rejected=rejected, bounded_context_traces_replayed=True,
        complete_task_abi_verified=False, task_names_mapped=False, waiting_root_cause_identified=False,
        **{n: False for n in boot.FALSE_FIELDS})
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
