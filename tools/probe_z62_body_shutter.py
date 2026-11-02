"""Verify Z62 body half-press: descriptor 9 -> PG1 -> state1 -> switch bit31.

The route is grounded by input-descriptors/trace.json and the original MCU scan
table at 0804f01d. This wrapper keeps the earlier G14 probe source reproducible.
"""
import argparse
from pathlib import Path
from probe_z62_preview_inputs import run

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = run(args.output, 'gpio-g', 1)
    samples = result['samples']
    observed = any(int(s.get('capture', {}).get('input_route_probe', {}).get(
        'switch_words', ['0'])[0], 16) & 0x80000000 for s in samples)
    print('body_half_switch_observed=', observed)
    raise SystemExit(0 if result['observation_completed'] and observed else 1)
