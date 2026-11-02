"""Verify r18 native DMA and original CPU consumption without camera claims."""
import argparse
import hashlib
import json
from pathlib import Path

import run_z62_continuous_stats as host
from probe_z62_continuous_stats import expected_outputs, BASES, PITCHES, SIZES
from verify_z62_frame_delivery import pairs

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/z62-statistics-r18'


def verify(long_observation=False):
    build = host.verify_build(host.DEFAULT_QEMU)
    hashes = {}
    def load(name):
        raw = (BASE/name).read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    native = load('native.json')
    required = ('actual_five_output_dma','independent_scene_equations','six_slots_and_guards',
                'w1c_backpressure','mask_latching','no_unchanged_source_replay',
                'unchanged_commit_preserves_cursor','bank_commit_restarts_cursor',
                'invalid_profile_no_data_or_completion','uncommitted_change_rejected',
                'source_overlap_rejected','legacy_finite_coexistence','stop_restart',
                'failed_raw_no_statistics_completion','readonly','slave_isolation','reset')
    if native.get('completed') is not True or native['binary_sha256'] != build['binary_sha256'] or any(
            native.get(name) is not True for name in required):
        raise ValueError('Native statistics coverage incomplete')
    finite = load('finite-regression.json')
    if finite.get('completed') is not True or finite['binary_sha256'] != build['binary_sha256']:
        raise ValueError('Existing finite profile regression incomplete')
    math = load('pixels-fixed/report.json')
    if (math.get('completed') is not True or math['header_sha256'] !=
            host.device.identity()['headers_sha256']['nikon-z62-statistics-pixels.h'] or
            math['test_sha256'] != hashlib.sha256((ROOT/'tests/native/z62_statistics_pixels_test.c').read_bytes()).hexdigest()):
        raise ValueError('Portable arithmetic proof is stale')
    expected = expected_outputs()
    original = (ROOT/'artifacts/z62-reference-1.70/master.bin').read_bytes()
    names = [('firmware-initial',3),('native-contract',3),('native-reader',11)]
    if long_observation:
        names.append(('native-primary-reader2',18))
    summaries = {}
    for name, duration in names:
        d = load(name+'/trace.json')
        session = load(name+'/session.json')
        if (d.get('failure') or d.get('cleanup_error') or d.get('process_closed') is not True or
                d.get('detach') != 'OK' or d.get('stop_reason') != 'virtual limit' or
                d.get('guest_state_patched') is not False or d.get('camera_accessed') is not False or
                d.get('device_experiments') or d.get('shutter_contacts') or
                d['observations'][-1]['virtual_seconds'] < duration or
                session['qemu_sha256'] != build['binary_sha256']):
            raise ValueError('Incomplete original-firmware evidence: '+name)
        row = {'end_virtual_seconds':d['observations'][-1]['virtual_seconds']}
        if name.startswith('native-') and 'reader' in name:
            reads = [h for h in d['hits'] if h['label'] == 'native-ram-read']
            channels = set()
            if not reads:
                raise ValueError('No original CPU reads: '+name)
            for h in reads:
                pc = int(h['registers']['pc'],16)
                if (bytes.fromhex(h['watch_instruction_4']) != original[pc-0x10020000:pc-0x10020000+4] or
                        h['watch_before'] != h.get('watch_after')):
                    raise ValueError('Original reader instruction/data changed')
                address = int(h['watch_address'],16)
                if address >= 0xC0000000:
                    address -= 0x40000000
                matches = []
                for ch in range(5):
                    for slot in range(6):
                        offset = address-BASES[ch]-slot*PITCHES[ch]
                        if 0 <= offset <= SIZES[ch]-8 and h['watch_before'] == expected[ch][offset:offset+8].hex():
                            matches.append(ch)
                if len(matches) != 1:
                    raise ValueError('Original CPU read differs from independent scene value: '+h['watch_address'])
                channels.add(matches[0])
            required_channels = {2,3,4} if name == 'native-reader' else {0,1}
            if channels != required_channels:
                raise ValueError('Not all expected output channels were consumed')
            row.update(matched_cpu_reads=len(reads),channels=sorted(channels))
        if name in ('native-contract','native-primary-reader2'):
            status = d['observations'][-1].get('continuous_statistics_status',{})
            if not status.get('known') or status.get('errors'):
                raise ValueError('Statistics counters unavailable')
            main, slave = status['engines']['master'], status['engines']['slave']
            if (main['continuous-frames'] < 6 or main['continuous-rejected'] or
                    main['continuous-bytes'] != main['continuous-frames']*sum(SIZES) or
                    slave['continuous-frames'] != 0):
                raise ValueError('Statistics stream failed or crossed engine boundary')
            row['statistics'] = main
        if name == 'firmware-initial':
            waits = pairs(d,'input-ready')
            if len(waits) < 5 or not all(w['result'] == 0 and .19 <= w['seconds'] <= .22 for w in waits):
                raise ValueError('Remaining input-ready behavior changed; review it')
            row['remaining_input_ready_waits'] = waits
        summaries[name] = row
    return {'schema':1,'qemu_sha256':build['binary_sha256'],'evidence_sha256':hashes,'observations':summaries,
            'native_statistics_dma_verified':True,'original_rgb_consumption_verified':True,
            'original_primary_consumption_verified':long_observation,
            'long_observation_verified':long_observation,'remaining_input_wait_resolved':False,
            'silicon_calibration_verified':False,'photo_capture_verified':False,
            'complete_emulator':False,'flash_safety_verified':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--long-observation',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=verify(args.long_observation)
    with args.output.open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2))
