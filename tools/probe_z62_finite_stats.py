"""Native firmware-free r8 DMA, counter, IRQ and cancellation verification."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_raw_stream as stream
import run_z62_finite_stats as host

INPUT = '/machine/master-input'
START, END, PITCH, SIZE = 0x89C48400, 0x8A092400, 0x12000, 768


@contextmanager
def session(binary, enabled=True):
    original = stream.host.configure_command
    def configure(command, *a, **kw):
        return host.configure_command(original(command, *a, **kw), enabled)
    with patch.object(stream.host, 'configure_command', configure), stream.session(binary, enabled=False) as s:
        yield s


def get(s, name):
    return s.get('finite-'+name, INPUT)


def frame(s, count=1):
    for _ in range(count):
        for level in (1, 0):
            s.access(f'set_irq_in {INPUT} finite-frame 0 {level}')


def configure(s, pitch=PITCH, bank=0, destination=START):
    values = {0x2006A514:3, 0x2006A518:1, 0x2006A524:0, 0x2006A53C:bank,
              0x2006A540:1, 0x2006A544:0, 0x2006A548:60, 0x2006A54C:0,
              0x2006A550:destination, 0x2006A560:destination, 0x2006A580:pitch,
              0x2006A2BC:3, 0x2006A2D0:0x0C1E}
    for address, value in values.items():
        s.write(address, value)


def arm(s, mask=0xA0):
    s.write(0x20068010, 0x10)
    # Native finite capture keeps this command-notification enable word set.
    s.write(0x20068018, 0x1C)
    s.write(0x20068260, mask)
    s.write(0x20068008, 0x10)
    s.write(0x20068100, 8)


def source(s):
    s.configure()
    s.submit()
    assert s.get('raw-accepted', INPUT) > 0


def expected_grid():
    # Independent scalar scene reference; native C decodes actual packed RAW.
    result = bytearray(SIZE)
    for y in range(12):
        for x in range(30):
            total = count = 0
            for sy in range(y*1006//12, (y+1)*1006//12):
                for sx in range(x*1514//30, (x+1)*1514//30):
                    total += (sx*3 + sy*5 + 0x100) & 4095
                    count += 1
            result[y*64+x*2:y*64+x*2+2] = ((total+count//2)//count).to_bytes(2, 'little')
    return bytes(result)


def check(binary):
    evidence = {}
    expected = expected_grid()
    with session(binary, False) as s:
        source(s); configure(s); arm(s); frame(s, 62)
        assert get(s, 'frames') == get(s, 'batches') == get(s, 'attempts') == 0
        evidence['default_off'] = True
    with session(binary) as s:
        configure(s); arm(s); frame(s)
        assert get(s, 'reason') == 'source' and get(s, 'frames') == 0
        assert stream.read(s, 0x20068270) == 0
        source(s)
        s.access(f'memset {START:#x} {61*PITCH:#x} 0xa5')
        s.write(0x20068100, 8)
        frame(s, 60)
        assert get(s, 'frames') == 60 and get(s, 'batches') == 0
        assert stream.read(s, 0x20068270) == 0x20
        assert s.read(START, SIZE) == expected
        assert s.read(START+59*PITCH, SIZE) == expected
        assert s.read(START+60*PITCH, SIZE) == b'\xa5'*SIZE
        frame(s)
        assert get(s, 'batches') == 1 and get(s, 'frames') == 61
        assert stream.read(s, 0x20068270) == 0xA0
        assert 'IRQ raise 64' in s.irqs
        assert s.read(START+60*PITCH, SIZE) == expected
        for index in (0, 30, 60):
            assert s.read(START+index*PITCH+SIZE, 32) == b'\xa5'*32
        frame(s, 5)
        s.write(0x20068100, 8)
        frame(s)
        assert get(s, 'batches') == 1  # no duplicate for unchanged completed descriptor
        s.write(0x20068270, 0xA0)
        assert stream.read(s, 0x20068270) == 0
        assert 'IRQ lower 64' in s.irqs
        configure(s, pitch=0, bank=1)
        s.write(0x20068100, 8)
        frame(s, 60)
        assert get(s, 'batches') == 1 and get(s, 'frames') == 121
        frame(s)
        assert get(s, 'batches') == 2 and get(s, 'bytes') == 122*SIZE
        assert s.read(START, SIZE) == expected
        s.query('qom-set', {'path': INPUT, 'property':'finite-batches', 'value':0}, error=True)
        s.query('system_reset')
        frame(s, 62)
        assert get(s, 'frames') == get(s, 'batches') == 0
        configure(s); arm(s); frame(s)
        assert get(s, 'reason') == 'source'
        evidence.update(actual_raw_means=True, rows_and_padding=True, all_61_slots=True,
            no_early_completion=True, irq96_w1c=True, unchanged_commit_no_replay=True,
            native_zero_pitch_second_bank=True, readonly_counters=True, reset=True, command=s.command)
    with session(binary) as s:
        source(s)
        invalid = END-60*PITCH-512
        configure(s, destination=invalid); arm(s)
        s.access(f'memset {invalid:#x} {SIZE:#x} 0x5a')
        frame(s)
        assert get(s, 'reason') == 'destination' and get(s, 'frames') == 0
        assert s.read(invalid, SIZE) == b'\x5a'*SIZE
        assert stream.read(s, 0x20068270) == 0
        configure(s); s.write(0x20068100, 8); frame(s)
        assert get(s, 'frames') == 1
        s.write(0x2006A2D0, 0x141E); frame(s)
        assert get(s, 'reason') == 'configuration-changed' and get(s, 'batches') == 0
        s.write(0x2006A2D0, 0x0C1E); frame(s)
        assert get(s, 'frames') == 1  # no silent rearm after a changed descriptor
        s.write(0x20068100, 8); frame(s)
        assert get(s, 'frames') == 2
        s.write(0x2006800C, 0x10); frame(s, 62)
        assert get(s, 'frames') == 2 and get(s, 'batches') == 0
        arm(s, mask=0); s.irqs.clear(); frame(s, 61)
        assert get(s, 'batches') == 1 and stream.read(s, 0x20068270) == 0xA0
        assert 'IRQ raise 64' not in s.irqs
        s.write(0x20068260, 0xA0)
        assert 'IRQ raise 64' in s.irqs
        evidence.update(full_batch_preflight=True, changed_descriptor_requires_commit=True,
                        stop_cancels_partial=True, restart=True, masked_status_preserved=True)
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, default=host.DEFAULT_QEMU)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = host.verify_build(args.qemu.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        result = {'completed': False, 'binary_sha256': manifest['binary_sha256'],
                  'firmware_loaded': False, 'guest_instructions_executed': False}
        try:
            result.update(check(args.qemu), completed=True)
        except Exception as exc:
            result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
            raise
        finally:
            json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))
