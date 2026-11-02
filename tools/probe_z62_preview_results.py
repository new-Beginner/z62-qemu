"""Firmware-free native result/DMA/IRQ/backpressure checks for r47b."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_preview as preview
import run_z62_preview_results as initial
import run_z62_preview_results_format as host

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT/'qemu/z62-preview-results/observed-profile.json'
FIXTURE_SHA = 'bbde7789ec91b38e907936d9177f17376f5e81e58e68131f258c350a185b434a'
PARAMETERS = (0xC2400000, 0xC2401000, 0xC2402000)


@contextmanager
def session(binary, enabled=True):
    original = preview.host.configure_command
    def configure(command, *args, **kwargs):
        return host.configure_command(original(command, *args, **kwargs), enabled)
    with patch.object(preview.host, 'configure_command', configure), preview.session(binary) as s:
        yield s


def fixture():
    data = FIXTURE.read_bytes()
    if hashlib.sha256(data).hexdigest() != FIXTURE_SHA:
        raise ValueError('Observed Z62 result fixture identity mismatch')
    return json.loads(data)


def configure_units(s, variant=-1):
    units = fixture()['variants'][variant]['units']
    for i, row in enumerate(units):
        data = bytearray.fromhex(row['parameters_0a0'])
        data[0x8c:0x94] = bytes.fromhex('efbeaddebeab0df0')
        for offset in range(0, len(data), 4):
            s.write(PARAMETERS[i]+offset, int.from_bytes(data[offset:offset+4], 'little'))
        registers = list(row['register_words_raw'])
        registers[4] = PARAMETERS[i]
        for j, value in enumerate(registers):
            s.write(int(row['register_address'], 16)+j*4, value)


def get(s, name, path=None):
    return s.get('preview-result-'+name, path or s.master)


def acknowledge(s):
    s.write(0x2010001C, 0x61)
    preview.acknowledge(s)


def pixels_and_guards(s):
    for channel, (w, h, stride, uv) in enumerate(preview.GEOMETRY):
        yprefix, uvprefix = preview.expected_prefix(w, h)
        for address in set(preview.OUTPUTS[channel]):
            assert s.read(address, 32) == yprefix
            assert s.read(address+uv, 32) == uvprefix
            for base, size in ((address, stride*h), (address+uv, stride*h//2)):
                assert s.read(base-16, 16) == b'\xa5'*16
                assert s.read(base+size, 16) == b'\xa5'*16


def check(binary):
    result = {}
    with session(binary, False) as s:
        assert not s.get('z62-preview-results', s.master)
        preview.configure(s)
        configure_units(s)
        preview.new_raw(s)
        preview.advance(s)
        assert preview.get(s, 'outputs') == 12
        assert preview.read(s, 0x2010001C) == 0 and get(s, 'batches') == 0
        result['explicit_default_off'] = True
    with session(binary) as s:
        assert s.get('z62-preview-results', s.master)
        preview.configure(s)
        configure_units(s)
        s.write(0x20100010, 0x61)
        preview.advance(s)
        assert get(s, 'batches') == 0  # register configuration alone is not work
        preview.fill_guards(s)
        preview.new_raw(s)
        preview.advance(s)
        assert preview.get(s, 'reason') == 'success', preview.get(s, 'reason')
        assert get(s, 'batches') == 1 and get(s, 'units') == 3
        assert preview.get(s, 'outputs') == 12 and preview.get(s, 'bytes') == preview.BATCH_BYTES
        assert preview.read(s, 0x2010001C) == 0x61 and preview.read(s, 0x20100020) == 8
        pixels_and_guards(s)
        for pointer in PARAMETERS:
            assert s.read(pointer+0x8c, 8) == bytes.fromhex('efbeaddebeab0df0')
        s.irqs.clear()
        s.write(0x2010001C, 1)
        assert preview.read(s, 0x2010001C) == 0x60
        s.write(0x2010001C, 0x20)
        assert preview.read(s, 0x2010001C) == 0x40
        s.write(0x2010001C, 0x40)
        assert preview.read(s, 0x2010001C) == 0 and preview.read(s, 0x20100020) == 8
        assert 'IRQ lower 70' not in s.irqs  # command source keeps shared IRQ102 raised
        preview.acknowledge(s)
        assert 'IRQ lower 70' in s.irqs
        s.write(0x20100010, 0)
        s.write(0x20100014, 0)
        s.write(0x20380020, 0)
        s.irqs.clear()
        preview.new_raw(s)
        preview.advance(s)
        assert get(s, 'batches') == 2 and preview.read(s, 0x2010001C) == 0x61
        assert 'IRQ raise 70' not in s.irqs
        s.write(0x20100010, 1)
        assert 'IRQ raise 70' in s.irqs
        s.write(0x2010001C, 1)
        assert 'IRQ lower 70' in s.irqs
        s.write(0x20100010, 0x60)
        assert s.irqs[-1] == 'IRQ raise 70'
        preview.acknowledge(s)  # Leave two result bits pending.
        first = preview.OUTPUTS[0][0]
        s.access(f'memset {first:#x} 0x20 0xa6')
        preview.new_raw(s)
        preview.advance(s)
        assert get(s, 'batches') == 2 and get(s, 'blocked') > 0
        assert s.read(first, 32) == b'\xa6'*32
        s.write(0x2010001C, 0x60)
        preview.advance(s)
        assert get(s, 'batches') == 3 and preview.get(s, 'outputs') == 36
        assert s.read(first, 32) == preview.expected_prefix(1920, 1080)[0]
        acknowledge(s)
        preview.new_raw(s)
        s.write(0x20102100, 0)
        preview.advance(s)
        assert get(s, 'batches') == 3 and preview.read(s, 0x2010001C) == 0
        s.write(0x20102100, 0x121)
        preview.advance(s)
        assert get(s, 'batches') == 4
        acknowledge(s)
        preview.new_raw(s)
        s.write(0x203800F0, 0xFC400)
        preview.advance(s)
        assert get(s, 'batches') == 4 and preview.read(s, 0x2010001C) == 0
        assert not (preview.read(s, 0x20100020) & 4)
        assert get(s, 'batches', s.slave) == get(s, 'units', s.slave) == 0
        s.query('qom-set', {'path': s.master, 'property': 'preview-result-batches', 'value': 0}, error=True)
        s.query('system_reset')
        preview.advance(s)
        assert all(get(s, name) == 0 for name in ('batches', 'units', 'rejected', 'blocked'))
        assert preview.read(s, 0x2010001C) == preview.read(s, 0x20100020) == 0
        result.update(actual_twelve_nv12_writes=True, independent_prefixes_and_guards=True,
                      software_metadata_ignored_and_preserved=True, per_bit_w1c=True,
                      shared_irq102_preserved=True, masked_results_latch=True,
                      partial_ack_keeps_backpressure=True, last_ack_resumes=True,
                      cancel_and_stop_no_completion=True, no_bank0_completion=True,
                      slave_isolation=True, read_only_counters=True, reset=True, command=s.command)
    with session(binary) as s:
        failures = (
            ('non-ram-parameters', lambda: s.write(0x201009F0, 0x20100000)),
            ('wrapped-parameters', lambda: s.write(0x201009F0, 0xFFFFFFD0)),
            ('unfinished-unit-submit', lambda: s.write(0x201009F4, 1)),
            ('disabled-unit', lambda: s.write(0x201009EC, 0)),
            ('wrong-port', lambda: s.write(PARAMETERS[1]+12, 0x10003)),
            ('wrong-internal-height', lambda: s.write(PARAMETERS[0]+0x30, 0x046F0000)),
            ('unknown-format', lambda: s.write(PARAMETERS[2]+0x1c, 0xff010400)),
            ('bad-last-destination', lambda: s.write(0x20102200+3*64+4*4, 0xC1800000)),
        )
        rejected = []
        for name, change in failures:
            s.query('system_reset')
            preview.configure(s)
            configure_units(s)
            first = preview.OUTPUTS[0][0]
            s.access(f'memset {first:#x} 0x20 0xa5')
            change()
            preview.new_raw(s)
            preview.advance(s)
            assert get(s, 'batches') == get(s, 'units') == preview.get(s, 'outputs') == 0, name
            assert preview.read(s, 0x2010001C) == preview.read(s, 0x20100020) == 0, name
            assert s.read(first, 32) == b'\xa5'*32, name
            rejected.append(name)
        result['rejected_without_output_or_completion'] = rejected
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--initial-profile', action='store_true')
    args = parser.parse_args()
    m = initial.verify_build(args.qemu.resolve()) if args.initial_profile else host.verify_build(args.qemu.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        result = {'schema': 1, 'completed': False, 'binary_sha256': m['binary_sha256'],
                  'initial_profile_under_test': args.initial_profile, 'firmware_loaded': False,
                  'synthetic_arm_loops_executed': True, 'camera_accessed': False,
                  'whole_camera_verified': False}
        try:
            result.update(check(args.qemu), completed=True)
        except Exception as exc:
            result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
            raise
        finally:
            json.dump(result, handle, indent=2)
    print(json.dumps(result), flush=True)
