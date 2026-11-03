"""Read existing QOM diagnostics through GDB's HMP channel on this owned VM."""
import argparse
import importlib
import json
from pathlib import Path
import sys

from probe_z62_capture_submit import owner, profiles, MASTER_SHA
from record_z62_action_evidence import workspace, digest, require

PROPERTIES = ('functional-continuous-stats', 'continuous-attempts', 'continuous-frames',
    'continuous-batches', 'continuous-rejected', 'continuous-bytes', 'continuous-blocked',
    'continuous-index', 'continuous-source', 'continuous-reason', 'finite-attempts',
    'finite-frames', 'finite-batches', 'finite-rejected', 'finite-bytes', 'finite-reason')


def read_property(remote, name):
    require(name in PROPERTIES, 'Only existing input diagnostics may be read')
    command = 'qom-get /machine/master-input '+name
    packet = remote.command('qRcmd,'+command.encode('ascii').hex())
    output = []
    while packet.startswith('O') and packet != 'OK':
        output.append(bytes.fromhex(packet[1:]).decode('utf-8', 'strict'))
        packet = remote.receive()
    require(packet == 'OK', 'Monitor read did not complete: '+packet)
    raw = ''.join(output)
    return {'command': command, 'raw_reply': raw, 'value': json.loads(raw.strip())}


def run(session, previous, output):
    session, previous, output = map(workspace, (session, previous, output))
    old = json.loads(previous.read_text(encoding='utf-8'))
    require(old['completed_observation'] and old['detach'] == 'OK' and old['scope'] == 'fresh-vm-no-controls',
            'A completed fresh no-control observation is required')
    profile = profiles(session); paths = list((session/'runs').glob('*/command.json'))
    require(len(paths) == 1 and profile == old['profile'], 'VM configuration changed')
    command = json.loads(paths[0].read_text(encoding='utf-8'))
    binary = Path(command[0]); require(digest(binary) == profile['diagnostic_profile']['binary_sha256'], 'Runtime changed')
    require(digest(session/'inputs/master.bin') == MASTER_SHA, 'Master changed')
    port = int(command[command.index('-gdb')+1].rsplit(':', 1)[1])
    owned = owner(port, binary); require(owned['ProcessId'] == old['owner']['ProcessId'], 'VM was replaced')
    output.mkdir(parents=True, exist_ok=False)
    record = {'schema': 1, 'version': '2026.11.03-input-counters-r80', 'owner': owned,
        'prior_trace_sha256': digest(previous), 'controls_sent': [], 'camera_accessed': False,
        'guest_memory_written': False, 'functional_acceptance_eligible': False,
        'completed_observation': False, 'properties': {}, 'read_errors': [],
        'source_sha256': {str(p): digest(p) for p in (Path(__file__),
            session/'source/analyze/qemu_display.py', Path(__file__).with_name('probe_z62_capture_submit.py'))}}
    remote = None
    try:
        sys.path.insert(0, str(session/'source'))
        Remote = importlib.import_module('analyze.qemu_display').Remote
        remote = Remote(port); record['attachment_stop'] = remote.command('?')
        require(record['attachment_stop'].startswith(('T05','S05','T02','S02')), 'No stopped target')
        for name in PROPERTIES:
            try:
                record['properties'][name] = read_property(remote, name)
            except (ValueError, RuntimeError) as exc:
                record['read_errors'].append({'property': name, 'type': type(exc).__name__, 'message': str(exc)})
        record['completed_observation'] = not record['read_errors']
    except Exception as exc:
        record['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        if remote is not None:
            try: record['detach'] = remote.command('D')
            except Exception as exc: record['cleanup_error'] = str(exc)
            remote.sock.close()
        record['sources_unchanged'] = all(digest(Path(p)) == sha for p, sha in record['source_sha256'].items())
        with (output/'result.json').open('x', encoding='utf-8') as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
    print(json.dumps(record, ensure_ascii=False), flush=True)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--previous-trace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = run(args.session, args.previous_trace, args.output)
    raise SystemExit(0 if result['completed_observation'] and result.get('detach') == 'OK' else 1)
