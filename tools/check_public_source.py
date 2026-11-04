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
import subprocess
import sys
import tempfile
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
    'test_z62_paired_camera', 'test_z62_committed_controls_js',
    'test_z62_action_queue', 'test_z62_action_evidence',
    'test_z62_capture_submit', 'test_z62_capture_submit_evidence',
    'test_z62_prepare_packet', 'test_z62_prepare_control', 'test_z62_prepare_control_evidence',
    'test_z62_input_counters', 'test_z62_kernel_event_layout', 'test_z62_kernel_event_frames',
    'test_z62_capturework_original',
    'test_z62_group_parameter_input', 'test_z62_original_clock_guard',
)
EXCLUDED = {'.git', '.build', '.runtime', '.venv', 'venv', 'artifacts', 'runs', 'third_party', '__pycache__', '.pytest_cache'}
FORBIDDEN = {'.bin', '.exe', '.dll', '.raw', '.p12', '.p14', '.p16', '.img', '.nef', '.mp4', '.mov', '.zip', '.7z', '.xz'}


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


def check_native(compiler):
    """Compile only exported C sources; no private manifest or firmware is needed."""
    root = Path.cwd()
    if not root.samefile(ROOT) or not str(root).isascii():
        raise ValueError('Run from the public checkout using its ASCII path or verified ASCII alias')
    compiler = Path(compiler).absolute()
    if not compiler.is_file():
        raise FileNotFoundError('Explicit local GCC is required')
    base = root/'.runtime/tmp'
    base.mkdir(parents=True, exist_ok=True)
    if not base.resolve().is_relative_to(ROOT):
        raise ValueError('Native build output must remain inside the checkout')
    env = dict(os.environ, TEMP=str(base), TMP=str(base), TMPDIR=str(base), LANG='C', LC_ALL='C',
               PATH=str(compiler.parent)+os.pathsep+os.environ.get('PATH', ''))
    from PIL import Image
    from z62_main_frame import make_packet
    from z62_raw_transfer import RawTransfer
    sources = ('nikon-z62-capturework-pixels.h', 'nikon-z62-main-source.h',
               'nikon-z62-raw-transfer.h')
    probes = ('z62_capturework_pixels_probe.c', 'z62_main_source_probe.c', 'z62_raw_transfer_probe.c')
    result = {'completed': False, 'firmware_loaded': False, 'qemu_started': False,
              'cases': [], 'source_sha256': {name: hashlib.sha256((root/name).read_bytes()).hexdigest()
                  for name in (*('qemu/z62-capturework/'+n for n in sources),
                               *('tests/native/'+n for n in probes))}}
    with tempfile.TemporaryDirectory(prefix='public-capturework-', dir=base) as directory:
        executable = Path(directory)/('capturework.exe' if os.name == 'nt' else 'capturework')
        command = [str(compiler), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
                   '-I', str(root/'qemu/z62-capturework'),
                   str(root/'tests/native/z62_capturework_pixels_probe.c'), '-o', str(executable)]
        built = subprocess.run(command, env=env, cwd=directory, capture_output=True, timeout=60)
        result['compile'] = {'returncode': built.returncode,
            'stdout': built.stdout.decode('utf-8', 'backslashreplace'),
            'stderr': built.stderr.decode('utf-8', 'backslashreplace'),
            'stderr_sha256': hashlib.sha256(built.stderr).hexdigest()}
        if built.returncode:
            return result
        result['executable_sha256'] = hashlib.sha256(executable.read_bytes()).hexdigest()
        version = subprocess.run([str(compiler), '--version'], env=env, capture_output=True,
                                 timeout=15, check=True)
        result['compiler_version'] = version.stdout.decode('utf-8', 'backslashreplace').splitlines()[0]
        for case in ('raw12', 'raw14', 'raw16', 'rational-mono', 'rational-cfa', 'lookup', 'padding', 'rejects'):
            ran = subprocess.run([str(executable), case], env=env, cwd=directory,
                                 capture_output=True, timeout=60)
            row = {'case': case, 'returncode': ran.returncode,
                   'stdout': ran.stdout.decode('utf-8', 'backslashreplace'),
                   'stderr': ran.stderr.decode('utf-8', 'backslashreplace')}
            try:
                data = json.loads(ran.stdout)
                row['completed'] = ran.returncode == 0 and data.get('completed') is True and data.get('case') == case
            except (ValueError, UnicodeError):
                row['completed'] = False
            result['cases'].append(row)
        result['completed'] = all(row['completed'] for row in result['cases'])
        packet = Path(directory)/'main.z62m'
        packet.write_bytes(make_packet(Image.new('RGB', (7, 5), (255, 128, 0)),
            width=14, height=10, stride=32, epoch=62, publish_id=1,
            frame_id=1, virtual_time_ns=33_333_334))
        # Exercise the actual published C parsers/lifecycles. No private build lock.
        for label, probe in (('main', probes[1]), ('transfer', probes[2])):
            binary = Path(directory)/(label+('.exe' if os.name == 'nt' else ''))
            command = [str(compiler), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
                       '-I', str(root/'qemu/z62-capturework'),
                       str(root/'tests/native'/probe), '-o', str(binary)]
            built = subprocess.run(command, env=env, cwd=directory, capture_output=True, timeout=60)
            result[label+'_compile'] = {'returncode': built.returncode,
                'stderr': built.stderr.decode('utf-8', 'backslashreplace')}
            if built.returncode:
                result['completed'] = False
                return result
            if label == 'main':
                cases = [(case, [case, str(packet)]) for case in ('parse', 'lifecycle', 'rejects')]
            else:
                cases = []
                for bits, codec, case in ((12, 'shift', 'roundtrip'), (14, 'shift', 'roundtrip'),
                        (16, 'shift', 'roundtrip'), (12, 'lookup8-high-byte', 'roundtrip'),
                        (12, 'lookup8-high-byte', 'rejects')):
                    descriptor = Path(directory)/(str(bits)+'-'+codec+'.z62t')
                    lut = tuple(16+i*4 for i in range(256)) if codec == 'lookup8-high-byte' else ()
                    descriptor.write_bytes(RawTransfer(bits, codec, lut).to_bytes())
                    cases.append((str(bits)+'-'+codec+'-'+case, [case, str(descriptor)]))
            for case, arguments in cases:
                ran = subprocess.run([str(binary), *arguments], env=env, cwd=directory,
                                     capture_output=True, timeout=60)
                row = {'case': label+'-'+case, 'returncode': ran.returncode,
                    'stdout': ran.stdout.decode('utf-8', 'backslashreplace'),
                    'stderr': ran.stderr.decode('utf-8', 'backslashreplace')}
                try:
                    row['completed'] = ran.returncode == 0 and json.loads(ran.stdout).get('completed') is True
                except (ValueError, UnicodeError):
                    row['completed'] = False
                result['cases'].append(row)
        result['completed'] = all(row['completed'] for row in result['cases'])
    return result


def check(output, native_compiler=None):
    output = Path(output)
    if output.exists() or output.with_suffix('.log').exists():
        raise FileExistsError('Use a new source-check result path')
    result = {'schema': 1, 'snapshot': '2026.11.04-r103', 'completed': False,
              'firmware_loaded': False, 'camera_accessed': False,
              'historical_full_suite_repeated': False, 'test_modules': list(TEST_MODULES),
              'native_requested': native_compiler is not None}
    log = io.StringIO()
    try:
        result.update(verify_sources())
        sys.path.insert(0, str(ROOT/'tests'))
        suite = unittest.defaultTestLoader.loadTestsFromNames(TEST_MODULES)
        with redirect_stdout(log), redirect_stderr(log):
            tested = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        result.update(tests=tested.testsRun, failures=len(tested.failures), errors=len(tested.errors),
                      skipped=len(tested.skipped), completed=tested.wasSuccessful() and not tested.skipped)
        if native_compiler is not None:
            result['native_capturework'] = check_native(native_compiler)
            result['completed'] = result['completed'] and result['native_capturework']['completed']
        result['dependencies'] = {}
        for name in ('numpy', 'Pillow', 'capstone', 'unicorn', 'av', 'rawpy'):
            try: result['dependencies'][name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError: result['dependencies'][name] = None
    except Exception as exc:
        result['completed'] = False
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
    parser.add_argument('--native-compiler', type=Path)
    args = parser.parse_args()
    result = check(args.output, args.native_compiler)
    raise SystemExit(0 if result['completed'] else 1)
