# SPDX-License-Identifier: GPL-2.0-or-later
"""Reconstruct hash-bound source fixtures, not historical complete build trees.

The legacy test adapter changes only exact source-fixture reads. All assertions,
source render guards and writes remain unchanged. Never creates old build paths.
"""
import argparse
import hashlib
import importlib
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import unittest
from unittest.mock import patch

import rebuild_fenestra_z62_model as model

ROOT = model.ROOT
VERSION = 'z62-reconstructed-fixtures/0.1.0'
MODEL = ROOT / '.build/fenestra-z62-model-r13-03'
HISTORICAL = {
    'capcom': 'z62-transaction-2026.10.28-r5',
    'raw_stream': 'z62-capcom-2026.10.28-r6',
    'finite_stats': 'z62-raw-stream-2026.10.29-r7',
    'preview': 'z62-finite-stats-2026.10.29-r8',
    'grid': 'z62-preview-results-format-2026.11.02-r47b',
    'grid_geometry': 'z62-grid-2026.11.02-r48',
    'photo_results': 'z62-grid-geometry-2026.11.03-r52',
    'video_isp': 'z62-photo-results-2026.11.03-r53',
}
TESTS = ('capcom', 'raw_stream', 'finite_stats', 'preview', 'capture_contacts',
         'grid_device', 'grid_geometry', 'photo_results', 'video_isp', 'paired_ingress')


def guard(work):
    work = Path(work).absolute()
    if (work.parent.resolve() != (ROOT / '.build').resolve() or
            not work.name.startswith('fenestra-z62-fixtures-r14-') or work.exists()):
        raise ValueError('Use a new direct .build/fenestra-z62-fixtures-r14-* output')
    for part in (work, *work.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError('Linked fixture workspace')
    return work.resolve()


def dependencies():
    """Include all file-valued exported C/header constants, not just HEADER(S)."""
    result = model.recipe_files()
    result[Path(__file__).relative_to(ROOT).as_posix()] = model.reference.upstream.digest(Path(__file__))
    for module in [model.functional, model.transaction, *model.modules()]:
        for name, value in vars(module).items():
            if isinstance(value, Path) and value.is_file() and value.suffix in ('.c', '.h'):
                if not value.resolve().is_relative_to(ROOT.resolve()):
                    raise ValueError('Adapter source dependency escapes project: ' + name)
                result[value.relative_to(ROOT).as_posix()] = model.reference.upstream.digest(value)
    return result


def layer_inputs(name, module, source):
    inputs = getattr(module, 'INPUTS', None)
    root = source if name in model.ROOTED else source / 'hw/arm'
    if name == 'preview_results_format':
        inputs = {module.NAME: module.INPUT_SHA}
    elif name in model.SINGLES and not inputs:
        inputs = {model.SINGLES[name]: module.INPUT_SHA}
    result = {}
    for key, digest in inputs.items():
        data = (root / key).read_bytes()
        if model.sha(data) != digest:
            raise ValueError('Reconstructed fixture differs from frozen input: ' + name + '/' + key)
        relative = (root / key).relative_to(source).as_posix()
        result[relative] = (data, digest)
    return result


def create(work):
    work = guard(work)
    prepared = json.loads((MODEL / 'prepared.json').read_text(encoding='utf-8'))
    if model.recipe_files() != prepared['recipe_sha256']:
        raise ValueError('Original r13 recipe changed')
    before = dependencies()
    pixel = ROOT / 'qemu/z62-mode-geometry/nikon-z62-mode-grid-pixels.h'
    if model.reference.upstream.digest(pixel) != prepared['source_sha256']['hw/arm/' + pixel.name]:
        raise ValueError('Additional PIXELS dependency differs from compiled source')
    # Verify only the explicitly bound donor snapshot; this is not a full build.
    model.verify_tree(MODEL / 'donor', prepared['donor_file_sha256'])
    archive = ROOT / '.build/downloads/qemu-10.2.4.tar.xz'
    if model.reference.upstream.digest(archive) != model.reference.upstream.ARCHIVE_SHA256:
        raise ValueError('Offline archive differs')
    model.reference.verify_repository('z62')
    work.mkdir()
    model.save(work / 'claim.json', {'version': VERSION, 'complete_qemu_tree': False,
                                    'old_build_trees_restored': False, 'old_r69_reproduced': False})
    source = work / 'working'
    arm = source / 'hw/arm'
    arm.mkdir(parents=True)
    # Minimal donor fixture: real C/H files, not executable preparation helpers.
    for original in (MODEL / 'donor/qemu').iterdir():
        if original.suffix in ('.c', '.h'):
            shutil.copyfile(original, arm / original.name)
    board = arm / 'nikon-z72.c'
    board.write_bytes(model.reference.compatible_board(board.read_bytes()))
    needed = {'hw/arm/meson.build', 'system/memory.c', 'system/trace-events'}
    archive_files = {}
    with tarfile.open(archive, 'r|xz') as stream:
        for member in stream:
            relative = member.name.removeprefix('qemu-10.2.4/')
            if relative in needed:
                if not member.isfile():
                    raise ValueError('Unexpected primitive source type')
                data = stream.extractfile(member).read()
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as handle:
                    handle.write(data)
                archive_files[relative] = model.sha(data)
    if set(archive_files) != needed:
        raise ValueError('Missing archive source primitive')
    model.reference_updates.apply_source(source)
    model.functional.apply_source(source)
    model.transaction_body(source)
    fixtures = {}
    generated = set()
    for name, module in zip(model.CHAIN, model.modules()):
        inputs = layer_inputs(name, module, source)
        rows = {}
        for relative, (data, digest) in inputs.items():
            target = work / 'inputs' / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as handle:
                handle.write(data)
            rows[relative] = {'path': target.relative_to(work).as_posix(), 'sha256': digest}
        fixtures[name] = rows
        layer = model.render_layer(name, module, source)
        generated.update(layer['output_sha256'])
    # Every final affected file must equal the source used for the actual r13 EXE.
    for relative in generated:
        if model.reference.upstream.digest(source / relative) != prepared['source_sha256'][relative]:
            raise ValueError('Final fixture chain differs from compiled r13: ' + relative)
    if dependencies() != before:
        raise ValueError('Fixture dependencies changed during reconstruction')
    result = {'version': VERSION, 'work': str(work), 'fixtures': fixtures,
              'dependencies_sha256': before, 'archive_files_sha256': archive_files,
              'r13_prepared_sha256': model.reference.upstream.digest(MODEL / 'prepared.json'),
              'final_generated_source_files_verified': len(generated),
              'source_tree_is_complete_qemu': False, 'old_build_trees_restored': False,
              'old_r69_reproduced': False,
              'additional_pixel_header_matches_r13_generated_source': True}
    model.save(work / 'fixture-manifest.json', result)
    return result


def read_mapping(work):
    work = Path(work).resolve()
    manifest = json.loads((work / 'fixture-manifest.json').read_text(encoding='utf-8'))
    if manifest['version'] != VERSION or manifest['dependencies_sha256'] != dependencies():
        raise ValueError('Fixture identity changed')
    result = {}
    for layer, historical in HISTORICAL.items():
        for relative, row in manifest['fixtures'][layer].items():
            original = ROOT / '.build' / historical / 'source/qemu-10.2.4' / relative
            fixture = work / row['path']
            if not fixture.resolve().is_relative_to(work) or model.reference.upstream.digest(fixture) != row['sha256']:
                raise ValueError('Fixture read escaped or changed')
            result[original.absolute()] = (fixture, row['sha256'])
    return result


def run_tests(work, output):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / 'analysis/fenestra-z62-model-r14') or output.exists():
        raise ValueError('Use new r14 test output')
    mapping = read_mapping(work)
    source = Path.read_bytes
    reads = []
    def fixture_read(path):
        key = path.absolute()
        if key not in mapping:
            return source(path)
        fixture, digest = mapping[key]
        data = source(fixture)
        if model.sha(data) != digest:
            raise ValueError('Fixture changed during test')
        reads.append({'historical_request': str(path), 'new_fixture': str(fixture), 'sha256': digest})
        return data
    sys.path.insert(0, str(ROOT / 'tests'))
    modules = [importlib.import_module('test_z62_' + name) for name in TESTS]
    test_sources = {Path(m.__file__).relative_to(ROOT).as_posix(): source(Path(m.__file__)) for m in modules}
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m) for m in modules)
    log = io.StringIO()
    with patch.object(Path, 'read_bytes', new=fixture_read):
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    if set(test_sources) != {Path(m.__file__).relative_to(ROOT).as_posix() for m in modules}:
        raise ValueError('Test sources changed')
    for name, data in test_sources.items():
        if source(ROOT / name) != data:
            raise ValueError('Legacy test source changed')
    record = {'version': VERSION, 'original_test_assertions_unchanged': True,
              'input_mode': 'explicit hash-verified reconstructed source fixtures; not old complete build trees',
              'test_sources_sha256': {name: model.sha(data) for name, data in test_sources.items()},
              'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': len(result.skipped), 'fixture_reads': reads, 'log': log.getvalue(),
              'fixture_manifest_sha256': model.reference.upstream.digest(Path(work) / 'fixture-manifest.json'),
              'old_build_trees_restored': False, 'old_r69_reproduced': False}
    model.save(output, record)
    print(log.getvalue(), flush=True)
    if not result.wasSuccessful() or result.skipped:
        raise ValueError('Legacy assertions failed with reconstructed fixtures')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('create', 'test'))
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'create':
        record = create(args.work)
        print('Frozen fixture layers:', len(record['fixtures']), flush=True)
    else:
        if args.output is None:
            parser.error('test requires --output')
        run_tests(args.work, args.output)
