"""Replay scene identities and remeasure saved RAW/NV12/LCD observations."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

import run_z62_photo_results as host
import z62_scene_packet as packet
import z62_scene_response as response

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(case, output):
    if output.exists():
        raise FileExistsError('Existing scene response inventory is immutable')
    build = host.verify_build()
    read = lambda path: json.loads(path.read_text(encoding='utf-8'))
    receipt = read(case/'scene-response.json')
    life, trace = read(case/'lifecycle.json'), read(case/'trace.json')
    require(receipt['qemu_sha256'] == build['binary_sha256'], 'Frozen binary differs')
    require(receipt['completed_observation'] is True and receipt['process_closed'] is True and
            life['completed'] is True and trace['process_closed'] is True and trace['detach'] == 'OK',
            'Original scene window did not finish and close')
    require(receipt['sources_unchanged_during_run'] is True and not receipt['read_errors'],
            'Source or observation failure')
    for path, digest in receipt['sources_sha256'].items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, 'Observed source changed')
    for row in receipt['source_challenges']:
        data = packet.make_packet(Image.new('RGB', (64, 64), (row['gray'],)*3),
            epoch=row['epoch'], publish_id=row['publish_id'], frame_id=row['frame_id'],
            virtual_time_ns=row['virtual_time_ns'])
        info, raw = packet.parse_packet(data)
        require(info['raw_sha256'] == row['raw_sha256'] and
                hashlib.sha256(data).hexdigest() == row['packet_sha256'], 'Scene payload cannot be replayed')
        start = 502*2272+752*3//2
        require(raw[start:start+48].hex() == row['raw_reference'], 'RAW reference differs from source packet')
    for row in receipt['observations']:
        png = case/row['lcd_file']
        require(hashlib.sha256(png.read_bytes()).hexdigest() == row['lcd_sha256'], 'LCD evidence changed')
        with Image.open(png) as image:
            measured = response.measure(row['gray'], bytes.fromhex(row['raw_reference']),
                [bytes.fromhex(r['data']) for r in row['raw_patches']],
                [{'y': bytes.fromhex(r['y']), 'uv': bytes.fromhex(r['uv'])} for r in row['nv12_patches']], image)
        require(measured == row['measurement'], 'Pixel measurement cannot be reproduced')
    actual = response.assess(receipt['selected_observations'], receipt['return_time_sampled'])
    require(actual == receipt['assessment'], 'Scene verdict differs from recorded evidence')
    require(receipt['strict_mode_recovery_verified'] == life['assessment']['recovery_observed'],
            'Strict lifecycle verdict was changed')
    evidence = sorted(p for p in case.parent.rglob('*') if p.is_file() and
                      p.suffix in ('.json', '.png', '.txt', '.md', '.log'))
    source_names = ('tools/z62_scene_response.py', 'tools/trace_z62_scene_response.py',
        'tools/verify_z62_scene_response_evidence.py', 'tools/inspect_z62_paired_contract.py',
        'tests/test_z62_scene_response.py', 'tests/test_z62_paired_contract.py')
    result = {'schema': 1, 'version': '2026.11.03-scene-response-evidence-r54',
        'verification_completed': True, 'qemu_sha256': build['binary_sha256'],
        'original_guest_seconds': life['final_state']['virtual_seconds'],
        'original_stops': trace['stops'], 'observations_remeasured': len(receipt['observations']),
        'source_packets_replayed': len(receipt['source_challenges']),
        'source_sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_names},
        'evidence_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence},
        'new_scene_response_assessment': actual, 'strict_lifecycle_assessment': life['assessment'],
        'full_frame_pixel_identity_verified': False, 'video_verified': False, 'whole_camera_verified': False}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({k: result[k] for k in ('verification_completed', 'original_guest_seconds',
        'original_stops', 'observations_remeasured', 'source_packets_replayed',
        'new_scene_response_assessment', 'strict_lifecycle_assessment')}, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    verify(args.case, args.output)
