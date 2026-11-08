"""Build only no-firmware Fenestra loader probes. Never creates Nikon images."""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

from pack import VERSION, UPSTREAM, FIRMWARE, digest, make_package, cases, fixtures_header

ROOT = Path(__file__).resolve().parents[2]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def elf_symbols(data):
    require(data[:7] == b'\x7fELF\x01\x01\x01', 'Expected ELF32 little endian')
    require(struct.unpack_from('<H', data, 18)[0] == 40, 'Expected EM_ARM')
    offset = struct.unpack_from('<I', data, 32)[0]
    entry_size, count = struct.unpack_from('<2H', data, 46)
    require(entry_size == 40 and offset + count * 40 <= len(data), 'Invalid ELF section table')
    sections = [struct.unpack_from('<10I', data, offset + i * 40) for i in range(count)]
    symbols = {}
    for section in sections:
        if section[1] != 2:
            continue
        require(section[9] == 16 and section[6] < count, 'Invalid ELF symbols')
        strings_section = sections[section[6]]
        strings = data[strings_section[4]:strings_section[4] + strings_section[5]]
        require(section[4] + section[5] <= len(data), 'Truncated ELF symbols')
        for p in range(section[4], section[4] + section[5], 16):
            name, value, _, _, _, index = struct.unpack_from('<IIIBBH', data, p)
            require(name < len(strings), 'Invalid ELF symbol name')
            if index:
                end = strings.find(b'\0', name)
                require(end >= name, 'Unterminated ELF symbol')
                symbols[strings[name:end].decode('ascii')] = value
    return symbols


def build(output, zig):
    alias = Path('Q:/')
    require(alias.is_dir() and alias.samefile(ROOT), 'Verified ASCII workspace alias Q: is required')
    target = (ROOT / output).resolve() if not output.is_absolute() else output.resolve()
    require(target.is_relative_to(ROOT / '.build') and not target.exists(), 'Use a new directory under project .build')
    out = alias / target.relative_to(ROOT)
    source = alias / 'fenestra/z62'
    upstream = alias / 'fenestra/upstream'
    original = ROOT / 'artifacts/z62-reference-1.70/master.bin'
    require(digest(original.read_bytes()) == FIRMWARE, 'Original C1.70 master identity mismatch')
    head = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    require(head == UPSTREAM, 'Fenestra base identity mismatch')
    zig = zig.resolve()
    require(zig.is_file() and str(zig).isascii(), 'Zig path must be an existing ASCII path')
    gcc = alias / '.runtime/tools/msys64/ucrt64/bin/gcc.exe'
    require(gcc.is_file(), 'Project native GCC is required')
    scratch = Path(os.environ['PI_SCRATCH_DIR'])
    env = dict(os.environ, TEMP=str(scratch), TMP=str(scratch), TMPDIR=str(scratch),
               ZIG_GLOBAL_CACHE_DIR=str(scratch / 'zig-cache'),
               ZIG_LOCAL_CACHE_DIR=str(scratch / 'zig-local'), PYTHONDONTWRITEBYTECODE='1',
               PATH=str(gcc.parent) + os.pathsep + os.environ.get('PATH', ''))
    out.mkdir(parents=True)
    record = dict(version=VERSION, upstream=UPSTREAM, completed=False, commands=[],
                  firmware_identity=FIRMWARE.hex(), firmware_loaded=False,
                  firmware_integrated=False, flash_safety_verified=False)

    def run(command):
        command = list(map(str, command))
        result = subprocess.run(command, cwd=out, env=env, capture_output=True, timeout=180)
        item = dict(command=command, exit_code=result.returncode,
                    stdout=result.stdout.decode('utf-8', 'backslashreplace'),
                    stderr=result.stderr.decode('utf-8', 'backslashreplace'))
        record['commands'].append(item)
        if result.returncode:
            raise RuntimeError(json.dumps(item, ensure_ascii=False))
        return item['stdout']

    try:
        record['zig_version'] = run([zig, 'version']).strip()
        require(record['zig_version'] == '0.13.0', 'Pinned Zig 0.13.0 required')
        cc = [zig, 'cc', '-target', 'arm-freestanding-eabi', '-mcpu=cortex_a7',
              '-mfloat-abi=soft', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
              '-fno-unwind-tables', '-nostdlib', '-O2', '-Wall', '-Wextra', '-Werror',
              '-Wl,--build-id=none']
        run(cc + [source / 'module.S', '-Wl,-e,fenestra_module_entry', '-Wl,-T,' + str(source / 'module.ld'), '-o', out / 'module.elf'])
        run([zig, 'objcopy', '-O', 'binary', out / 'module.elf', out / 'module.bin'])
        symbols = elf_symbols((out / 'module.elf').read_bytes())
        code = (out / 'module.bin').read_bytes()
        entry = symbols['fenestra_module_entry'] & ~1
        require(entry == 2 and symbols['module_helper'] & 1, 'Thumb symbol state/alignment mismatch')
        package = make_package(code, entry, symbols['module_message'], symbols['module_helper'])
        (out / f'fenestra-z62-{VERSION}.wlm').write_bytes(package)
        record.update(module_symbols=symbols, fixture_names=[row[0] for row in cases(package)],
                      package_sha256=digest(package).hex())
        (out / 'fixtures.h').write_text(fixtures_header(package), encoding='ascii')
        common = [upstream / ('src/' + f) for f in ('sha256.c', 'memory.c')]
        # The Zig 0.13 driver mixes ARMv4 frontend defaults with A7 feature overrides.
        # Pin a coherent integer-only Thumb-v7 frontend instead of weakening hashing.
        frontend = [zig, '-cc1', '-triple', 'thumbv7-none-eabi', '-target-cpu', 'cortex-a7',
                    '-target-abi', 'aapcs', '-mfloat-abi', 'soft', '-msoft-float',
                    '-target-feature', '+soft-float', '-target-feature', '+soft-float-abi',
                    '-target-feature', '-neon', '-target-feature', '-fpregs',
                    '-target-feature', '+strict-align',
                    '-ffreestanding', '-fno-builtin', '-internal-isystem', zig.parent / 'lib/include',
                    '-DFX_FREESTANDING', '-DFX_TARGET_ARMV7_THUMB_EXPERIMENTAL',
                    '-I', upstream / 'include', '-I', out, '-emit-obj', '-O2', '-Wall', '-Wextra', '-Werror']
        objects = []
        for file in [source / 'probe.c', source / 'aeabi.c', upstream / 'src/module.c', *common]:
            obj = out / (file.stem + '.o')
            run(frontend + [file, '-o', obj])
            objects.append(obj)
        run(cc + [source / 'start.S', *objects, '-Wl,-T,' + str(source / 'probe.ld'),
                  '-o', out / 'probe.elf'])
        run([zig, 'objcopy', '-O', 'binary', out / 'probe.elf', out / 'probe.bin'])
        # Default branch versus the unmodified original, format only; no A64 execution.
        native = out / 'native'
        native.mkdir()
        package64 = make_package(code, 0, symbols['module_message'], symbols['module_helper'], bits=64)
        (native / 'fixtures.h').write_text(fixtures_header(package64, bits=64), encoding='ascii')
        original_source = subprocess.check_output(['git', '-C', str(upstream), 'show', UPSTREAM + ':src/module.c'])
        (native / 'original_module.c').write_bytes(original_source)
        record['native_format'] = {}
        for label, loader in (('original', native / 'original_module.c'), ('ported_default', upstream / 'src/module.c')):
            exe = native / (label + '.exe')
            run([gcc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-static',
                 '-DFX_NATIVE_FORMAT_TEST', '-I', upstream / 'include', '-I', native,
                 source / 'probe.c', loader, *common, '-o', exe])
            record['native_format'][label] = json.loads(run([exe]))
        require(record['native_format']['original'] == record['native_format']['ported_default'],
                'Default AArch64 format behavior differs from upstream')
        record['source_sha256'] = {}
        for p in [*source.glob('*.py'), *source.glob('*.c'), *source.glob('*.S'), *source.glob('*.ld'),
                  upstream / 'src/module.c', *common, upstream / 'include/fenestra_module.h',
                  upstream / 'include/fenestra.h', upstream / 'include/fenestra_memory.h',
                  upstream / 'include/fenestra_api.h', upstream / 'include/fenestra_sha256.h']:
            record['source_sha256'][p.relative_to(alias).as_posix()] = digest(p.read_bytes()).hex()
        record['artifact_sha256'] = {p.relative_to(out).as_posix(): digest(p.read_bytes()).hex()
                                    for p in out.rglob('*') if p.is_file()}
        record['completed'] = True
        print(json.dumps({k:record[k] for k in ('version','completed','module_symbols','native_format')}, indent=2))
    finally:
        (out / 'build.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--zig', type=Path, required=True)
    args = parser.parse_args()
    build(args.output, args.zig)
