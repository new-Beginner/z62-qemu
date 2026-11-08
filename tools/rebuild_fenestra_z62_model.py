# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline, new-identity rebuild of the local Z62 chain; never replace old r69.

prepare and compile are separate, exclusive steps. No firmware is executed here.
A successful build establishes the new source/output relation, not old EXE provenance.
"""
import argparse
import ast
import hashlib
import importlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import build_reference_qemu as reference
import reference_updates
import z62_functional_device as functional
import z62_transaction_device as transaction

ROOT = reference.ROOT
VERSION = 'fenestra-z62-model-rebuild/0.1.2'
PREFIX = 'fenestra-z62-model-r13-'
CHAIN = (
    'capcom', 'raw_stream', 'finite_stats', 'preview', 'capture_contacts',
    'raw_boundary', 'continuous_stats', 'analog_input', 'scene_source', 'scene_file',
    'preview_results', 'preview_results_format', 'grid', 'grid_geometry',
    'photo_results', 'video_isp', 'video_isp_format', 'statistics_observe',
    'raw_stop_control', 'mmio_filter', 'paired_ingress', 'paired_handoff', 'output_lineage',
)
SINGLES = {name: 'nikon-z72.c' for name in
           ('capcom', 'raw_stream', 'capture_contacts', 'raw_boundary')}
SINGLES.update(analog_input='nikon-z72-controller-adc.c',
               scene_file='nikon-z72-input-config.c')
ROOTED = {'mmio_filter', 'paired_ingress', 'paired_handoff', 'output_lineage'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write('\n')


def guard(work, fresh):
    work = Path(work).absolute()
    for part in (work, *work.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError('Linked model workspace')
    if work.parent.resolve() != (ROOT / '.build').resolve() or not work.name.startswith(PREFIX):
        raise ValueError('Choose a direct .build/fenestra-z62-model-r13-* workspace')
    if fresh and work.exists():
        raise ValueError('Existing output is immutable; choose a new workspace')
    if not fresh and not work.is_dir():
        raise ValueError('Prepared workspace missing')
    return work.resolve()


def verify_tree(root, expected):
    actual = reference.tree_hashes(root)
    if actual != expected:
        different = sorted(k for k in actual.keys() | expected.keys()
                           if actual.get(k) != expected.get(k))
        raise ValueError('Frozen tree differs: ' + ', '.join(different[:8]))


def modules():
    return [importlib.import_module('z62_' + name + '_device') for name in CHAIN]


def recipe_files():
    paths = {Path(__file__), Path(reference.__file__), Path(reference.upstream.__file__),
             Path(reference_updates.__file__), Path(functional.__file__), Path(transaction.__file__),
             ROOT / 'qemu/reference-updates/nikon-z62-input-trace.h',
             ROOT / 'tools/z62_reference_features.py', functional.HEADER, transaction.HEADER}
    for module in modules():
        paths.add(Path(module.__file__))
        if hasattr(module, 'HEADER'):
            paths.add(module.HEADER)
        headers = getattr(module, 'HEADERS', ())
        paths.update(headers.values() if isinstance(headers, dict) else headers)
    return {p.relative_to(ROOT).as_posix(): reference.upstream.digest(p) for p in sorted(paths)}


def transaction_body(source):
    """Exact r5 transform body, with new ownership guard at the caller.

    Keep the original fixed INPUTS and every unique replacement. The AST test
    compares the complete body starting at arm=... with the original adapter.
    """
    arm = source / 'hw/arm'
    texts = {}
    for name, digest in transaction.INPUTS.items():
        data = (arm / name).read_bytes()
        if reference_updates.sha(data) != digest:
            raise ValueError('Transaction input SHA mismatch: ' + name)
        texts[name] = data.decode('utf-8')
    replace = reference_updates.replace_once
    text = texts['nikon-z62-sensor-config.c']
    text = replace(text, '#include "qemu/timer.h"', '#include "qemu/timer.h"\n#include "qapi/error.h"')
    text = replace(text, '    uint64_t frame_completions;', '''    uint64_t frame_completions;
    bool functional_raw_completion, raw_dma_level;
    uint64_t raw_source_events, raw_completions, raw_ignored, raw_coalesced;
    uint32_t transaction_reason;''')
    text = replace(text, 'static void sensor_mode2_complete(',
                   '#include "nikon-z62-transaction.h"\n\nstatic void sensor_mode2_complete(')
    text = replace(text, '    s->frame_completions = 0;', '''    s->frame_completions = 0;
    s->raw_dma_level = false;
    s->raw_source_events = s->raw_completions = 0;
    s->raw_ignored = s->raw_coalesced = 0;
    s->transaction_reason = TX_RESET;''')
    text = replace(text, '    .minimum_version_id = 6,', '''    .minimum_version_id = 6,
    .subsections = (const VMStateDescription * const[]) {
        &transaction_vmstate, NULL
    },''')
    text = replace(text, '    qdev_init_gpio_in_named(DEVICE(s), sensor_frame_end, "frame-end", 1);', '''    qdev_init_gpio_in_named(DEVICE(s), sensor_frame_end, "frame-end", 1);
    qdev_init_gpio_in_named(DEVICE(s), sensor_raw_dma_complete, "raw-dma-complete", 1);
    object_property_add_uint64_ptr(obj, "raw-source-events", &s->raw_source_events, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "raw-completions", &s->raw_completions, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "raw-ignored", &s->raw_ignored, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(obj, "raw-coalesced", &s->raw_coalesced, OBJ_PROP_FLAG_READ);
    object_property_add_str(obj, "raw-completion-last-reason", transaction_reason, NULL);''')
    text = replace(text, '    static const Property properties[] = {', '''    static const Property properties[] = {
        DEFINE_PROP_BOOL("functional-raw-completion", Z62SensorConfig,
                         functional_raw_completion, false),''')
    text = replace(text, '    dc->vmsd = &sensor_config_vmstate;',
                   '    dc->vmsd = &sensor_config_vmstate;\n    dc->realize = transaction_realize;')
    board = replace(texts['nikon-z72.c'],
        '        sysbus_realize_and_unref(SYS_BUS_DEVICE(sensor_config), &error_fatal);',
        '        sysbus_realize_and_unref(SYS_BUS_DEVICE(sensor_config), &error_fatal);\n'
        '        qdev_connect_gpio_out_named(input_config, "raw-complete", 0,\n'
        '            qdev_get_gpio_in_named(sensor_config, "raw-dma-complete", 0));')
    (arm / 'nikon-z62-sensor-config.c').write_text(text, encoding='utf-8', newline='\n')
    (arm / 'nikon-z72.c').write_text(board, encoding='utf-8', newline='\n')
    (arm / transaction.HEADER.name).write_bytes(transaction.HEADER.read_bytes())
    return transaction.identity()


def check_transaction_body():
    def body(path, name):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        start = next(i for i, n in enumerate(fn.body) if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'arm' for t in n.targets))
        return '\n'.join(ast.unparse(n) for n in fn.body[start:])
    old = body(Path(transaction.__file__), 'apply_source')
    old = old.replace('INPUTS.items()', 'transaction.INPUTS.items()').replace(
        'reference.sha', 'reference_updates.sha').replace('reference.replace_once',
        'reference_updates.replace_once').replace('HEADER', 'transaction.HEADER').replace(
        'return identity()', 'return transaction.identity()')
    if old != body(Path(__file__), 'transaction_body'):
        raise ValueError('Independent r5 transform differs from original body')


def render_layer(name, module, source):
    root = source if name in ROOTED else source / 'hw/arm'
    inputs = getattr(module, 'INPUTS', None)
    if name == 'preview_results_format':
        inputs = {module.NAME: module.INPUT_SHA}
    elif name in SINGLES and not inputs:
        inputs = {SINGLES[name]: module.INPUT_SHA}
    data = {key: (root / key).read_bytes() for key in inputs}
    for key, digest in inputs.items():
        if sha(data[key]) != digest:
            raise ValueError('Frozen layer input differs: ' + name + '/' + key)
    if name == 'preview_results_format':
        out = {module.NAME: module.HEADER.read_bytes()}
    elif name in SINGLES:
        out = {SINGLES[name]: module.render(data[SINGLES[name]])}
    else:
        out = module.render(data)
    out = {key: value.encode('utf-8') if isinstance(value, str) else value
           for key, value in out.items()}
    # Earlier renderers return modified inputs only; later ones include headers.
    headers = getattr(module, 'HEADERS', ())
    headers = headers.values() if isinstance(headers, dict) else headers
    for header in ([module.HEADER] if hasattr(module, 'HEADER') else []) + list(headers):
        key = ('hw/arm/' if name in ROOTED else '') + header.name
        if key in out and out[key] != header.read_bytes():
            raise ValueError('Renderer/header conflict: ' + name + '/' + key)
        out[key] = header.read_bytes()
    for key, value in out.items():
        target = root / key
        if not target.resolve().is_relative_to(source.resolve()):
            raise ValueError('Renderer output escapes source')
        target.write_bytes(value)
    return {'name': name, 'version': module.VERSION, 'input_sha256': inputs,
            'output_sha256': {str((root / k).relative_to(source).as_posix()): sha(v)
                              for k, v in out.items()}, 'identity': module.identity()}


def prepare_meson_lock(source):
    # Meson DirectoryLock creates this empty host lock in subprojects. Freeze
    # it explicitly so the post-build full-tree comparison needs no exclusions.
    with (source / 'subprojects/.wraplock').open('xb'):
        pass


def prepare(work):
    work = guard(work, True)
    archive = ROOT / '.build/downloads/qemu-10.2.4.tar.xz'
    if reference.upstream.digest(archive) != reference.upstream.ARCHIVE_SHA256:
        raise ValueError('Offline archive differs')
    repo = reference.verify_repository('z62')
    recipe = recipe_files()
    check_transaction_body()
    # Verify the additional Z72 objects exist locally, without any fetch.
    reference_updates.upstream_files()
    if shutil.disk_usage(work.parent).free < 12 * 1024 ** 3:
        raise ValueError('Need 12 GiB for independent model build')
    work.mkdir(exist_ok=False)
    save(work / 'claim.json', {'version': VERSION, 'old_r69_reproduced': False})
    snapshot = work / 'recipe'
    for name in recipe:
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    save(work / 'recipe-sha256.json', recipe)
    donor = work / 'donor'
    donor_hashes = reference.snapshot_donor(repo, donor)
    source = reference.upstream.unpack(archive, work / 'source')
    reference.prepare_source(source, donor)
    reference_updates.apply_source(source)
    functional.apply_source(source)
    transaction_body(source)
    layers = [{'name': 'reference+functional+transaction',
               'identity': [reference.identity('z62', True), functional.identity(), transaction.identity()],
               'output_sha256': {p.relative_to(source).as_posix(): reference.upstream.digest(p)
                                 for p in sorted((source / 'hw/arm').glob('nikon*'))}}]
    save(work / 'layer-00.json', layers[-1])
    for index, (name, module) in enumerate(zip(CHAIN, modules()), 1):
        print('Rendering', index, name, flush=True)
        layer = render_layer(name, module, source)
        save(work / ('layer-%02d.json' % index), layer)
        layers.append(layer)
    if recipe_files() != recipe:
        raise ValueError('Recipe changed during preparation')
    reference.verify_repository('z62')
    prepare_meson_lock(source)
    hashes = reference.tree_hashes(source)
    result = {'version': VERSION, 'model_identity': work.name, 'old_r69_reproduced': False,
              'old_r69_exact_source_recovered': False, 'firmware_executed': False,
              'full_fenestra_port_verified': False, 'flash_safety_verified': False,
              'source': str(source), 'archive_sha256': reference.upstream.ARCHIVE_SHA256,
              'donor_commit': reference.COMMITS['z62'], 'donor_file_sha256': donor_hashes,
              'recipe_sha256': recipe, 'source_sha256': hashes, 'layers': layers,
              'configure': reference.CONFIGURE}
    save(work / 'prepared.json', result)
    print('Prepared source files:', len(hashes), flush=True)
    return result


def scratch_root():
    value = os.environ.get('PI_SCRATCH_DIR')
    if not value or not Path(value).is_dir():
        raise ValueError('An existing PI_SCRATCH_DIR is required')
    return Path(value).resolve()


def build_command(source, build, msys, jobs):
    if not 1 <= jobs <= 32:
        raise ValueError('jobs must be 1..32')
    scratch = scratch_root()
    exports = {'PATH': '/ucrt64/bin:/usr/bin:/c/Windows/System32',
               'TMP': reference.upstream.msys_path(scratch),
               'TEMP': reference.upstream.msys_path(scratch),
               'TMPDIR': reference.upstream.msys_path(scratch),
               'XDG_CACHE_HOME': reference.upstream.msys_path(scratch / 'model-build-cache'),
               'PYTHONDONTWRITEBYTECODE': '1', 'PIP_NO_INDEX': '1',
               'PIP_DISABLE_PIP_VERSION_CHECK': '1'}
    script = 'export ' + ' '.join(k + '=' + shlex.quote(v) for k, v in exports.items())
    script += ' && cd ' + shlex.quote(reference.upstream.msys_path(build))
    script += ' && ' + shlex.quote(reference.upstream.msys_path(source / 'configure'))
    script += ' ' + shlex.join(reference.CONFIGURE)
    script += ' && ninja -j ' + str(jobs) + ' qemu-system-arm.exe'
    env = dict(os.environ, MSYSTEM='UCRT64', CHERE_INVOKING='1', PYTHONUTF8='1',
               PYTHONIOENCODING='utf-8', LANG='C.UTF-8', LC_ALL='C.UTF-8',
               TEMP=str(scratch), TMP=str(scratch), TMPDIR=str(scratch),
               WINDRES=shlex.join(['windres', '--use-temp-file', '-I',
                                  Path(os.path.relpath(source, build)).as_posix()]),
               PATH=str(msys / 'usr/bin') + ';' + os.environ.get('SystemRoot', 'C:/Windows') + '/System32')
    return [str(msys / 'usr/bin/bash.exe'), '--noprofile', '--norc', '-c', script], env


def guard_toolchain_stage(destination):
    destination = Path(destination).absolute()
    if (destination.parent.resolve() != scratch_root() or
            not destination.name.startswith('msys-r13-') or not str(destination).isascii()):
        raise ValueError('Toolchain stage needs an ASCII msys-r13-* direct scratch child')
    for part in (destination, *destination.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError('Linked toolchain stage')
    return destination


def stage_toolchain(destination):
    destination = guard_toolchain_stage(destination)
    if destination.exists():
        raise ValueError('Toolchain stage is immutable; choose a new scratch child')
    original = ROOT / '.runtime/tools/msys64'
    hashes = reference.tree_hashes(original)
    destination.mkdir()
    for index, (name, digest) in enumerate(hashes.items(), 1):
        data = (original / name).read_bytes()
        if sha(data) != digest:
            raise ValueError('Original toolchain changed: ' + name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
        if index % 10000 == 0:
            print('Copied toolchain files:', index, flush=True)
    verify_tree(destination, hashes)
    verify_tree(original, hashes)
    result = {'source': str(original), 'destination': str(destination),
              'file_sha256': hashes, 'source_and_copy_identical': True}
    save(destination.with_name(destination.name + '-copy.json'), result)
    return {'destination': str(destination), 'files': len(hashes), 'source_and_copy_identical': True}


def toolchain_identity(msys):
    if msys.resolve() != (ROOT / '.runtime/tools/msys64').resolve():
        guard_toolchain_stage(msys)
        copied = json.loads(msys.with_name(msys.name + '-copy.json').read_text(encoding='utf-8'))
        verify_tree(msys, copied['file_sha256'])
        verify_tree(ROOT / '.runtime/tools/msys64', copied['file_sha256'])
    roots = ('ucrt64/bin', 'ucrt64/include', 'ucrt64/lib', 'ucrt64/libexec',
             'ucrt64/share/pkgconfig', 'usr/bin', 'usr/lib', 'var/lib/pacman/local')
    hashes = {}
    for name in roots:
        root = msys / name
        if root.exists():
            for key, digest in reference.tree_hashes(root).items():
                hashes[name + '/' + key] = digest
    env = dict(os.environ, PATH=str(msys / 'ucrt64/bin') + ';' + str(msys / 'usr/bin') + ';' +
               os.environ.get('SystemRoot', 'C:/Windows') + '/System32')
    versions = {}
    for tool in ('gcc', 'ninja', 'python', 'pkgconf', 'objdump'):
        result = subprocess.run([str(msys / 'ucrt64/bin' / (tool + '.exe')), '--version'],
                                env=env, capture_output=True, timeout=30, check=True)
        versions[tool] = (result.stdout + result.stderr).decode('utf-8', 'replace')
    return {'root': str(msys), 'file_sha256': hashes, 'versions': versions,
            'coverage_roots': roots, 'complete_toolchain_reproducibility_verified': False}


def compile_model(work, jobs, msys=None):
    work = guard(work, False)
    if (work / 'build').exists() or (work / 'runtime').exists() or (work / 'build-attempt.json').exists():
        raise ValueError('Build attempt is immutable; prepare another new workspace')
    prepared = json.loads((work / 'prepared.json').read_text(encoding='utf-8'))
    if prepared['version'] != VERSION or prepared['model_identity'] != work.name:
        raise ValueError('Wrong prepared model identity')
    if prepared['recipe_sha256'] != recipe_files():
        raise ValueError('Prepared recipe differs from current source')
    verify_tree(work / 'recipe', prepared['recipe_sha256'])
    source = work / 'source/qemu-10.2.4'
    if source.resolve() != Path(prepared['source']).resolve():
        raise ValueError('Prepared source path differs')
    verify_tree(source, prepared['source_sha256'])
    msys = Path(msys) if msys else ROOT / '.runtime/tools/msys64'
    tools = toolchain_identity(msys)
    save(work / 'toolchain-current.json', tools)
    build = work / 'build'
    cmd, env = build_command(source, build, msys, jobs)
    save(work / 'build-attempt.json', {'command': cmd, 'jobs': jobs, 'version': VERSION,
                                     'temporary_root': str(scratch_root())})
    build.mkdir()
    try:
        with (work / 'compile.log').open('xb') as log:
            subprocess.run(cmd, env=env, cwd=work, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=1800)
        reference.verify_devices(build)
        runtime = work / 'runtime'
        runtime.mkdir()
        binary = build / 'qemu-system-arm.exe'
        dlls = reference.upstream.stage_windows(binary, msys, runtime)
        checks = reference.smoke_checks(runtime / binary.name, 'z62')
        verify_tree(source, prepared['source_sha256'])
        if recipe_files() != prepared['recipe_sha256']:
            raise ValueError('Recipe changed during compilation')
        if toolchain_identity(msys) != tools:
            raise ValueError('Toolchain changed during compilation')
        result = {'version': VERSION, 'model_identity': work.name,
                  'old_r69_reproduced': False, 'old_r69_exact_source_recovered': False,
                  'binary': str(runtime / binary.name), 'binary_sha256': reference.upstream.digest(binary),
                  'runtime_dll_sha256': dlls, 'checks': checks,
                  'prepared_sha256': reference.upstream.digest(work / 'prepared.json'),
                  'toolchain_sha256': reference.upstream.digest(work / 'toolchain-current.json'),
                  'firmware_executed': False, 'full_fenestra_port_verified': False,
                  'flash_safety_verified': False, 'physical_camera_accessed': False}
        save(work / 'model-build.json', result)
        return result
    except Exception as exc:
        save(work / 'build-failure.json', {'type': type(exc).__name__, 'error': str(exc),
                                          'complete_build': False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'compile', 'stage-toolchain'))
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=8)
    parser.add_argument('--msys', type=Path)
    args = parser.parse_args()
    if args.action == 'stage-toolchain':
        result = stage_toolchain(args.work)
    elif args.action == 'prepare':
        result = prepare(args.work)
    else:
        result = compile_model(args.work, args.jobs, args.msys)
    print(json.dumps({k: v for k, v in result.items() if k not in ('source_sha256', 'layers')},
                     indent=2), flush=True)


if __name__ == '__main__':
    main()
