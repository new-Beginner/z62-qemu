"""Bind the r76 reader before shutter input, then summarize its actual samples."""
import argparse
import hashlib
import json
from pathlib import Path

from z62_action_queue_console import VERSION, decode_capture, queue_layout

ROOT = Path(__file__).resolve().parents[1]
MODULES = ('tools/z62_console.py', 'tools/z62_action_queue_console.py',
           'tools/z62_persistent_diagnostic_console.py', 'tools/z62_paired_diagnostic_console.py',
           'tools/z62_paired_console.py', 'tools/z62_workspace_paths.py',
           'web-z62/console.js', 'web-z62/index.html')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workspace(path):
    path = Path(path).absolute()
    require(path.resolve().is_relative_to(ROOT.resolve()), 'Evidence must stay inside the workspace')
    return path


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def bind(session, case, output, *, allow_post_shutter=False):
    session, case, output = map(workspace, (session, case, output))
    journal = case/'observations.jsonl'
    data = journal.read_bytes()
    # Binding must precede every shutter send, even a send whose reply is unknown.
    events = [json.loads(line) for line in data.splitlines()]
    before = not any(e['kind'] == 'send' and e['value'].get('type') == 'shutter' for e in events)
    require(before or allow_post_shutter,
            'Too late to claim a pre-shutter source binding')
    sources = {str(session/'source'/name): digest(session/'source'/name) for name in MODULES}
    # r73 replaces this one import in each generated copy, keeping data in Q:.
    original = (ROOT/'tools/z62_action_queue_console.py').read_text(encoding='utf-8')
    anchor = 'from pathlib import Path\n'
    require(original.count(anchor) == 1, 'Unexpected filesystem import')
    expected = original.replace(anchor, 'from tools.z62_workspace_paths import WorkspacePath as Path\n')
    require((session/'source/tools/z62_action_queue_console.py').read_bytes() == expected.encode('utf-8'),
            'Generated action reader differs beyond the reviewed r73 import mapping')
    record = {'schema': 1, 'version': VERSION, 'session': str(session), 'case': str(case),
              'source_sha256': sources, 'tool_sha256': digest(Path(__file__)),
              'journal_prefix_bytes': len(data), 'journal_prefix_sha256': hashlib.sha256(data).hexdigest(),
              'bound_before_shutter_send': before,
              'binding_scope': 'before-shutter' if before else 'ongoing-observation-only',
              'camera_accessed': False}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
    return record


def summary(row):
    require(row['action_queue_version'] == VERSION, 'Not an r76 sample')
    queue = row['capture_work_queue']
    require(queue['known_layout'] is True, 'Queue layout is unknown')
    layout = queue_layout(queue['header_before'])
    require(all(queue[k] == v for k, v in layout.items()), 'Decoded queue fields differ')
    require(queue['header_stable_during_read'] == (queue['header_before'] == queue['header_after']),
            'Queue stability verdict differs')
    require(sum(queue['work_id_counts'].values()) == layout['count'] and
            len(queue['work_ids_in_order']) == layout['count'], 'Queue item accounting differs')
    require(queue['atomic_snapshot_proven'] is False and queue['queue_modified_by_reader'] is False,
            'Read-only/non-atomic boundary differs')
    flow = row['capture_flow']
    require(decode_capture(flow['raw_words']) == flow, 'Capture context decoding differs')
    require(row['applv_ram']['words'][22] == row['applv_ram']['action_word_at_c181d388'],
            'APPLV action decoding differs')
    return {'label': row['label'], 'virtual_time_ns': row['virtual_time_ns'],
            'queue_count': layout['count'], 'queue_capacity': layout['capacity'],
            'queue_head': layout['head'], 'queue_header_stable': queue['header_stable_during_read'],
            'work_id_counts': queue['work_id_counts'],
            'capture': {k: flow[k] for k in ('active_word', 'flow_word', 'stage', 'callback',
                       'callback_result_word', 'outstanding', 'elapsed', 'deadline')},
            'applv_action_word': row['applv_ram']['action_word_at_c181d388'],
            'selector': row['selector'], 'output_mode': row['output']['mode'],
            'pipeline_phase': row['pipeline_mode']['phase']}


def finish(binding, output):
    binding, output = map(workspace, (binding, output))
    bound = read(binding); case = workspace(bound['case'])
    require(bound['tool_sha256'] == digest(Path(__file__)), 'Evidence recorder changed after binding')
    require(all(digest(Path(p)) == sha for p, sha in bound['source_sha256'].items()),
            'A generated reader changed during observation')
    data = (case/'observations.jsonl').read_bytes()
    require(hashlib.sha256(data[:bound['journal_prefix_bytes']]).hexdigest() ==
            bound['journal_prefix_sha256'], 'Pre-shutter journal was changed')
    result = read(case/'result.json')
    require(result['completed_observation'] is True and result['source_unchanged'] is True,
            'Underlying selector observation is incomplete or changed')
    require(all(digest(Path(p)) == sha for p, sha in result['source_sha256'].items()),
            'Underlying selector source changed')
    rows = [summary(row) for row in result['samples']]
    after = [row for row in rows if row['label'] != 'initial-photo-and-original-gate']
    require(after and all(row['header_stable_during_read'] for row in
                         (s['capture_work_queue'] for s in result['samples'])),
            'A non-atomic queue read also had a changing header')
    eligible = not result['read_errors'] and not any(s['host_capture_attempted'] for s in result['samples'])
    require(result['functional_acceptance_eligible'] ==
            (not any(s['host_capture_attempted'] for s in result['samples'])),
            'Underlying debugger qualification differs')
    record = {'schema': 1, 'version': VERSION, 'completed_evidence_check': True,
              'source_binding_sha256': digest(binding), 'case_result_sha256': digest(case/'result.json'),
              'r76_reader_bound_before_shutter': bound['bound_before_shutter_send'],
              'r76_source_unchanged_since_binding': True,
              'journal_sha256': digest(case/'observations.jsonl'), 'sample_count': len(rows),
              'unperturbed_observation': eligible, 'read_errors': result['read_errors'],
              'initial_gate': summary(result['initial_gate']),
              'after_photo': summary(result['after_photo']), 'final': summary(result['final']),
              'after_shutter_queue_count_range': [min(r['queue_count'] for r in after),
                                                max(r['queue_count'] for r in after)],
              'full_queue_sampled_after_shutter': any(r['queue_count'] == r['queue_capacity'] for r in after),
              'video_mode_confirmed': result['video_mode_confirmed'],
              'queue_enqueue_return_observed': False, 'atomic_snapshot_proven': False,
              'factory_capture_verified': False, 'AF_verified': False, 'flash_safety_verified': False,
              'camera_accessed': False, 'samples': rows}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    initial = commands.add_parser('bind')
    initial.add_argument('--session', type=Path, required=True)
    initial.add_argument('--case', type=Path, required=True)
    initial.add_argument('--allow-post-shutter-binding', action='store_true',
                         help='Explicitly record reduced ongoing-observation scope')
    final = commands.add_parser('finish')
    final.add_argument('--binding', type=Path, required=True)
    for command in (initial, final):
        command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    record = bind(args.session, args.case, args.output, allow_post_shutter=args.allow_post_shutter_binding) \
        if args.command == 'bind' else finish(args.binding, args.output)
    print(json.dumps({k: v for k, v in record.items() if k not in ('source_sha256', 'samples')}, ensure_ascii=False))
