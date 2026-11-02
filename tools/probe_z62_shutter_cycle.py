"""Original menus plus sustained preview after real half-press, using the host adapter."""
import json
import sys
import probe_z62_preview_cycle as preview
import probe_z62_transaction_cycle as transaction
import run_z62_preview as host
import z62_shutter_input as shutter


def verify_dwell(record, cycles):
    groups = []
    active = None
    for row in record.get('samples', []):
        if row.get('stage') == 'after-exit' and row.get('index') == 3:
            if active is None:
                active = []
                groups.append(active)
            active.append(row)
        else:
            active = None
    results = []
    for group in groups:
        first, last = group[0], group[-1]
        start = first['capture']['preview_status']['engines']['master']['preview-batches']
        end = last['capture']['preview_status']['engines']['master']['preview-batches']
        duration = last['virtual_seconds'] - first['virtual_seconds']
        results.append({'first': first['virtual_seconds'], 'last': last['virtual_seconds'],
                        'first_batches': start, 'last_batches': end,
                        'passed': duration >= 5 and end > start and all(
                            not r.get('observation_error') and r.get('status_codes') == [] and
                            not r['capture']['preview_status']['engines']['master']['preview-rejected']
                            for r in group)})
    return {'dwells': results, 'preview_after_half_press_verified':
            len(results) == cycles and all(r['passed'] for r in results) and
            record.get('process_closed') is True and record.get('menu_cycle_state_passed') is True}


def run(args):
    if args.output.exists():
        raise FileExistsError('Existing evidence is protected')
    original = transaction.host.apply_console
    def apply(source, persistent=False):
        original(source, persistent)
        shutter.apply_console(source)
    transaction.host.apply_console = apply
    args.exit_pin = shutter.HALF_PRESS
    args.post_exit_dwell = 5.5
    try:
        result = preview.run(args)
    finally:
        transaction.host.apply_console = original
    result['input_adapter'] = shutter.identity()
    result.update(verify_dwell(result, args.cycles))
    (args.output / 'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    argv = list(sys.argv[1:])
    if '--qemu' not in argv:
        argv += ['--qemu', str(host.DEFAULT_QEMU)]
    args = transaction.parse_args(argv)
    args.raw_stream = args.input_drain = args.paired_sync = args.capcom_sync = True
    if not args.functional_raw or not args.raw_completion:
        raise ValueError('functional-raw and raw-completion required')
    result = run(args)
    print(result['dwells'])
    raise SystemExit(0 if result['preview_after_half_press_verified'] else 1)
