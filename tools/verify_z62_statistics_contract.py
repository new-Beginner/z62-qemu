"""Verify original statistics DMA descriptors and actual CPU read widths."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import run_z62_raw_boundary as host

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/z62-statistics-r18'


def verify():
    build = host.verify_build(host.DEFAULT_QEMU)
    image = (ROOT / 'artifacts/z62-reference-1.70/master.bin').read_bytes()
    records, hashes = {}, {}
    for name, duration in (('initial-contract2',3),('reader-watch',18),('primary-reader-watch',11)):
        raw = (BASE / name / 'trace.json').read_bytes()
        d = json.loads(raw)
        session = json.loads((BASE / name / 'session.json').read_text(encoding='utf-8'))
        if (d.get('process_closed') is not True or d.get('detach') != 'OK' or d.get('failure') or
                d.get('cleanup_error') or d.get('stop_reason') != 'virtual limit' or
                d.get('live_anchors_verified') is not True or d.get('guest_state_patched') is not False or
                d.get('camera_accessed') is not False or d.get('device_experiments') or d.get('shutter_contacts') or
                d['observations'][-1]['virtual_seconds'] < duration or
                session['qemu_sha256'] != build['binary_sha256']):
            raise ValueError('Incomplete or incompatible statistics evidence: '+name)
        records[name] = d
        hashes[name] = hashlib.sha256(raw).hexdigest()
    commit = next(h for h in records['initial-contract2']['hits'] if
                  h['label'] == 'parameter-commit' and h['registers']['r0'] == '0x9e')
    state = commit['state']['extra_words']
    starts = (0x88E37000,0x88E73000,0x88EDF000,0x88EF1000,0x88F03000)
    pitches = (0xA000,0x12000,0x36000,0x36000,0x36000)
    for ch in range(5):
        base=0x2006A400+ch*256
        if (state[hex(base+0x14)] != ['0x3','0x1'] or
                state[hex(base+0x3c)] != ['0x0','0x1','0x0','0x5','0x0',hex(starts[ch])] or
                state[hex(base+0x60)] != [hex(starts[ch])] or state[hex(base+0x80)] != [hex(pitches[ch])]):
            raise ValueError('Original six-slot descriptor differs')
    counts = {}
    for name in ('reader-watch','primary-reader-watch'):
        d = records[name]
        reads = [h for h in d['hits'] if h['label'] == 'native-ram-read']
        if not reads or d.get('write_watchpoints'):
            raise ValueError('Missing read-only CPU observation')
        for h in reads:
            pc = int(h['registers']['pc'],16)
            if (not 0x10020000 <= pc < 0x12400000 or
                    bytes.fromhex(h['watch_instruction_4']) != image[pc-0x10020000:pc-0x10020000+4] or
                    h['watch_before'] != h.get('watch_after') or
                    int(h['extra_observation']['cpsr'],16) & 0x200):
                raise ValueError('Read instruction, data or endianness mismatch')
        counts[name] = dict(Counter(h['registers']['pc'] for h in reads))
    for pc in ('0x1024054e','0x10240554','0x10240558'):
        if counts['reader-watch'].get(pc,0) < 4:
            raise ValueError('Insufficient three-plane u16 read evidence')
    for pc in ('0x1024fd7e','0x1024f356','0x1024f35a'):
        if counts['primary-reader-watch'].get(pc,0) < 1:
            raise ValueError('Missing scalar or sum/count CPU access')
    return {'schema':1,'qemu_sha256':build['binary_sha256'],'trace_sha256':hashes,
            'reader_counts':counts,'dma_slots':6,'dma_bases':[hex(x) for x in starts],
            'dma_pitches':[hex(x) for x in pitches],
            'original_sum_count_u32_and_scalar_u16_verified':True,
            'original_three_plane_u16_reads_verified':True,
            'silicon_color_calibration_verified':False,'statistics_device_implemented':False,
            'photo_capture_verified':False,'complete_emulator':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=verify()
    with args.output.open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2))
