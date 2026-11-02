"""Native r18 data, ring ownership, IRQ and rejection tests without firmware."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import struct
from unittest.mock import patch

import probe_z62_raw_stream as raw
import probe_z62_finite_stats as finite
import run_z62_continuous_stats as host

INPUT = '/machine/master-input'
BASES = (0x88E37000, 0x88E73000, 0x88EDF000, 0x88EF1000, 0x88F03000)
PITCHES = (0xA000, 0x12000, 0x36000, 0x36000, 0x36000)
SIZES = (9600, 1280, 5120, 5120, 5120)


@contextmanager
def session(binary, enabled=True, legacy=False):
    original = raw.host.configure_command
    def configure(command, *a, **kw):
        result = host.configure_command(original(command, *a, **kw), enabled)
        if legacy:
            result += ['-global', 'nikon-z72-input-config.functional-finite-stats=on']
        return result
    with patch.object(raw.host, 'configure_command', configure), raw.session(binary, enabled=False) as s:
        yield s


def get(s, prop, path=INPUT):
    return s.get('continuous-'+prop, path)


def configure(s, bank=0):
    for ch, (base, pitch) in enumerate(zip(BASES, PITCHES)):
        mmio = 0x2006A400+ch*256
        values = {0x14:3, 0x18:1, 0x24:0, 0x3c:bank, 0x40:1, 0x44:0, 0x48:5, 0x4c:0,
                  0x50:base, 0x60:base, 0x80:pitch}
        if ch >= 2:
            values.update({offset:base for offset in (0x54,0x58,0x5c,0x64,0x68,0x6c)})
        for offset, value in values.items():
            s.write(mmio+offset, value)
    geometry = {0x2204:1, 0x2268:0x14, 0x226c:0xa, 0x2270:0x42042, 0x2274:0x42042,
                0x2278:0x141e, 0x22bc:3, 0x22c0:0x10d1b, 0x22c4:6, 0x22c8:2,
                0x22cc:0xc832, 0x22d0:0x141e}
    for ch in range(3):
        b = 0x22d4+ch*0x18
        geometry.update({b:(ch+1)*0x100+3,b+4:0x10e39,b+8:0x26,b+12:0x18,b+16:0x6018,b+20:0x283c})
    for offset, value in geometry.items():
        s.write(0x20068000+offset, value)


def arm(s, mask=0xA0):
    s.write(0x20068010, 0x10)
    s.write(0x20068260, mask)
    s.write(0x20068008, 0x10)
    s.write(0x20068100, 8)


def frame(s, level=None, path=INPUT):
    for value in ((1, 0) if level is None else (level,)):
        s.access(f'set_irq_in {path} finite-frame 0 {value}')


def source(s):
    s.configure()
    s.submit()


def expected_outputs():
    # Independent scene equations, no unpacking copied from the C device.
    result = [bytearray(n) for n in SIZES]
    def scene(x, y):
        return (x*3+y*5+256) & 4095
    for width, height in ((30,20),(60,40)):
        for y in range(height):
            for x in range(width):
                sums, total, count = [0,0,0], 0, 0
                for sy in range(y*503//height,(y+1)*503//height):
                    for sx in range(x*757//width,(x+1)*757//width):
                        r,g1,g2,b = scene(2*sx,2*sy),scene(2*sx+1,2*sy),scene(2*sx,2*sy+1),scene(2*sx+1,2*sy+1)
                        sums[0]+=r; sums[1]+=(g1+g2+1)//2; sums[2]+=b
                        total+=r+g1+g2+b; count+=1
                if width == 30:
                    struct.pack_into('<4I',result[0],y*480+x*16,*sums,count)
                    struct.pack_into('<H',result[1],y*64+x*2,(total+2*count)//(4*count))
                else:
                    for ch in range(3):
                        struct.pack_into('<H',result[ch+2],y*128+x*2,(sums[ch]+count//2)//count)
    return [bytes(p) for p in result]


def fill(s):
    s.access('memset 0x88e37000 0x1ec000 0xa5')


def check(binary):
    expected = expected_outputs()
    with session(binary, False) as s:
        configure(s); arm(s); source(s); frame(s)
        assert get(s,'frames') == 0
    with session(binary) as s:
        configure(s); fill(s); arm(s); frame(s)
        assert get(s,'frames') == 0 and get(s,'reason') == 'source'
        source(s)
        s.verify_slots(raw.raw.raw.pattern(), guards=False)
        frame(s,level=1)
        assert get(s,'frames') == 1 and get(s,'index') == 1
        assert raw.read(s,0x20068270) == 0x20 and 'IRQ raise 64' in s.irqs
        frame(s,level=1)
        assert get(s,'frames') == 1
        frame(s,level=0)
        source(s); frame(s)
        assert get(s,'frames') == 1 and get(s,'blocked') == 1
        assert s.read(BASES[1]+PITCHES[1],SIZES[1]) == b'\xa5'*SIZES[1]
        s.write(0x20068270,0x20); frame(s)
        assert get(s,'frames') == 2 and get(s,'index') == 2
        for index in range(2,6):
            s.write(0x20068270,0xA0); source(s); s.write(0x20068100,8); frame(s)
            assert get(s,'frames') == index+1 and get(s,'index') == (index+1)%6
        assert get(s,'batches') == 1 and get(s,'bytes') == 6*sum(SIZES)
        assert raw.read(s,0x20068270) == 0xA0
        for ch in range(5):
            for slot in range(6):
                address=BASES[ch]+slot*PITCHES[ch]
                assert s.read(address,SIZES[ch]) == expected[ch], (ch,slot)
                assert s.read(address+SIZES[ch],16) == b'\xa5'*16
        s.write(0x20068270,0xA0); frame(s)
        assert get(s,'frames') == 6  # unchanged source cannot replay
        s.write(0x20068260,0); s.irqs.clear(); source(s); frame(s)
        assert get(s,'frames') == 7 and raw.read(s,0x20068270) == 0x20
        assert 'IRQ raise 64' not in s.irqs
        s.write(0x20068260,0xA0)
        assert 'IRQ raise 64' in s.irqs
        s.write(0x20068270,0xA0)
        accepted=s.get('raw-accepted'); rejected=s.get('raw-rejected')
        s.write(0x20069A08,1); s.submit(); frame(s)
        assert s.get('raw-accepted') == accepted and s.get('raw-rejected') == rejected+1
        assert get(s,'frames') == 7 and raw.read(s,0x20068270) == 0
        configure(s,bank=1); s.write(0x20068100,8); source(s); frame(s)
        assert get(s,'frames') == 8 and get(s,'index') == 1
        s.write(0x20068270,0xA0); s.write(0x2006800C,0x10); source(s); frame(s)
        assert get(s,'frames') == 8
        arm(s); frame(s)
        assert get(s,'frames') == 8  # restart requires new RAW
        source(s); frame(s)
        assert get(s,'frames') == 9
        s.query('qom-set', {'path':INPUT,'property':'continuous-frames','value':0}, error=True)
        frame(s,path='/machine/slave-input')
        assert get(s,'frames','/machine/slave-input') == 0
        s.query('system_reset'); frame(s)
        assert all(get(s,n) == 0 for n in ('frames','batches','bytes','blocked','source','index'))
    for address,value,reason in ((0x2006A548,6,'descriptor'),(0x2006A2E8,0x283B,'geometry'),
                                 (0x2006A550,0x81000000,'destination'),(0x2006A63C,2,'descriptor')):
        with session(binary) as s:
            configure(s); fill(s); arm(s); source(s); s.write(address,value); frame(s)
            assert get(s,'frames') == 0 and get(s,'reason') == reason
            assert raw.read(s,0x20068270) == 0
            assert s.read(BASES[0],32) == b'\xa5'*32
    with session(binary) as s:
        configure(s); fill(s); arm(s); source(s); frame(s); s.write(0x20068270,0xA0)
        s.write(0x2006A53C,1); source(s); frame(s)
        assert get(s,'frames') == 1 and get(s,'reason') == 'configuration-changed'
        assert raw.read(s,0x20068270) == 0
    with session(binary) as s:
        configure(s); arm(s); s.configure(); s.write(0x20069A50,BASES[0]); s.submit()
        before=s.read(BASES[0],32); frame(s)
        assert get(s,'frames') == 0 and get(s,'reason') == 'overlap'
        assert s.read(BASES[0],32) == before and raw.read(s,0x20068270) == 0
    with session(binary,legacy=True) as s:
        finite.configure(s); finite.arm(s); source(s); finite.frame(s,61)
        assert get(s,'frames') == 0 and finite.get(s,'frames') == 61
        assert s.read(finite.START,finite.SIZE) == finite.expected_grid()
    return {'actual_five_output_dma':True,'independent_scene_equations':True,'six_slots_and_guards':True,
            'w1c_backpressure':True,'mask_latching':True,'no_unchanged_source_replay':True,
            'unchanged_commit_preserves_cursor':True,'bank_commit_restarts_cursor':True,
            'invalid_profile_no_data_or_completion':True,'uncommitted_change_rejected':True,
            'source_overlap_rejected':True,'legacy_finite_coexistence':True,'stop_restart':True,
            'failed_raw_no_statistics_completion':True,
            'readonly':True,'slave_isolation':True,'reset':True}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu',type=Path,default=host.DEFAULT_QEMU)
    parser.add_argument('--unextended-parent',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    verifier=host.parent.verify_build if args.unextended_parent else host.verify_build
    manifest=verifier(args.qemu.resolve())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    result={'completed':False,'binary_sha256':manifest['binary_sha256'],'firmware_loaded':False,
            'guest_instructions_executed':False,'camera_accessed':False}
    with args.output.open('x',encoding='utf-8') as handle:
        try:
            result.update(check(args.qemu),completed=True)
        except Exception as exc:
            result['failure']={'type':type(exc).__name__,'message':str(exc)}
            raise
        finally:
            json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2))
