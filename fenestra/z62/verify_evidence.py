"""Verify the bounded loader-only evidence; never asserts hardware safety."""
import argparse
import json
from pathlib import Path
import subprocess
from build_probe import ROOT, require
from pack import VERSION, digest
from run_probe import QEMU_REL, QEMU_SHA


def verify(build, runs):
    build = build.resolve()
    require(build.is_relative_to(ROOT / '.build'), 'Build must remain in this project')
    manifest_path = build / 'build.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    require(manifest.get('completed') is True and manifest['version'] == VERSION, 'Incomplete build')
    for name, sha in manifest['source_sha256'].items():
        p = (ROOT / name).resolve()
        require(p.is_relative_to(ROOT) and digest(p.read_bytes()).hex() == sha, 'Changed source: ' + name)
    for name, sha in manifest['artifact_sha256'].items():
        p = (build / name).resolve()
        require(p.is_relative_to(build) and digest(p.read_bytes()).hex() == sha, 'Changed artifact: ' + name)
    original = manifest['native_format']['original']
    require(original == manifest['native_format']['ported_default'] and original['phase'] == 2 and original['passed'] == 58,
            'Default AArch64 format comparison failed')
    receipts = []
    require(len(runs) >= 2, 'Two independent executions are required')
    for path in runs:
        path = path.resolve()
        require(path.is_relative_to(ROOT / 'analysis'), 'Run receipt escaped project')
        r = json.loads(path.read_text(encoding='utf-8'))
        require(r['build_manifest_sha256'] == digest(manifest_path.read_bytes()).hex(), 'Run/build identity mismatch')
        require(r['completed'] and r['module_execution_verified'] and r['owned_process_closed'] and r['exit_code'] == 0,
                'Run failed or did not exit normally')
        require(r['probe']['passed'] == 58 and r['probe']['phase'] == 2 and r['probe']['logs'] == 2 and r['probe']['pointer_bytes'] == 4,
                'Guest checks incomplete')
        require(r['fixture_names'] == manifest['fixture_names'] and len(r['fixture_names']) == 29, 'Fixture identity mismatch')
        require(r['probe']['entry0'] != r['probe']['entry1'], 'Independent image placement missing')
        require(all(r[k] is False for k in ('firmware_loaded','camera_accessed','firmware_integrated','flash_safety_verified')),
                'Evidence scope was changed')
        require(digest(path.with_suffix('.qemu.log').read_bytes()).hex() == r['log_sha256'], 'Run log changed')
        receipts.append(dict(file=path.relative_to(ROOT).as_posix(), sha256=digest(path.read_bytes()).hex(), pid=r['owned_pid']))
    require(len({x['pid'] for x in receipts}) == len(receipts), 'Executions did not use separate processes')
    require(digest((ROOT / QEMU_REL).read_bytes()).hex() == QEMU_SHA, 'Existing QEMU changed')
    baseline = json.loads((ROOT / 'analysis/fenestra-feasibility/source-check.json').read_text(encoding='utf-8'))
    for row in baseline['original_inputs']:
        data = (ROOT / row['file']).read_bytes()
        require(len(data) == row['size'] and digest(data).hex() == row['sha256'], 'Original firmware identity changed')
    for row in baseline['sources']:
        if row['tree'] == 'workspace':
            require(digest((ROOT / row['file']).read_bytes()).hex() == row['sha256'], 'Existing source changed: ' + row['file'])
    files = subprocess.check_output(['git','-C',str(ROOT/'fenestra/upstream'),'diff','--name-only','HEAD'],text=True).splitlines()
    require(sorted(files) == ['include/fenestra_module.h','src/module.c'], 'Unexpected upstream source edits')
    return dict(version=VERSION, loader_evidence_verified=True, runs=receipts,
                guest_checks_per_run=58, distinct_fixture_kinds=29, positive_callbacks_per_run=2,
                original_firmware_inputs_unchanged=4, existing_qemu_unchanged=True,
                firmware_integrated=False, flash_safety_verified=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--run', type=Path, action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT/'analysis') and not output.exists(), 'Use a new project analysis output')
    result = verify(args.build, args.run)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))
