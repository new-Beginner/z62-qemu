"""Exercise the r20 HTTP rotate endpoint and preserve the prior entry checks."""
import argparse
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit

import probe_z62_entry as entry
import z62_encoder_queue as encoder
import z62_encoder_labels as labels


def record_browser_status(url, output):
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('Expected the owned loopback console root URL')
    with entry.urlopen(entry.Request(url.rstrip('/') + '/status'), timeout=15) as response:
        state = json.loads(response.read())
    if (state.get('encoder_adapter') != encoder.identity() or state.get('encoder_labels') != labels.identity()
            or state.get('phase') != 'running' or state['encoder_input']['queued_phases'] != 0
            or state['encoder_input']['phases'] != {'0':0, '1':0}
            or state['encoder_input']['issued_phases'] != 16):
        raise ValueError('Four browser rotation clicks have not completed on the expected console')
    with output.open('x', encoding='utf-8') as handle:
        json.dump({'schema':1, 'read_only':True, 'browser_clicks_expected':4, 'state':state}, handle, indent=2)
    print('Four browser clicks produced 16 phases and returned to rest')


def run(output, firmware=None, *, python_entry=None, hardware_version='2026.10.29-r13', before_stop=None):
    receipt = {'schema': 1, 'completed': False, 'encoder_adapter': encoder.identity(), 'rotations': []}

    def checks(http_request):
        def request(path, payload=None):
            return json.loads(http_request(path, payload is not None, payload))
        initial = request('/status')
        if initial.get('encoder_adapter') != encoder.identity():
            raise ValueError('Unexpected staged encoder identity')
        if initial.get('encoder_labels') != labels.identity():
            raise ValueError('Unexpected staged encoder labels')
        receipt['encoder_labels'] = labels.identity()
        html = http_request('/').decode('utf-8')
        if any(f'aria-label="{label}{direction}"' not in html
               for label in ('主拨轮', '副拨轮') for direction in ('减少一格', '增加一格')):
            raise ValueError('Accessible main/sub controls are missing')
        previous = initial['encoder_input']['issued_phases']
        for index, steps in ((0,1),(0,-1),(1,1),(1,-1)):
            request('/rotate', {'encoder': index, 'steps': steps})
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                state = request('/status')
                actual = state['encoder_input']
                if (actual['known'] and actual['queued_phases'] == 0 and
                        actual['phases'] == {'0': 0, '1': 0}):
                    break
                time.sleep(.1)
            else:
                raise TimeoutError('Encoder queue did not return to rest')
            if actual['issued_phases'] != previous + 4:
                raise ValueError('An HTTP request did not produce four physical phases')
            receipt['rotations'].append({'encoder': index, 'steps': steps, 'status': actual})
            previous = actual['issued_phases']
        before = request('/status')['encoder_input']
        try:
            request('/rotate', {'encoder': True, 'steps': 1})
        except HTTPError as error:
            if error.code != 400:
                raise
        else:
            raise ValueError('Boolean encoder index was accepted')
        after = request('/status')['encoder_input']
        if before != after:
            raise ValueError('Invalid request changed physical queue')
        receipt.update(completed=True, invalid_input_rejected=True)
        if before_stop is not None:
            before_stop(http_request)


    try:
        result = entry.run(output, expected_version='2026.10.29-no-lens-r16',
            diagnostic_key='preview_status', firmware=firmware,
            python_entry=python_entry or entry.ROOT/'tools/run_z62_encoder_console.py',
            require_monitor_transport=True, expected_hardware_version=hardware_version,
            exercise_capture_input=True, before_stop=checks)
        receipt['entry_completed'] = result['completed']
        receipt['completed'] &= result['completed']
    except Exception as exc:
        receipt.update(completed=False, failure={'type':type(exc).__name__, 'message':str(exc)})
    finally:
        if output.is_dir():
            with (output/'encoder-check.json').open('x', encoding='utf-8') as handle:
                json.dump(receipt, handle, indent=2)
    print(json.dumps(receipt, indent=2))
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--firmware', type=Path)
    parser.add_argument('--browser-url')
    args = parser.parse_args()
    if args.browser_url:
        record_browser_status(args.browser_url, args.output)
        raise SystemExit(0)
    raise SystemExit(0 if run(args.output, args.firmware)['completed'] else 1)
