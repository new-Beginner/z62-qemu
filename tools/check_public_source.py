# SPDX-License-Identifier: GPL-2.0-or-later
"""Check the exported source, local links and a declared firmware-free test subset.

This is not the historical full-suite/native/firmware acceptance command.
No QEMU firmware run or camera connection is requested by this program.
"""
import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import re
import sys
import unittest
from urllib.parse import unquote

from export_z62_public import SECRET_PATTERNS, scrub

ROOT = Path(__file__).resolve().parents[1]
TEST_MODULES = (
    'test_public_export', 'test_z62_scene_packet', 'test_z62_scene_exchange',
    'test_z62_grid_config', 'test_z62_grid_delivery', 'test_z62_grid_lifecycle',
    'test_z62_media_card', 'test_z62_media_scene', 'test_z62_card_inventory',
    'test_z62_video_job_files', 'test_z62_video_codec', 'test_z62_video_input',
    'test_z62_video_scene', 'test_z62_video_card', 'test_z62_async_video_card',
    'test_z62_async_video_scene', 'test_z62_async_video_job',
    'test_z62_selector_observation', 'test_z62_selector_configuration', 'test_z62_selector_completion',
)
EXCLUDED = {'.git', '.build', '.venv', 'venv', 'artifacts', 'runs', 'third_party', '__pycache__', '.pytest_cache'}
FORBIDDEN = {'.bin', '.exe', '.dll', '.raw', '.img', '.nef', '.mp4', '.mov', '.zip', '.7z', '.xz'}


def files():
    for directory, folders, names in os.walk(ROOT):
        folders[:] = [name for name in folders if name not in EXCLUDED]
        for name in names:
            yield Path(directory)/name


def verify_sources():
    manifest = json.loads((ROOT/'publication-manifest.json').read_text(encoding='utf-8'))
    checked = 0
    for row in manifest['files']:
        data = (ROOT/row['published']).read_bytes()
        if hashlib.sha256(data).hexdigest() != row['published_sha256']:
            raise ValueError('Published export changed: '+row['published'])
        checked += 1
    syntax = 0
    links = []
    for path in files():
        relative = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() in FORBIDDEN:
            raise ValueError('Excluded artifact in public source: '+relative)
        data = path.read_bytes()
        if any(pattern.search(data) for pattern in SECRET_PATTERNS):
            raise ValueError('Credential-shaped data in public source: '+relative)
        if path.suffix == '.py':
            compile(data, relative, 'exec')
            syntax += 1
        if path.suffix == '.md':
            text = data.decode('utf-8-sig')
            text = re.sub(r'```[\s\S]*?```', '', text)
            for target in re.findall(r'!?\[[^\]\n]*\]\(([^)\n]+)\)', text):
                target = target.strip('<>').split('#')[0]
                if not target or target.startswith(('https:', 'http:', 'mailto:')): continue
                resolved = (path.parent/unquote(target)).resolve()
                if not resolved.exists(): links.append({'document': relative, 'target': target})
    if links:
        raise ValueError('Broken local Markdown links: '+json.dumps(links, ensure_ascii=False))
    return {'exported_files_checked': checked, 'python_files_compiled_in_memory': syntax,
            'local_markdown_links_valid': True, 'forbidden_artifacts_found': 0,
            'credential_shapes_found': 0}


def check(output):
    output = Path(output)
    if output.exists() or output.with_suffix('.log').exists():
        raise FileExistsError('Use a new source-check result path')
    result = {'schema': 1, 'snapshot': '2026-11-02-r49', 'completed': False,
              'firmware_loaded': False, 'camera_accessed': False,
              'historical_full_suite_repeated': False, 'test_modules': list(TEST_MODULES)}
    log = io.StringIO()
    try:
        result.update(verify_sources())
        sys.path.insert(0, str(ROOT/'tests'))
        suite = unittest.defaultTestLoader.loadTestsFromNames(TEST_MODULES)
        with redirect_stdout(log), redirect_stderr(log):
            tested = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        result.update(tests=tested.testsRun, failures=len(tested.failures), errors=len(tested.errors),
                      skipped=len(tested.skipped), completed=tested.wasSuccessful() and not tested.skipped)
        result['dependencies'] = {}
        for name in ('numpy', 'Pillow', 'capstone', 'unicorn', 'av', 'rawpy'):
            try: result['dependencies'][name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError: result['dependencies'][name] = None
    except Exception as exc:
        result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.with_suffix('.log').open('x', encoding='utf-8') as handle:
        handle.write(scrub(log.getvalue(), ROOT))
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    result = check(parser.parse_args().output)
    raise SystemExit(0 if result['completed'] else 1)
