# SPDX-License-Identifier: GPL-2.0-or-later
"""Explicit offline candidate input, restricted to the Z62 C1.70 image layout.

CRC means structural integrity, never Nikon authenticity or flash safety.
No updater, physical device, or repacker is provided here.
"""
import binascii
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import stat

from prepare_reference_firmware import PROFILES
from prepare_firmware import ROOT, XOR_SOURCE, XOR_SOURCE_SHA256, decode, public_tables
from reference_updates import replace_once

SPEC = PROFILES['z62']
PACKAGE_SIZE = 49002888
LAYOUT = (
    ('ex1850_012000.bi', 208, 524290),
    ('_tpj01_v140.bin', 524498, 57346),
    ('eg1850_mas_01700', 581844, 38750138),
    ('vr1850_010100.bi', 39331982, 838664),
    ('eg1850_sla_01700', 40170646, 8832194),
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_regular(path, size):
    path = Path(path)
    # Check before resolution, including Windows junctions/reparse points.
    for part in (path.absolute(), *path.absolute().parents):
        info = part.lstat()
        if part.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Candidate input cannot use links/reparse points: ' + str(part))
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size != size:
        raise ValueError(f'Unsupported C1.70 input size/type: {path.name}, expected {size}')
    with path.open('rb') as stream:
        import os
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != size:
            raise ValueError(f'Unsupported C1.70 input size/type: {path.name}, expected {size}')
        data = stream.read(size + 1)
    if len(data) != size:
        raise ValueError('Candidate changed size while reading')
    return data


@dataclass(frozen=True)
class Candidate:
    # Bytes are snapshotted before staging; later edits to source paths do not
    # change the selected input. Each boot verifies the staged snapshot again.
    members: tuple
    metadata_json: str

    @property
    def metadata(self):
        return json.loads(self.metadata_json)


def load_candidate(*, package=None, members=None):
    if (package is None) == (members is None):
        raise ValueError('Specify exactly one candidate package or member directory')
    files, package_record, extra = {}, None, []
    if package is not None:
        raw = read_regular(package, PACKAGE_SIZE)
        decoder = XOR_SOURCE.read_bytes()
        if sha(decoder) != XOR_SOURCE_SHA256:
            raise ValueError('Public decoder identity changed')
        plain, modules = decode(raw, public_tables(decoder.decode('utf-8')))
        if tuple(modules) != LAYOUT:
            raise ValueError('Unsupported model/version/layout: requires Z62 C1.70')
        for name, offset, length in modules:
            data = plain[32 + offset:32 + offset + length]
            if name in SPEC['members']:
                files[SPEC['members'][name][0]] = data
            else:
                extra.append({'member': name, 'sha256': sha(data), 'size': len(data),
                              'executed': False, 'reason': 'Peripheral processor not emulated'})
        package_record = {'name': Path(package).name, 'sha256': sha(raw), 'size': len(raw),
                          'matches_reference': sha(raw) == SPEC['sha256']}
    else:
        for filename, size, _ in SPEC['members'].values():
            files[filename] = read_regular(Path(members) / filename, size)
    records = {}
    for name, (filename, size, baseline_sha) in SPEC['members'].items():
        data = files[filename]
        if len(data) != size or binascii.crc_hqx(data, 0) != 0:
            raise ValueError('Candidate member length/CRC mismatch: ' + filename)
        baseline = (ROOT / 'artifacts/z62-reference-1.70' / filename).read_bytes()
        if len(baseline) != size or sha(baseline) != baseline_sha:
            raise ValueError('Reference member identity mismatch: ' + filename)
        # Bounded summary; do not produce millions of ranges for arbitrary inputs.
        import numpy as np
        indexes = np.flatnonzero(np.frombuffer(data, dtype=np.uint8) !=
                                 np.frombuffer(baseline, dtype=np.uint8))
        records[filename] = {'member': name, 'size': size, 'sha256': sha(data),
            'baseline_sha256': baseline_sha, 'matches_reference': sha(data) == baseline_sha,
            'changed_bytes': int(indexes.size),
            'first_changed_offset': int(indexes[0]) if indexes.size else None,
            'last_changed_offset': int(indexes[-1]) if indexes.size else None}
    metadata = {'schema': 1, 'mode': 'explicit-offline-candidate',
        'layout': 'Z62 C1.70 fixed module names and sizes', 'package': package_record,
        'members': records, 'unexecuted_members': extra,
        'all_executed_members_match_reference': all(r['matches_reference'] for r in records.values()),
        'package_crc_verified': package is not None, 'member_crcs_verified': True,
        'signature_verified': False, 'flash_safety_verified': False,
        'candidate_layout_semantics_verified': False, 'camera_accessed': False}
    return Candidate(tuple(sorted(files.items())), json.dumps(metadata, sort_keys=True))


def install_candidate(work, record, candidate):
    """Replace only disposable staged originals with the selected snapshot."""
    info = candidate.metadata
    for filename, data in candidate.members:
        row = info['members'][filename]
        if sha(data) != row['sha256'] or len(data) != row['size']:
            raise ValueError('Candidate snapshot identity mismatch')
    for filename, data in candidate.members:
        path = work / 'inputs' / filename
        if path.is_symlink() or sha(path.read_bytes()) != info['members'][filename]['baseline_sha256']:
            raise ValueError('Expected disposable original staging copy')
    for filename, data in candidate.members:
        (work / 'inputs' / filename).write_bytes(data)
    record['inputs'] = {name: {'size': row['size'], 'sha256': row['sha256']}
                        for name, row in info['members'].items()}
    record['firmware_candidate'] = info
    record['guest_patched'] = not info['all_executed_members_match_reference']
    record['runtime_guest_patches'] = False
    (work / 'candidate.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')


def candidate_health(machine, info):
    """Hardcoded C1.70 RAM addresses are not a candidate health oracle."""
    return {'firmware_candidate': info, 'firmware_health_known': False,
            'firmware_status_empty': False, 'firmware_status_codes': None,
            'firmware_status_count': None, 'live_view_verified': False,
            'firmware_observation_error': 'Candidate internal state layout is unverified'}


def candidate_status(machine, read_status, info):
    try:
        state = read_status()
    except (OSError, RuntimeError, ValueError) as exc:
        # The candidate may not initialize the original OS/RAM structures at all.
        # Keep the observation failure visible; do not invent application health.
        process = machine.process
        exited = process is not None and process.poll() is not None
        state = {'model': 'Z62', 'phase': 'failed' if exited else machine.phase,
                 'error': 'Candidate QEMU exited' if exited else machine.error,
                 'ready': False, 'input_ready': False,
                 'candidate_observation_error': type(exc).__name__ + ': ' + str(exc)}
    state.update(candidate_health(machine, info))
    state['candidate_internal_observations_verified'] = False
    state['package_version'] = '2026.10.28-candidate1'
    return state


def apply_console(source, candidate):
    """Bind the disposable console to exact candidate hashes, not arbitrary images."""
    info = candidate.metadata
    identities = {Path(name).stem: (row['size'], row['sha256'])
                  for name, row in info['members'].items()}
    path = source / 'tools/z62_console.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text, "PACKAGE_VERSION = '2026.10.28-r5'",
        "PACKAGE_VERSION = '2026.10.28-candidate1'\n"
        'IDENTITIES = ' + repr(identities) + '\n'
        'CANDIDATE_INFO = ' + repr(info) + '\n'
        'from tools.z62_candidate_health import candidate_health, candidate_status\n')
    text = replace_once(text, "f'{role}: expected the original Z62 C1.70 image'",
                        "f'{role}: staged candidate hash/size mismatch'")
    text = replace_once(text, "self.firmware = dict(model='Z6 II', version='C1.70', source='original')",
                        "self.firmware = dict(model='Z6 II', version='candidate', source='user-selected')")
    text = replace_once(text, 'state.update(firmware_health(self))',
                        'state.update(candidate_health(self, CANDIDATE_INFO))')
    text = replace_once(text, '    def status(self):',
        '    def status(self):\n'
        '        return candidate_status(self, self._candidate_legacy_status, CANDIDATE_INFO)\n\n'
        '    def _candidate_legacy_status(self):')
    # Preserve read-only legacy observations, but explicitly label their assumptions.
    text = replace_once(text, '        return state\n\n    def _cleanup',
        "        state['candidate_internal_observations_verified'] = False\n"
        '        return state\n\n    def _cleanup')
    # Copy only a small dependency-free helper, not the parser or host library.
    import inspect
    helper = inspect.getsource(candidate_health) + '\n\n' + inspect.getsource(candidate_status)
    html = source / 'web-z62/index.html'
    content = replace_once(html.read_text(encoding='utf-8'),
        '独立开发版 · 2026.10.28-r5', '候选固件离线测试 · candidate1')
    content = replace_once(content,
        'r5可选真实RAW DMA完成后的设备事件桥；默认关闭，非硬件时序定论。只读固件状态与事务计数；完整取景、拍照保存和稳定菜单循环尚未验收。',
        '正在执行你明确选择的候选固件。CRC仅检查完整性；内部状态地址未验证，固件健康状态为未知。完整取景、拍照和更新流程未模拟，不能据此判断真机刷写安全。')
    for old, new in (
        ('<title>Z62 · 原厂菜单模拟器</title>', '<title>Z62 · 候选固件测试</title>'),
        ('原厂菜单模拟器 · C1.70', '候选固件测试 · C1.70布局'),
        ('Z62 原厂固件实时画面', 'Z62 候选固件 LCD 输出'),
        ('<h1>操作原厂菜单</h1>', '<h1>测试候选固件</h1>'),
    ):
        content = replace_once(content, old, new)
    path.write_text(text, encoding='utf-8', newline='\n')
    (source / 'tools/z62_candidate_health.py').write_text(helper, encoding='utf-8', newline='\n')
    html.write_text(content, encoding='utf-8', newline='\n')
