"""Run pinned portable Ghidra on selected original Z62 Thumb functions.

Creates a separate analysis database and exports pseudocode. Never executes or
modifies firmware. Generated pseudocode is evidence to check, not a hardware spec.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from prepare_reference_firmware import ROOT, PROFILES
from setup_ghidra import TOOLS, SHA256

DEFAULT_FUNCTIONS = (0x1023C38A, 0x102384CA, 0x1020C8BE, 0x1020C8F0,
    0x10238A80, 0x1023831E, 0x1023C4FC, 0x1026E662, 0x10238FF2,
    0x10239128, 0x102392B8, 0x1020AEA8, 0x1020AF08, 0x1020B130)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_exports(output, functions):
    """Catch unusable exports; passing is not a claim of semantic correctness."""
    issues = []
    for address in functions:
        name = f'{address & ~1:x}'
        code, listing = output/(name+'.c'), output/(name+'.asm')
        if not code.is_file() or not listing.is_file():
            issues.append({'function': name, 'issue': 'missing pseudocode or instruction listing'})
            continue
        text = code.read_text(encoding='utf-8')
        for marker in ('halt_baddata', 'Control flow encountered bad instruction',
                       'Could not recover jumptable', 'Possible PIC construction', 'BADSPACEBASE'):
            if marker in text:
                issues.append({'function': name, 'issue': marker})
    return {'exports_checked': len(functions), 'issues': issues,
            'all_exports_structurally_usable': not issues,
            'semantics_verified': False}


def run(args):
    role = getattr(args, 'role', 'master')
    image = ROOT/f'artifacts/z62-reference-1.70/{role}.bin'
    member = 'eg1850_mas_01700' if role == 'master' else 'ex1850_012000.bi'
    expected = PROFILES['z62']['members'][member][2]
    if sha(image) != expected:
        raise ValueError('Original C1.70 image identity mismatch')
    locator = TOOLS/'ghidra-ascii.json'
    if not locator.is_file():
        locator = TOOLS/'ghidra-11.4.2/installation.json'
    installation = json.loads(locator.read_text(encoding='utf-8'))
    if installation['archive_sha256'] != SHA256:
        raise ValueError('Portable analysis tool identity mismatch')
    headless = Path(installation['headless'])
    if not headless.is_file() or not (args.java_home/'bin/java.exe').is_file():
        raise ValueError('Verified headless launcher or Java 21 is missing')
    args.output.mkdir(parents=True, exist_ok=False)
    work = Path(tempfile.mkdtemp(prefix='z62-ghidra-', dir=os.environ.get('PI_SCRATCH_DIR')))
    if not str(work).isascii():
        raise ValueError('Headless working directory must be ASCII')
    script = ROOT/'tools/ghidra/ExportZ62Functions.java'
    (work/'scripts').mkdir()
    shutil.copyfile(script, work/'scripts'/script.name)
    staged = work/(role+'.bin')
    shutil.copyfile(image, staged)
    exports = work/'exports'
    exports.mkdir()
    project = work/'project'
    project.mkdir()
    functions = args.functions or DEFAULT_FUNCTIONS
    command = [str(headless), str(project), 'Z62C170', '-import', str(staged),
        '-loader', 'BinaryLoader', '-processor', 'ARM:LE:32:v7', '-cspec', 'default',
        '-noanalysis', '-scriptPath', str(work/'scripts'), '-postScript', script.name,
        str(exports), 'base:' + ('10020000' if role == 'master' else '08000000'),
        *[hex(address) for address in functions]]
    env = dict(os.environ, JAVA_HOME=str(args.java_home), PYTHONUTF8='1')
    record = {'tool': installation, 'input_sha256': expected, 'script_sha256': sha(script),
              'work': str(work), 'functions': [hex(a) for a in functions],
              'command': command, 'module_role': role,
              'firmware_executed': False, 'completed': False}
    print('Headless workspace:', work, flush=True)
    with (args.output/'headless.log').open('xb') as log:
        result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
    record['exit_code'] = result.returncode
    record['original_unchanged'] = sha(image) == expected and sha(staged) == expected
    for path in exports.iterdir():
        if path.is_file():
            shutil.copyfile(path, args.output/path.name)
    record['completed'] = (result.returncode == 0 and record['original_unchanged'] and
                           (args.output/'functions.tsv').is_file())
    record['export_audit'] = audit_exports(args.output, functions)
    (args.output/'manifest.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps({key: record[key] for key in ('completed', 'exit_code', 'original_unchanged')}))
    return record


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--java-home', type=Path, default=Path('D:/java'))
    p.add_argument('--functions', type=lambda x: int(x, 16), nargs='+')
    p.add_argument('--role', choices=('master', 'controller'), default='master')
    args = p.parse_args()
    low, high = (0x10020000, 0x12400000) if args.role == 'master' else (0x08000000, 0x08080000)
    if args.role == 'controller' and not args.functions:
        p.error('Controller analysis requires explicit independently located functions')
    if args.functions and any(not low <= value < high for value in args.functions):
        p.error('Functions must be within the mapped original module')
    raise SystemExit(0 if run(args)['completed'] else 1)
