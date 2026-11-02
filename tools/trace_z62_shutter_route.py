"""Trace original input dispatch around actual PG1/PG13 contacts on frozen r9.

Uses a snapshot of an existing virtual regular card. Breakpoints perturb timing;
this probe identifies consumers and is separate from native exposure acceptance.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import trace_z62_capture_setup as capture
import run_z62_raw_stream as raw
import run_z62_finite_stats as finite
import run_z62_preview as host
import z62_shutter_input_v2 as shutter
import z62_qmp_transport as monitor
from z62_preview_status import preview_status
from z62_virtual_sd import image_path, digest


def run(output, card, *, extra_points=None, extra_state=None, only_points=None, max_stops=1000,
        extra_hit_hook=None, wait_for_ready=False, duration=30, breakpoint_window=None,
        extra_contact_hook=None, full_press_hold=.5, write_watchpoints=None,
        extra_observation_hook=None, read_watchpoints=None, automatic_shutter=True, wall_limit=None,
        observation_timeout_recovery=False):
    if output.exists():
        raise FileExistsError('Existing evidence is protected')
    if isinstance(full_press_hold, bool) or not .05 <= full_press_hold <= 15:
        raise ValueError('Full contact hold must be .05..15 virtual seconds')
    if type(automatic_shutter) is not bool or (wait_for_ready and not automatic_shutter):
        raise ValueError('Ready-triggered shutter requires automatic_shutter=True')
    if wall_limit is not None and (type(wall_limit) not in (int,float) or not 60 <= wall_limit <= 3600):
        raise ValueError('Explicit observation wall limit must be 60..3600 seconds')
    card = image_path(card)
    before = digest(card)
    host.verify_build(host.DEFAULT_QEMU.resolve())
    old = (capture.POINTS, capture.STATE, raw.configure_command,
           capture.trace.observe_capture, capture.host.host.apply_console)
    def configure(command, *a, **kw):
        return host.configure_command(finite.configure_command(old[2](command, *a, **kw)), True)
    def observe(machine):
        return {**old[3](machine), **preview_status(machine)}
    def apply(source, persistent=False):
        old[4](source, persistent)
        shutter.apply_console(source)
        monitor.apply_console(source)
    capture.POINTS = {0x10239734:'raw-buffer-descriptor', 0x10436600:'mcu-input-decode',
        0x1038DC0C:'input-cache', 0x1038DB5E:'system-input-callback',
        0x1038DB8E:'extended-input-callback'}
    capture.STATE = {**old[1], 0xC1811BB0:24, 0xC1F7A720:13, 0xC25D6FC0:13}
    capture.POINTS.update(extra_points or {})
    if only_points is not None:
        capture.POINTS = dict(only_points)
    capture.STATE.update(extra_state or {})
    raw.configure_command, capture.trace.observe_capture = configure, observe
    capture.host.host.apply_console = apply
    phase = 0
    events = []
    readiness_receipt = None
    schedule = None if wait_for_ready else ((20,1,0), (21,13,0), (21+full_press_hold,13,1), (21.5+full_press_hold,1,1))
    if not automatic_shutter:
        schedule = ()
    def input_step(machine, row):
        nonlocal phase, schedule, readiness_receipt
        diagnostic = extra_observation_hook(machine, row) if extra_observation_hook else None
        if schedule is None:
            with machine.io:
                inhibit = machine._words(0xC1821EB8,1)[0]
                joined = machine._words(0xC1868AE8,1)[0]
            if row['virtual_seconds'] < 17 or row['index'] != 3 or inhibit != 0 or joined != 3:
                return diagnostic
            now = row['virtual_seconds']
            readiness_receipt = {'virtual_seconds':now,'input_inhibit':inhibit,'ready_join':joined}
            schedule = ((now+.5,1,0), (now+1.5,13,0),
                        (now+1.5+full_press_hold,13,1), (now+2+full_press_hold,1,1))
            print('ORIGINAL_READY',readiness_receipt,flush=True)
        if phase >= len(schedule) or row['virtual_seconds'] < schedule[phase][0]:
            return diagnostic
        _, pin, level = schedule[phase]
        with machine.io:
            machine._qtest(f'set_irq_in /machine/controller/keys-gpio unnamed-gpio-in {pin} {level}')
            contact_observation = extra_contact_hook(machine, pin, level) if extra_contact_hook else None
        item = {'kind':'external-shutter-contact', 'pin':pin, 'level':level,
                'virtual_seconds':row['virtual_seconds']}
        if contact_observation is not None:
            item['additional_contact_path'] = contact_observation
        phase += 1
        events.append(item)
        print('CONTACT', item, flush=True)
        return item
    def hit(remote, registers):
        pointer = registers['r0']
        result = {}
        if pointer == 0x041B0040:
            payload = registers['r1']
            if 0xC0000000 <= payload <= 0xDFFFFFFF-0x440:
                result = {'message':hex(pointer), 'payload':hex(payload),
                        'payload_32':remote.read(payload,32).hex(),
                        'payload_word_428':remote.read(payload+0x428,4).hex(),
                        'payload_word_42c':remote.read(payload+0x42c,4).hex()}
        if 0xC0000000 <= pointer <= 0xDFFFFFFF-128:
            result = {'input_r0':hex(pointer), 'input_bytes_128':remote.read(pointer,128).hex()}
        if extra_hit_hook is not None:
            result.update(extra_hit_hook(remote, registers))
        return result
    args = SimpleNamespace(output=output,qemu=host.DEFAULT_QEMU,native_source=True,
        input_drain=True,frame_start=True,boundary_experiment=False,boundary_line=136,
        ready_bit_experiment=False,ready_set_experiment=False,lifecycle=False,frame_objects=False,
        ownership=False,metadata_event_experiment=False,startup_waits=False,
        virtual_limit=duration,wall_limit=wall_limit if wall_limit is not None else (1500 if wait_for_ready else 1200),menu_at=1000,reopen_delay=1000,
        poll=2,max_stops=max_stops,sd_card=card,breakpoint_window=breakpoint_window,
        write_watchpoints=write_watchpoints, read_watchpoints=read_watchpoints,
        observation_timeout_recovery=observation_timeout_recovery)
    try:
        result = capture.run(args, extra_hit_hook=hit, extra_observation_hook=input_step)
    finally:
        capture.POINTS,capture.STATE,raw.configure_command,capture.trace.observe_capture,capture.host.host.apply_console = old
    result['shutter_contacts'] = events
    result['automatic_shutter_enabled'] = automatic_shutter
    result['waited_for_original_ready'] = wait_for_ready
    result['readiness_receipt'] = readiness_receipt
    result['full_press_hold_seconds'] = full_press_hold
    result['virtual_card'] = {'path':str(card), 'snapshot':True, 'before_sha256':before,
                              'after_sha256':digest(card)}
    result['input_adapter'] = shutter.identity()
    result['monitor_transport'] = monitor.identity()
    result['extra_probe_points'] = {hex(k):v for k,v in (extra_points or {}).items()}
    result['replacement_probe_points'] = {hex(k):v for k,v in (only_points or {}).items()}
    result['shutter_route_observation_completed'] = bool(result['capture_setup_observed'] and
        len(events)==4 and result['virtual_card']['after_sha256']==before and
        result.get('stop_reason')=='virtual limit' and result['observations'][-1]['virtual_seconds']>=duration)
    (output/'trace.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--card',type=Path,required=True)
    args=p.parse_args()
    result=run(args.output,args.card)
    print(result['summary'])
    raise SystemExit(0 if result['shutter_route_observation_completed'] else 1)
