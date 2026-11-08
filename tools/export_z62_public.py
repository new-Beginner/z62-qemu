# SPDX-License-Identifier: GPL-2.0-or-later
"""Export a new public source snapshot, preserving the private research workspace.

Maintainer packaging tool, not a firmware/runtime builder. Stock firmware,
decompilations, card images, compiled binaries and Git history are excluded.
Source bytes stay intact; documentation/evidence redactions get both hashes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
CODE_SUFFIXES = {'.py', '.c', '.h', '.java', '.js', '.html', '.css', '.cmd', '.md', '.json'}
SUMMARY_NAMES = {'summary.json', 'regression.json', 'report.json', 'comparison.json',
                 'verified-artifacts.json', 'media-check.json', 'async-video-check.json',
                 'native-console-check.json'}
EXTRA_EVIDENCE = {
    'analysis/z62-grid-r48/native-1.json', 'analysis/z62-grid-r48/native-2.json',
    'analysis/z62-grid-r48/native-parent.json', 'analysis/z62-grid-r48/parent-native-regressions.json',
    'analysis/z62-grid-r48/regression-output.txt',
    'analysis/z62-recovery-r49/grid-on-1/lifecycle.json',
    'analysis/z62-recovery-r49/grid-on-1-stdout.txt',
    'analysis/z62-recovery-r49/regression-output.txt', 'analysis/z62-recovery-r49/targeted-tests.txt',
    *{'analysis/z62-recovery-r49/grid-on-1/'+n+'.png' for n in ('before', 'pin0-low', 'pin0-high', 'final')},
}
SECRET_PATTERNS = [
    re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
    re.compile(rb'github_pat_[A-Za-z0-9_]{40,}'),
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    re.compile(rb'AKIA[0-9A-Z]{16}'),
]


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def scrub(text, root):
    replacements = ((str(root), '<WORKSPACE>'), (root.as_posix(), '<WORKSPACE>'),
                    (str(root.parent), '<PROJECTS>'), (root.parent.as_posix(), '<PROJECTS>'))
    for old, new in replacements:
        for spelling in (old.replace('\\', '\\\\'), old):
            text = text.replace(spelling, new)
    text = re.sub(r'(?i)C:[/\\]Users[/\\][^/\\\s"<>]+', '<USERPROFILE>', text)
    return text.replace('<LOCAL_EMAIL>', '<LOCAL_EMAIL>')


def scrub_json(value, root):
    if isinstance(value, str): return scrub(value, root)
    if isinstance(value, list): return [scrub_json(x, root) for x in value]
    if isinstance(value, dict): return {scrub(k, root): scrub_json(v, root) for k, v in value.items()}
    return value


def walk_files(base):
    if not base.is_dir(): return
    for directory, folders, files in os.walk(base, followlinks=False):
        folders[:] = [n for n in folders if n not in ('.git', '__pycache__', '.pytest_cache', '.venv', 'node_modules')
                      and not linked(Path(directory)/n)]
        for name in files:
            path = Path(directory)/name
            if not linked(path): yield path


def linked(path):
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def selection(root):
    mapping = {}
    for directory in ('tools', 'tests', 'qemu'):
        for path in walk_files(root/directory):
            if path.suffix.lower() in CODE_SUFFIXES:
                mapping[path] = path.relative_to(root).as_posix()
    for path in root.glob('*report.md'):
        mapping[path] = 'docs/history/'+path.name
    for path in root.glob('README-*.md'):
        mapping[path] = 'docs/profiles/'+path.name
    for pattern in ('requirements*.txt', 'start-*.cmd'):
        for path in root.glob(pattern): mapping[path] = path.name
    coverage = root/'Z62-CAPABILITY-COVERAGE.md'
    if coverage.is_file(): mapping[coverage] = 'docs/CAPABILITY-COVERAGE.md'
    for path in walk_files(root/'analysis'):
        relative = path.relative_to(root).as_posix()
        if relative in EXTRA_EVIDENCE or (
                path.name in SUMMARY_NAMES and path.stat().st_size <= 262144) or path.name == 'scope.md':
            if path.suffix in ('.json', '.md', '.txt', '.png'):
                mapping[path] = relative
    licenses = {
        'third_party/z62-qemu/COPYING': 'COPYING',
        'third_party/z62-qemu/NOTICE.md': 'LICENSES/z62-upstream-NOTICE.md',
        'third_party/z72-qemu/NOTICE.md': 'LICENSES/z72-upstream-NOTICE.md',
        'third_party/z6-qemu/NOTICE.md': 'LICENSES/z6-upstream-NOTICE.md',
        'third_party/z62-qemu/LICENSES/QEMU-LICENSE.txt': 'LICENSES/QEMU-LICENSE.txt',
        'third_party/nikon-fw-key-tool/LICENSE': 'LICENSES/nikon-fw-key-tool-GPL-3.0.txt',
    }
    for old, new in licenses.items():
        if (root/old).is_file(): mapping[root/old] = new
    return mapping


def rewrite_links(text, source, published, root, mapping):
    def replace(match):
        label, raw = match.group(1), match.group(2).strip()
        if raw.startswith(('https://', 'http://', 'mailto:', '#')): return match.group(0)
        target, marker, fragment = raw.strip('<>').partition('#')
        line = re.search(r':(\d+)$', target)
        if line:
            fragment, marker = 'L'+line.group(1), '#'
            target = target[:line.start()]
        path = Path(unquote(target))
        path = (path if path.is_absolute() else source.parent/path).resolve()
        selected = mapping.get(path)
        if selected:
            relative = posixpath.relpath(selected, posixpath.dirname(published) or '.')
            relative += ('#'+fragment) if marker else ''
            return label+'('+relative+')'
        caption = label.lstrip('!').removesuffix(']').removeprefix('[')
        return caption+'（本地证据，未分发：`'+scrub(raw, root)+'`）'
    return re.sub(r'(!?\[[^\]\n]*\])\(([^)\n]+)\)', replace, text)


def export(source, destination, *, dry_run=False):
    source = Path(source).resolve(strict=True)
    raw_target = Path(destination).absolute()
    if any(linked(p) for p in (raw_target, *raw_target.parents)):
        raise ValueError('Publication destination must not use filesystem links')
    destination = raw_target.resolve()
    if destination.exists() or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Choose a nonexistent independent publication directory')
    mapping = selection(source)
    if len(set(mapping.values())) != len(mapping): raise ValueError('Publication path collision')
    prepared, ledger = {}, []
    for path, relative in sorted(mapping.items(), key=lambda pair: pair[1]):
        if linked(path) or not path.resolve().is_relative_to(source):
            raise ValueError('Linked or external publication input: '+relative)
        original = path.read_bytes()
        if len(original) > 2*1024**2: raise ValueError('Oversized public input: '+relative)
        if any(pattern.search(original) for pattern in SECRET_PATTERNS):
            raise ValueError('Credential-shaped data in publication input: '+relative)
        data = original
        is_evidence = path.relative_to(source).parts[0] == 'analysis'
        if path.suffix == '.md':
            text = original.decode('utf-8-sig')
            text = rewrite_links(text, path, relative, source, mapping)
            data = scrub(text, source).encode('utf-8')
        elif is_evidence and path.suffix == '.json':
            data = (json.dumps(scrub_json(json.loads(original), source), ensure_ascii=False, indent=2)+'\n').encode('utf-8')
        elif is_evidence and path.suffix == '.txt':
            data = scrub(original.decode('utf-8-sig'), source).encode('utf-8')
        prepared[relative] = data
        ledger.append({'source': path.relative_to(source).as_posix(), 'published': relative,
                       'original_sha256': hashlib.sha256(original).hexdigest(),
                       'published_sha256': hashlib.sha256(data).hexdigest(),
                       'transformed': original != data, 'bytes': len(data)})
    local_evidence = []
    for path in sorted(walk_files(source/'analysis')):
        local_evidence.append({'path': path.relative_to(source).as_posix(), 'bytes': path.stat().st_size,
                               'original_sha256': digest(path), 'published': path in mapping})
    index = {'schema': 1, 'scope': 'Local evidence inventory; hashes do not publish the original contents.',
             'entries': local_evidence}
    prepared['docs/evidence-index.json'] = (json.dumps(index, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    result = {'schema': 1, 'snapshot': '2026-11-02-r49', 'file_count': len(prepared),
              'bytes': sum(map(len, prepared.values())), 'source_bytes_preserved': True,
              'original_firmware_included': False, 'compiled_runtimes_included': False,
              'raw_disassembly_included': False, 'original_git_history_included': False,
              'evidence_inventory_count': len(local_evidence), 'files': ledger,
              'notes': ['Documentation paths and selected evidence are redacted; both hashes are recorded.',
                        'Runtime source files retain their bytes and identity contracts.',
                        'Curated publication documents and Git submodule pointers are added separately.']}
    if dry_run: return result
    destination.mkdir(parents=True, exist_ok=False)
    for relative, data in prepared.items():
        path = destination/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as handle: handle.write(data)
    with (destination/'publication-manifest.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    result = export(args.source, args.destination, dry_run=args.dry_run)
    print(json.dumps({key: value for key, value in result.items() if key != 'files'}, ensure_ascii=False, indent=2))
