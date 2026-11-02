"""Reject mixed full-press while validating actual half-press menu cycles."""
import json
import sys
import probe_z62_shutter_cycle as prior
import z62_shutter_input_v2 as shutter


def run(args):
    timing = prior.transaction.timing
    old_observe, old_shutter = timing.observe_capture, prior.shutter
    def observe(machine):
        capture = old_observe(machine)
        capture['input_switch_words'] = [hex(w) for w in machine._words(0xC25D6FC0, 3)]
        return capture
    timing.observe_capture, prior.shutter = observe, shutter
    try:
        result = prior.run(args)
    finally:
        timing.observe_capture, prior.shutter = old_observe, old_shutter
    words = [int(r['capture']['input_switch_words'][0], 16)
             for r in result['samples'] if 'input_switch_words' in r.get('capture', {})]
    result['half_press_observed'] = any(w & 0x80000000 for w in words)
    result['full_press_observed'] = any(w & 0x40000000 for w in words)
    result['isolated_half_press_verified'] = bool(result['half_press_observed'] and
        not result['full_press_observed'] and result['preview_after_half_press_verified'])
    (args.output / 'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    argv = list(sys.argv[1:])
    if '--qemu' not in argv:
        argv += ['--qemu', str(prior.host.DEFAULT_QEMU)]
    args = prior.transaction.parse_args(argv)
    args.raw_stream = args.input_drain = args.paired_sync = args.capcom_sync = True
    if not args.functional_raw or not args.raw_completion:
        raise ValueError('functional-raw and raw-completion required')
    result = run(args)
    print({k: result[k] for k in ('half_press_observed','full_press_observed',
                                'isolated_half_press_verified','dwells')})
    raise SystemExit(0 if result['isolated_half_press_verified'] else 1)
