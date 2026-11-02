# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded original-firmware capture observation on the verified r6 machine.

No automatic/menu keys, guest functions or software state patches. Passive by
default. An explicit experiment can request real QEMU RAW DMA then supply one
decoded boundary only after the device confirms a complete four-slot write.
These diagnostic events are not yet a production sensor timing model.
Run once per Python process; preserves failures and closes only its own QEMU.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

import run_z62_capcom as host
from z62_capture_observation import install_preset, observe_capture
from z62_development_status import functional_raw_status
from z62_transaction_status import transaction_status
from z62_capcom_status import capcom_status

# LCD is implemented and mapped by Z62. The ISP/command addresses below are
# REFERENCE hypotheses to inspect, not established Z62 processing contracts.
REGISTERS = {
    'lcd_scanout': (0x20144200, 28),
    'lcd_enable': (0x20144110, 1),
    'lcd_interrupt': (0x20145200, 6),
    'isp_control_reference': (0x20380008, 1),
    'isp_irq_reference': (0x20380020, 2),
    'isp_geometry_reference': (0x20380048, 1),
    'isp_input_reference': (0x20380300, 9),
    'command0_reference': (0x20102000, 7),
    'command1_reference': (0x20102100, 7),
    'sequence_reference': (0x20102600, 9),
    'output3_reference': (0x201004C0, 13),
    'output4_reference': (0x20100500, 13),
    'output5_reference': (0x20100540, 13),
    'capture_flags': (0xC269FA0C, 8),
    'capture_mode': (0xC1888084, 1),
    'capture_state': (0xC1868490, 8),
    'sensor_mode': (0x20065504, 3),
    'input_bank3_mask': (0x20068260, 1),
    'input_bank4_mask': (0x20068280, 1),
    'channel1_descriptor': (0xC26A060C, 24),
    'channel2_descriptor': (0xC26A0AC4, 18),
    'raw_bank': (0x20069A3C, 1),
    'processing1_format': (0x2006A514, 2),
    'processing1_stride': (0x2006A524, 1),
    'processing1_control_addresses': (0x2006A53C, 6),
    'processing1_second_address': (0x2006A560, 1),
    'processing1_slot_bytes': (0x2006A580, 1),
    'processing2_format': (0x2006A614, 2),
    'processing2_stride': (0x2006A624, 1),
    'processing2_addresses': (0x2006A650, 8),
    'processing2_slot_bytes': (0x2006A680, 1),
}


def registers(machine):
    result = {}
    for name, (address, count) in REGISTERS.items():
        try:
            words = machine._words(address, count)
            result[name] = {'address': hex(address), 'read_succeeded': True,
                            'layout_verified': name.startswith('lcd_'),
                            'words': [hex(word) for word in words]}
        except (OSError, RuntimeError, ValueError) as exc:
            result[name] = {'address': hex(address), 'read_succeeded': False,
                            'layout_verified': name.startswith('lcd_'),
                            'error': type(exc).__name__ + ': ' + str(exc)}
    return result


def collect_logs(work, output):
    """Console saves last-* before removing its disposable run directory."""
    result = {}
    for name in ('console.txt', 'command.json'):
        source = work / 'runs' / ('last-' + name)
        data = source.read_bytes()
        target = output / name
        if target.exists():
            if target.read_bytes() != data:
                raise ValueError('Refusing changed log evidence: ' + str(target))
        else:
            with target.open('xb') as stream:
                stream.write(data)
        result[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
                        'origin': 'console cleanup snapshot before run-directory removal'}
    return result


def expected_raw_prefix():
    result = bytearray()
    for x in range(0, 22, 2):
        a, b = 3*x + 0x100, 3*(x+1) + 0x100
        result.extend((a & 255, (a >> 8) | ((b & 15) << 4), b >> 4))
    return bytes(result[:32])


def qtest_read(machine, address, size):
    # The inherited console _qtest helper deliberately only accepts bare OK
    # control replies. A memory read has a distinct OK 0x<data> response.
    machine.wire_file.write(f'read {address:#x} {size:#x}\n'.encode('ascii'))
    machine.wire_file.flush()
    line = machine.wire_file.readline().decode('ascii').strip()
    if not line.startswith('OK 0x'):
        raise ValueError('QTest memory read failed: ' + line[:200])
    data = bytes.fromhex(line[5:])
    if len(data) != size:
        raise ValueError('QTest memory read length mismatch')
    return data


def master_event_path(machine):
    configs = machine.qmp.command('qom-list', {'path': '/machine/unattached'})
    paths = ['/machine/unattached/'+e['name'] for e in configs
             if e['type'] == 'child<nikon-z72-boot-config>']
    masters = [path for path in paths if machine.qmp.command('qom-get',
                {'path': path, 'property': 'master-role'}) is True]
    if len(masters) != 1:
        raise ValueError('Cannot identify unique master event endpoint')
    return masters[0]


def metadata_after_transaction(machine, transaction):
    """Probe existing metadata notification only for a verified channel2 transfer."""
    if (not transaction.get('boundary_supplied') or transaction.get('boundary_line') != 136 or
            transaction.get('byte_delta') != 9142528):
        return {'supplied': False, 'reason': 'no verified channel2 RAW transaction'}
    enabled = machine._words(0x20069F00, 1)[0]
    mask = machine._words(0x20068200, 1)[0]
    if enabled & 0x11 != 0x11:
        return {'supplied': False, 'reason': 'metadata source not enabled', 'control': hex(enabled)}
    path = master_event_path(machine)
    for level in (1, 0):
        machine._qtest(f'set_irq_in {path} input-event 6 {level}')
    return {'supplied': True, 'boundary_line': 6, 'control': hex(enabled), 'mask': hex(mask),
            'statistics_values_verified': False}


def raw_boundary_transaction(machine, boundary_line=103):
    """Bounded diagnostic route, never complete a failed or unarmed RAW write.

    103 is the earlier wrong-stage control; 136 maps through original
    10239184 -> task4000 -> 10238C44 -> descriptor C26A0AC4 (RAW channel2).
    """
    if boundary_line not in (103, 136):
        raise ValueError('Unsupported diagnostic boundary route')
    mask_address = 0x20068200 + (boundary_line//32)*0x20
    mask_bit = 1 << (boundary_line%32)
    def get(prop):
        return machine.qmp.command('qom-get', {'path': '/machine/master-input', 'property': prop})
    if machine._words(0x20068008, 1)[0] != 0x200 or not machine._words(mask_address, 1)[0] & mask_bit:
        return {'submitted': False, 'reason': 'capture path or selected completion is not armed'}
    bank = machine._words(0x20069A3C, 1)[0] & 1
    addresses = machine._words(0x20069A50 + bank*16, 4)
    before, before_bytes = get('raw-accepted'), get('raw-bytes')
    for level in (0, 1, 0):
        machine._qtest(f'set_irq_in /machine/master-input raw-submit 0 {level}')
    after, after_bytes = get('raw-accepted'), get('raw-bytes')
    result = {'submitted': True, 'accepted_before': before, 'accepted_after': after,
              'byte_delta': after_bytes-before_bytes, 'reason': get('raw-last-reason'),
              'boundary_supplied': False, 'selected_bank': bank,
              'descriptor_addresses': [hex(address) for address in addresses]}
    if after != before+1 or after_bytes-before_bytes != 4*2285632:
        return result
    # Recheck after DMA; host operations are not an atomic hardware clock edge.
    if machine._words(0x20068008, 1)[0] != 0x200 or not machine._words(mask_address, 1)[0] & mask_bit:
        result['reason'] = 'configuration changed after DMA'
        return result
    if ((machine._words(0x20069A3C, 1)[0] & 1) != bank or
            machine._words(0x20069A50 + bank*16, 4) != addresses):
        result['reason'] = 'descriptors changed during host transaction'
        return result
    # Actual device readback, not a write through the debugger.
    data = qtest_read(machine, addresses[0], 32)
    result['first_raw_bytes'] = data.hex()
    if data != expected_raw_prefix():
        result['reason'] = 'actual RAW prefix does not match the configured synthetic source'
        return result
    path = master_event_path(machine)
    for level in (1, 0):
        machine._qtest(f'set_irq_in {path} input-event {boundary_line} {level}')
    result['boundary_supplied'] = True
    result['boundary_line'] = boundary_line
    return result


def run(args):
    if args.output.exists():
        raise FileExistsError('Existing observation directory is protected')
    if args.native_raw_stream:
        import run_z62_raw_stream as native_stream
        manifest = native_stream.verify_build(args.qemu.resolve())
    else:
        manifest = host.verify_build(args.qemu.resolve())
    args.output.mkdir(parents=True, exist_ok=False)
    original_popen, old_path = subprocess.Popen, list(sys.path)
    machine, work = None, None
    report = {'schema': 2, 'observation_completed': False, 'live_view_verified': False,
              'camera_accessed': False, 'guest_software_patched': False,
              'snapshots_nonatomic': True, 'reference_isp_contract_verified': False,
              'samples': [], 'frames': [], 'register_samples': [],
              'requested_virtual_seconds': args.duration, 'guest_error_logging': args.guest_errors,
              'frame_start_phase': args.frame_start,
              'raw_boundary_experiment': args.raw_boundary_experiment,
              'raw_boundary_line': args.raw_boundary_line, 'raw_transactions': [],
              'metadata_after_raw': args.metadata_after_raw, 'metadata_events': [],
              'native_raw_stream': args.native_raw_stream,
              'input_drain_completion': args.input_drain}
    start = time.monotonic()
    next_frame = 2.0
    next_transaction = 2.5
    pending_metadata = []
    try:
        work, record = host.host.r4.base.stage('z62', args.qemu,
            experimental_parameters=True, updates=True)
        host.host.apply_console(work / 'source')
        host.apply_status(work / 'source')
        if args.native_raw_stream:
            native_stream.apply_status(work / 'source')
        record.update(capcom_device=manifest, capcom_sync=True, functional_raw=True,
                      raw_completion=True, capture_preset='init-mode', no_auto_menu=True,
                      frame_start_phase=args.frame_start,
                      raw_boundary_experiment=args.raw_boundary_experiment,
                      raw_boundary_line=args.raw_boundary_line,
                      metadata_after_raw=args.metadata_after_raw,
                      native_raw_stream=args.native_raw_stream,
                      input_drain_completion=args.input_drain)
        (args.output / 'session.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        sys.path.insert(0, str(work / 'source'))
        module = importlib.import_module('tools.z62_console')
        host.host.r4.base.install_native_process_adapter(work)
        parent = install_preset(subprocess.Popen, 'init-mode')
        class CapturePopen(parent):
            def __init__(self, command, *a, **kw):
                if isinstance(command, (list, tuple)) and 'qemu-system-arm' in str(command[0]):
                    command = host.configure_command(host.host.configure_command(command, True, True), True)
                    if args.native_raw_stream:
                        command = native_stream.configure_command(command, True)
                    if args.input_drain:
                        command += ['-global', 'nikon-z72-boot-config.input-command-completion=on']
                    if args.frame_start:
                        command += ['-global', 'nikon-z72-boot-config.frame-start=on']
                    if args.guest_errors:
                        command += ['-d', 'guest_errors,unimp']
                    if args.trace_lcd:
                        kw['env'] = {**kw.get('env', os.environ), 'Z62_LCD_TRACE': '1'}
                super().__init__(command, *a, **kw)
        subprocess.Popen = CapturePopen
        sd_card = getattr(args, 'sd_card', None)
        if sd_card is not None:
            from z62_virtual_sd import image_path
            sd_card = image_path(sd_card)
        config = SimpleNamespace(qemu=args.qemu.resolve(), master=work/'inputs/master.bin',
            slave=work/'inputs/slave.bin', controller=work/'inputs/controller.bin',
            parameters=work/'parameters', runs=work/'runs', auto_menu=False, no_auto_menu=True,
            main_screen_experiment=False, sd_card=sd_card, wsl=False, sampling_source=False,
            input_trace=True, update_store=work/'update-store')
        machine = module.Z62Machine(config)
        machine.restart()
        while machine.phase not in ('running', 'failed'):
            if time.monotonic() - start > 60:
                raise TimeoutError('Machine start timeout')
            time.sleep(.05)
        if machine.phase != 'running':
            raise RuntimeError(machine.error)
        report['pid'] = machine.process.pid
        while time.monotonic() - start < args.wall_limit:
            if machine.process.poll() is not None:
                raise RuntimeError('Owned QEMU exited unexpectedly')
            row = {'wall_seconds': round(time.monotonic() - start, 3)}
            try:
                row.update(machine.status())
                with machine.io:
                    row['capture'] = observe_capture(machine)
                    row['capture'].update(functional_raw_status(machine))
                    row['capture'].update(transaction_status(machine))
                    row['capture'].update(capcom_status(machine))
                    if args.native_raw_stream:
                        from z62_raw_stream_status import raw_stream_status
                        row['capture'].update(raw_stream_status(machine))
            except (OSError, RuntimeError, ValueError) as exc:
                row['observation_error'] = type(exc).__name__ + ': ' + str(exc)
            report['samples'].append(row)
            now = row.get('virtual_seconds')
            if pending_metadata and now is not None and now >= pending_metadata[0][0]:
                _, transaction_index = pending_metadata.pop(0)
                with machine.io:
                    event = metadata_after_transaction(machine, report['raw_transactions'][transaction_index])
                event.update(transaction_index=transaction_index, virtual_seconds_before=now)
                report['metadata_events'].append(event)
                print('METADATA_EVENT', json.dumps(event), flush=True)
            if (args.raw_boundary_experiment and now is not None and now >= next_transaction and
                    len(report['raw_transactions']) < args.raw_transactions):
                with machine.io:
                    transaction = raw_boundary_transaction(machine, args.raw_boundary_line)
                transaction['virtual_seconds_before'] = now
                report['raw_transactions'].append(transaction)
                if args.metadata_after_raw and transaction.get('boundary_supplied'):
                    pending_metadata.append((now+.1, len(report['raw_transactions'])-1))
                print('RAW_TRANSACTION', json.dumps(transaction), flush=True)
                next_transaction = now + .5
            if now is not None and now >= next_frame:
                label = 'frame-' + str(len(report['frames']))
                png = machine.frame_png()
                (args.output / (label + '.png')).write_bytes(png)
                report['frames'].append({'file': label + '.png', 'virtual_seconds': now,
                                          'sha256': hashlib.sha256(png).hexdigest()})
                with machine.io:
                    report['register_samples'].append({'virtual_seconds': now,
                        'address_space': 'guest virtual, master CPU0', 'registers': registers(machine)})
                next_frame += 5
            print(json.dumps({k: row.get(k) for k in ('virtual_seconds', 'index',
                'firmware_status_codes', 'display_enabled', 'lcd_frames', 'observation_error')}), flush=True)
            if now is not None and now >= args.duration:
                report['observation_completed'] = True
                report['stop_reason'] = 'requested virtual duration'
                break
            if machine.work and (machine.work/'console.txt').stat().st_size > 64 * 1024 * 1024:
                report['stop_reason'] = 'bounded diagnostic log limit'
                break
            (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            time.sleep(args.poll)
        else:
            report['stop_reason'] = 'wall limit'
    except Exception as exc:
        report['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        if machine is not None:
            process = machine.process
            try:
                machine.close()
            except Exception as exc:
                report['cleanup_error'] = str(exc)
            report['qemu_exit_code'] = process.poll() if process is not None else None
            report['clean_exit'] = process is not None and process.poll() == 0
            if machine.work:
                for name in ('console.txt', 'command.json'):
                    if (machine.work/name).exists():
                        shutil.copyfile(machine.work/name, args.output/name)
        subprocess.Popen = original_popen
        sys.path[:] = old_path
        if work is not None:
            try:
                report['logs'] = collect_logs(work, args.output)
            except (OSError, ValueError) as exc:
                report['log_collection_error'] = str(exc)
            for source in work.glob('effective-command-*.json'):
                shutil.copyfile(source, args.output/source.name)
        report['observation_completed'] = bool(report['observation_completed'] and report.get('clean_exit')
                                               and not report.get('cleanup_error')
                                               and not report.get('log_collection_error'))
        (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qemu', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--duration', type=float, default=20)
    p.add_argument('--wall-limit', type=float, default=900)
    p.add_argument('--poll', type=float, default=2)
    p.add_argument('--guest-errors', action='store_true')
    p.add_argument('--trace-lcd', action='store_true')
    p.add_argument('--frame-start', action='store_true',
                   help='Explicit existing paired sync phase; no forced capture boundary')
    p.add_argument('--collect-logs', action='store_true',
                   help='Recover saved cleanup logs for an already closed observation; no QEMU run')
    p.add_argument('--raw-boundary-experiment', action='store_true',
                   help='Supply selected completion only after verified actual four-slot RAW DMA; diagnostic')
    p.add_argument('--raw-boundary-line', type=int, choices=(103,136), default=136,
                   help='136: channel2 RAW completion; 103: earlier wrong-stage control')
    p.add_argument('--raw-transactions', type=int, default=2)
    p.add_argument('--metadata-after-raw', action='store_true',
                   help='Diagnostic metadata event after each successful channel2 RAW transfer')
    p.add_argument('--native-raw-stream', action='store_true',
                   help='Use r7 device frame source; prohibits host RAW/boundary experiments')
    p.add_argument('--input-drain', action='store_true',
                   help='Enable existing command-matched input stop/drain acknowledgement')
    args = p.parse_args()
    if args.qemu is None:
        if args.native_raw_stream:
            from run_z62_raw_stream import DEFAULT_QEMU
            args.qemu = DEFAULT_QEMU
        else:
            args.qemu = host.DEFAULT_QEMU
    if (not 2 <= args.duration <= 120 or not 10 <= args.wall_limit <= 3600 or
            not .1 <= args.poll <= 30 or not 1 <= args.raw_transactions <= 10):
        p.error('duration 2..120, wall-limit 10..3600, poll .1..30 required')
    if args.metadata_after_raw and (not args.raw_boundary_experiment or args.raw_boundary_line != 136):
        p.error('--metadata-after-raw requires the channel2 RAW experiment')
    if args.native_raw_stream and (args.raw_boundary_experiment or args.metadata_after_raw):
        p.error('Native source observations cannot inject host RAW/boundary events')
    if args.collect_logs:
        report = json.loads((args.output/'report.json').read_text(encoding='utf-8'))
        if report.get('clean_exit') is not True:
            p.error('Only a recorded cleanly closed observation can collect saved logs')
        record = json.loads((args.output/'session.json').read_text(encoding='utf-8'))
        result = collect_logs(Path(record['work']), args.output)
        with (args.output/'collected-logs.json').open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
        print(json.dumps(result))
    else:
        raise SystemExit(0 if run(args)['observation_completed'] else 1)
