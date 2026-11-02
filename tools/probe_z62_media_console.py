"""Actual QEMU JPEG+NEF/NEF-only body flow with independent whole-RAW audit."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

import probe_z62_entry as entry
import probe_z62_native_scene_console as native
from z62_software_camera import SoftwareCamera, Scene, Frame
from z62_nef_codec import raw14_from_consumed_frame
from z62_media_card import MediaCard

ROOT = Path(__file__).resolve().parents[1]


def run(output, decoder_python, firmware=None, url=None, stop=False):
    if output.exists():
        raise ValueError('Fresh probe output required')
    receipt = {'schema': 1, 'completed': False, 'implementation_level': 'C', 'audits': [], 'events': [],
               'factory_nef_equivalence_verified': False, 'camera_accessed': False}
    verified = False
    http = None

    def checks(request):
        nonlocal verified
        state = json.loads(request('/software/status'))
        native.require(state.get('media_profile') == '2026.11.01-media-console-r25' and
                       state.get('capture_format') == 'jpeg-nef', 'Expected a fresh r25 JPEG+NEF profile')
        verified = True
        audited = False

        def audit_current(label):
            current = json.loads(request('/software/status'))
            item = current['card']['images'][0]
            member = next(row for row in item['files'] if row['name'].endswith('.NEF'))
            data = request('/software/file/' + member['name'])
            path = output / (label + '.NEF')
            path.write_bytes(data)
            meta = item['metadata']
            reference = SoftwareCamera(width=meta['width'], height=meta['height'], scene=Scene(), clock_epoch=meta['clock_epoch'])
            reference.event('power', {'on': True}, 0)
            reference.lens = deepcopy(meta['lens'])
            reference.lens['moving'] = False
            reference.exposure = deepcopy(meta['exposure'])
            frame = reference.frame(meta['virtual_time_ns'])
            frame.metadata = deepcopy(meta)
            raw, _ = raw14_from_consumed_frame(frame)
            expected = output / (label + '-raw14.bin')
            expected.write_bytes(raw.astype('<u2').tobytes())
            audit = output / (label + '-independent.json')
            result = subprocess.run([str(decoder_python), '-X', 'utf8', '-B', str(ROOT / 'tools/validate_z62_nef.py'),
                '--nef', str(path), '--expected-raw', str(expected), '--output', str(audit)], timeout=120)
            native.require(result.returncode == 0, 'Independent NEF audit failed: ' + label)
            receipt['audits'].append({'name': label, 'item': item, 'receipt': json.loads(audit.read_bytes())})

        def intercept(path, post=False, payload=None):
            nonlocal audited
            if path == '/camera/event' and post and payload == {'type': 'key', 'payload': {'pin': 23, 'level': 0}} and not audited:
                audit_current('pair')
                audited = True
            return request(path, post, payload)

        native.exercise(intercept, output, receipt)
        native.require(audited, 'JPEG+NEF pair was not audited before deletion')
        state = json.loads(request('/software/status'))
        native.require(state['card']['images'] == [], 'Pair deletion left visible media')
        def event(kind, payload):
            return json.loads(request('/camera/event', True, {'type': kind, 'payload': payload}))
        def wait(predicate):
            import time
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                state = json.loads(request('/software/status'))
                if predicate(state):
                    return state
                time.sleep(.15)
            raise TimeoutError('NEF-only body flow did not reach its requested state')
        event('photo-format', {'format': 'nef'})
        event('key', {'pin': 25, 'level': 0})
        event('key', {'pin': 25, 'level': 1})
        state = wait(lambda s: len(s['card']['images']) == 1)
        native.require(state['card']['images'][0]['name'] == 'Z62_0002.NEF', 'NEF-only numbering/format differs')
        audit_current('nef-only')
        event('playback', {'action': 'open'})
        wait(lambda s: s['view'] == 'playback')
        (output / 'nef-only-playback.jpg').write_bytes(request('/software/frame'))
        event('delete', {})
        wait(lambda s: s['card']['images'] == [])
        receipt['nef_only_playback_and_group_delete_verified'] = True

    try:
        if url:
            parsed = urlsplit(url)
            native.require(parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port and
                           parsed.path in ('', '/') and not parsed.query and not parsed.fragment, 'Owned loopback URL required')
            output.mkdir(parents=True, exist_ok=False)
            def http(path, post=False, payload=None):
                request = Request(url.rstrip('/') + path, data=json.dumps(payload or {}).encode() if post else None,
                                  headers={'Content-Type': 'application/json'} if post else {})
                with urlopen(request, timeout=30) as response:
                    return response.read()
            checks(http)
        else:
            result = entry.run(output, expected_version='2026.10.29-no-lens-r16', diagnostic_key='preview_status',
                firmware=firmware, python_entry=ROOT / 'tools/run_z62_media_console.py', expected_hardware_version='2026.11.01-r24',
                require_monitor_transport=True, before_stop=checks, entry_args=['--software-card', str(output.resolve() / 'card')])
            native.require(result['completed'] and result['process_closed'], 'Media host did not close normally')
            with MediaCard(output / 'card') as card:
                native.require(card.list() == [], 'Deleted photo group reappeared after shutdown')
            receipt['process_closed_and_empty_card_reopened'] = True
        receipt['completed'] = True
    except Exception as exc:
        receipt['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        if url and stop and verified:
            try:
                receipt['stop_response'] = http('/stop', True).decode()
            except Exception as exc:
                receipt['stop_failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        if output.is_dir():
            with (output / 'media-check.json').open('x', encoding='utf-8') as handle:
                json.dump(receipt, handle, indent=2)
    print(json.dumps({key: receipt.get(key) for key in ('completed', 'failure', 'nef_only_playback_and_group_delete_verified')}, indent=2))
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--decoder-python', type=Path, default=ROOT / '.build/tools/raw-verify-r25/Scripts/python.exe')
    parser.add_argument('--firmware', type=Path)
    parser.add_argument('--url')
    parser.add_argument('--stop', action='store_true')
    args = parser.parse_args()
    raise SystemExit(0 if run(args.output, args.decoder_python, args.firmware, args.url, args.stop)['completed'] else 1)
