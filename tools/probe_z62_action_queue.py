"""Bind r76 sources before the first diagnostic read, preserving the r72 scenario."""
import argparse
from pathlib import Path
import urllib.request
from unittest.mock import patch

import probe_z62_paired_selector_diagnostic as scenario
import record_z62_action_evidence as evidence


def run(url, session, output):
    original = urllib.request.urlopen
    bound = False

    def request(req, *args, **kwargs):
        nonlocal bound
        if not bound and req.full_url == url.rstrip('/')+'/paired/diagnostics':
            # The scenario has opened its new journal but has sent no controls.
            evidence.bind(session, output, output/'source-binding.json')
            bound = True
        return original(req, *args, **kwargs)

    with patch.object(urllib.request, 'urlopen', request):
        result = scenario.run(url, session, output)
    if result['completed_observation']:
        if not bound:
            raise ValueError('No source binding preceded observation')
        evidence.finish(output/'source-binding.json', output/'verified-action.json')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8688')
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.url, args.session, args.output)
    raise SystemExit(0 if result['completed_observation'] and result['source_unchanged'] else 1)
