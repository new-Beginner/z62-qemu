# SPDX-License-Identifier: GPL-2.0-or-later
"""Prepare the isolated public checkout; never stage, commit, push or run firmware.

Extends the historical r104 exporter with ARM32 research source and selected
verification summaries. Private workspace paths are redacted in public copies,
including source literals; original and public hashes remain in the ledger.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import export_z62_public as base
import refresh_z62_public_snapshot as previous

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = '2026.11.08-r110-fenestra-r19'
UPSTREAM = 'b199dcdfbb0ef536c6269ae5a9d97c376d488b8b'
SUMMARIES = {
    **{f'cw-recovery-r{stage}.json': f'analysis/{directory}/verification-1/result.json'
       for stage, directory in (
           (105, 'z62-cw-preview-recovery-r105'), (106, 'z62-cw-reentry-r106'),
           (107, 'z62-cw-reentry-r107'), (108, 'z62-cw-app-transition-r108'),
           (109, 'z62-applv-reentry-r109'))},
    'request-qualification-r110.json': 'analysis/z62-request-qualification-r110/publication-verification-20261108-1/result.json',
    'fenestra-loader-r1.json': 'analysis/fenestra-z62-r1/verification-round2.json',
    'fenestra-task-chain-r17.json': 'analysis/fenestra-z62-task-chain-r17/verification-final.json',
    'fenestra-business-prefix-r18.json': 'analysis/fenestra-z62-business-r18/prefix-verification-final.json',
    'fenestra-queue-r19.json': 'analysis/fenestra-z62-queue-r19/verification-final.json',
}


def public_text(text, root):
    text = base.scrub(text, root)
    if root.drive:
        wsl = '/mnt/' + root.drive[0].lower() + '/' + root.as_posix()[3:]
        text = text.replace(wsl, '<WORKSPACE>')
    # A personal address must not remain even in the old scrubber's source.
    text = re.sub(r'[0-9]{5,}@qq[.]com', 'redacted@example.invalid', text)
    # Historical personal prefixes, including corrupted workspace spellings.
    profile = ''.join(('320', '57'))
    for separator in ('/', chr(92)):
        for spelling in (separator, separator * 2):
            prefix = 'D:' + spelling + profile + spelling
            text = text.replace(prefix, '<PROJECTS>' + spelling)
            scratch = spelling.join(('D:', ''.join(('My', 'pi_deskktop')), '.pi-desktoooop', 'data', 'scratch')) + spelling
            text = re.sub(re.escape(scratch) + r'[0-9a-fA-F-]{36}', '<PI_SCRATCH>', text)
    return text

def compact(value):
    """Exclude host identity and source-path dictionaries, not acceptance limits."""
    omit = {'source_sha256', 'command', 'commands', 'owned_pid', 'pid',
            'build_directory', 'repositories', 'environment', 'source_files_verified',
            'recipe_files_verified', 'saved_identical_command_fallbacks'}
    if isinstance(value, dict):
        return {k: compact(v) for k, v in value.items() if k not in omit}
    if isinstance(value, list):
        return [compact(v) for v in value]
    return value


def prepare(destination, source=ROOT):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    # previous.refresh checks the exact publication parent and origin first.
    upstream = source / 'fenestra/upstream'
    head = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    if head != UPSTREAM:
        raise ValueError('Unexpected Fenestra source identity')
    tracked = subprocess.check_output(['git', '-C', str(upstream), 'ls-files', '-z']).decode().split('\0')
    additions = {p: p.relative_to(source).as_posix()
                 for p in base.walk_files(source / 'fenestra/z62')
                 if p.suffix in {'.py', '.c', '.h', '.S', '.ld', '.json', '.md'}}
    additions.update({upstream / name: 'fenestra/upstream/' + name for name in tracked if name})
    summaries = {}
    for name, local in SUMMARIES.items():
        path = source / local
        proof = json.loads(path.read_text(encoding='utf-8-sig'))
        if proof.get('camera_accessed', False) or proof.get('flash_safety_verified', False):
            raise ValueError('Unexpected research scope: ' + local)
        if name.startswith(('cw-', 'request-')) and proof.get('completed_evidence_check') is not True:
            raise ValueError('Incomplete verification: ' + local)
        summaries[name] = dict(compact(proof), snapshot=SNAPSHOT,
            original_record_sha256=base.digest(path),
            publication_scope='Selected offline verification, not raw traces or a new firmware run. Negative acceptance fields are preserved.')
    # Validate extra inputs before the existing exporter writes its own subset.
    for path in additions:
        if base.linked(path) or not path.resolve().is_relative_to(source):
            raise ValueError('Linked or external source input')
        data = path.read_bytes()
        if len(data) > 2 * 1024**2 or any(p.search(data) for p in base.SECRET_PATTERNS):
            raise ValueError('Oversized or credential-shaped input: ' + additions[path])
        data.decode('utf-8-sig')
    manifest = previous.refresh(destination, source)
    mapping = {p: rel for p, rel in base.selection(source).items()
               if p.relative_to(source).parts[0] != 'analysis' or p.name == 'scope.md'}
    mapping.update(additions)
    mapping[source / 'README.md'] = 'README.md'
    ledger = {row['published']: row for row in manifest['files']}
    for path, relative in sorted(additions.items(), key=lambda pair: pair[1]):
        original = path.read_bytes()
        text = original.decode('utf-8-sig')
        if path.suffix == '.md':
            text = base.rewrite_links(text, path, relative, source, mapping)
        data = public_text(text, source).encode('utf-8')
        target = destination / relative
        if base.linked(target) or not target.resolve().is_relative_to(destination):
            raise ValueError('Unsafe publication target')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        ledger[relative] = dict(source=path.relative_to(source).as_posix(), published=relative,
            original_sha256=hashlib.sha256(original).hexdigest(),
            published_sha256=hashlib.sha256(data).hexdigest(), transformed=original != data, bytes=len(data))
    for name, proof in summaries.items():
        relative = 'docs/evidence/' + name
        data = (json.dumps(proof, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        (destination / relative).write_bytes(data)
        ledger[relative] = dict(source=SUMMARIES[name], published=relative,
            original_sha256=proof['original_record_sha256'], generated_summary=True,
            published_sha256=hashlib.sha256(data).hexdigest(), transformed=True, bytes=len(data))
    with (destination / 'README.md').open('a', encoding='utf-8') as handle:
        handle.write('\n- [最新 r110 + Fenestra r19 发布说明](docs/RELEASE-r110.md)\n'
                     '- [Fenestra ARM32 阶段与真机门槛](docs/profiles/README-FENESTRA-Z62.md)\n'
                     '- [r110 请求资格诊断摘要](docs/evidence/request-qualification-r110.json)\n'
                     '- [Fenestra r19 局部队列摘要](docs/evidence/fenestra-queue-r19.json)\n')
    # Redact all exported text, including code and retained curated documents.
    # Never touch .git, binary data, ignored runtimes or third-party submodules.
    candidates = set(ledger)
    for directory in ('docs', 'analysis'):
        candidates.update(p.relative_to(destination).as_posix() for p in (destination / directory).rglob('*') if p.is_file())
    candidates.update({'NOTICE.md'})
    retained_privacy = []
    for relative in sorted(candidates):
        path = destination / relative
        if not path.is_file() or path.suffix == '.png':
            continue
        original = path.read_bytes()
        data = public_text(original.decode('utf-8-sig'), source).encode('utf-8')
        if any(pattern.search(data) for pattern in base.SECRET_PATTERNS):
            raise ValueError('Credential-shaped public output: ' + relative)
        if data != original:
            path.write_bytes(data)
            if relative not in ledger:
                retained_privacy.append(dict(published=relative, before_sha256=hashlib.sha256(original).hexdigest(), after_sha256=hashlib.sha256(data).hexdigest()))
        if relative in ledger:
            row = ledger[relative]
            row.update(published_sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
            row['transformed'] = row['transformed'] or data != original
    manifest.update(snapshot=SNAPSHOT, files=list(ledger.values()), file_count=len(ledger),
        bytes=sum(row['bytes'] for row in ledger.values()), source_bytes_preserved=False,
        retained_public_privacy_transformations=retained_privacy,
        source_identity_note='Only files marked transformed=false retain original bytes. Privacy substitutions in source literals are explicit; research originals and runtime guards are unchanged.',
        fenestra_upstream=dict(url='https://github.com/WonderLantern/Fenestra', commit=UPSTREAM,
            modified_files=['include/fenestra_module.h', 'src/module.c'],
            scope='Vendored tracked source with upstream LICENSE and NOTICE; ARM32 loader-only, no firmware integration.'))
    (destination / 'publication-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'files'}, ensure_ascii=False))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    prepare(parser.parse_args().destination)
