# SPDX-License-Identifier: GPL-2.0-or-later
"""Observe a local original-firmware menu cycle using only key-pin requests.

Does not write guest memory, force application indices, or claim absence of an
error dialog from foreground indices alone. PNGs require independent inspection.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def run(url, output, timeout):
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('Only local reference consoles are allowed')
    output.mkdir(parents=True, exist_ok=False)
    record = {'schema': 1, 'url': url, 'guest_state_written': False,
              'input': 'controller key pins, debounced press/release', 'observations': []}
    started = time.monotonic()
    def request(path, data=None):
        req = Request(url + path, data=None if data is None else json.dumps(data).encode(),
                      headers={} if data is None else {'Content-Type': 'application/json'})
        with urlopen(req, timeout=30) as response:
            return response.read()
    def save():
        (output / 'report.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    def observe(label, frame=False):
        state = json.loads(request('/status'))
        item = {'label': label, 'wall_seconds': round(time.monotonic() - started, 2), 'status': state}
        if frame and state.get('phase') == 'running':
            png = request('/frame')
            name = f'{len(record["observations"]):03d}-{label}.png'
            (output / name).write_bytes(png)
            item['frame'] = {'file': name, 'sha256': hashlib.sha256(png).hexdigest()}
        record['observations'].append(item)
        save()
        print(label, state.get('phase'), state.get('index'), state.get('virtual_seconds'),
              state.get('display_enabled'), flush=True)
        if state.get('phase') == 'failed' or state.get('error'):
            raise RuntimeError(str(state))
        return state
    def press(pin):
        request('/key', {'pin': pin, 'level': 0})
        request('/key', {'pin': pin, 'level': 1})
    def settle(label, virtual_delta=1.5, wall_limit=100):
        first = observe(label + '-start')
        virtual = first.get('virtual_seconds', 0)
        deadline = time.monotonic() + wall_limit
        while time.monotonic() < deadline:
            time.sleep(5)
            state = observe(label + '-wait')
            if state.get('virtual_seconds', 0) >= virtual + virtual_delta and not state.get('queued'):
                break
        return observe(label, frame=True)
    try:
        deadline = started + timeout
        while time.monotonic() < deadline:
            state = observe('boot')
            if state.get('index') == 1 and state.get('display_enabled') and not state.get('queued'):
                break
            time.sleep(10)
        else:
            record['menu_ready'] = False
            observe('boot-timeout', frame=True)
            return record
        record['menu_ready'] = True
        observe('menu', frame=True)
        request('/auto-menu', {'enabled': False})
        press(4)
        settle('menu-down')
        press(0)
        exited = settle('after-exit', virtual_delta=4, wall_limit=150)
        record['left_menu'] = exited.get('index') != 1
        press(9)
        reopened = settle('after-reopen', virtual_delta=4, wall_limit=150)
        record['reopened_menu'] = reopened.get('index') == 1 and reopened.get('display_enabled')
        return record
    finally:
        try:
            request('/release', {})
        finally:
            save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8662')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=720)
    args = parser.parse_args()
    record = run(args.url.rstrip('/'), args.output, args.timeout)
    print(json.dumps({name: record.get(name) for name in ('menu_ready', 'left_menu', 'reopened_menu')}))
    if not all(record.get(name) for name in ('menu_ready', 'left_menu', 'reopened_menu')):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
