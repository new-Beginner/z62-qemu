"""Firmware-free r9 preview DMA/IRQ/bounds/lifecycle checks."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import time
from unittest.mock import patch
import probe_z62_raw_stream as stream
from probe_z62_functional_raw import SLOTS
import run_z62_preview as host

OUTPUTS=((0xEAA20000,0xEAD59800,0xEAD59800,0xEB093000),
         (0xEBA3F800,0xEBC03800,0xEBDC7800,0xEBF8B800),
         (0xCFDD2200,0xCFF54400,0xD00D6600,0xCFDD2200))
GEOMETRY=((1920,1080,1920,0x226500),(1024,682,1024,0x12D400),(1024,680,1024,0xC1000))
BATCH_BYTES=4*sum(stride*h*3//2 for w,h,stride,uv in GEOMETRY)


@contextmanager
def session(binary,enabled=True):
    original=stream.host.configure_command
    def configure(command,*a,**kw):
        result=host.configure_command(original(command,*a,**kw),enabled)
        # This Windows build has TCG only, so qtest clock_step is unavailable.
        # Load an ARM infinite loop into each engine-local CPU address space.
        for cpu in range(4):
            result+=['-device',f'loader,addr=0x10020000,data=0xeafffffe,data-len=4,cpu-num={cpu}',
                     '-device',f'loader,addr=0x10020000,cpu-num={cpu}']
        return result
    with patch.object(stream.host,'configure_command',configure),stream.session(binary) as s: yield s


def get(s,name,path=None): return s.get('preview-'+name,path or s.master)
def read(s,address): return stream.read(s,address)
def advance(s):
    s.query('cont')
    try: time.sleep(.05)
    finally: s.query('stop')


def configure(s):
    stream.start(s)
    for i,address in enumerate(SLOTS): s.write(0x20380310+i*4,address)
    for ch,(w,h,stride,uv) in enumerate(GEOMETRY,3):
        base=0x20100400+ch*0x40
        for off,value in ((0,0x09000201),(0x10,stride),(0x14,stride),(0x20,(h<<16)|w),(0x28,uv)):
            s.write(base+off,value)
        for frame,address in enumerate(OUTPUTS[ch-3]): s.write(0x20102200+frame*64+ch*4,address)
    for address,value in ((0x20380048,0x05EA03EE),(0x20380300,0),(0x2038030C,2272),
        (0x20380020,0x1002),(0x20380008,1),(0x20100014,8),(0x20100004,1),
        (0x20102100,0x121),(0x20102600,0x305),(0x20102604,1002),(0x20102608,1)):
        s.write(address,value)


def new_raw(s):
    s.write(0x20068290,0x100)
    stream.frame(s)


def acknowledge(s):
    s.write(0x20100020,8)
    s.write(0x20380024,0x1002)


def expected_prefix(w,h):
    def tone(value):
        v=max(0,min(1,(value-64)/(4095-64)))
        return round(255*(12.92*v if v<=0.0031308 else 1.055*v**(1/2.4)-0.055))
    def rgb(x,y):
        sx=2+x*755//w*2;sy=2+y*501//h*2
        value=lambda x,y:(x*3+y*5+256)&4095
        return tone(value(sx,sy)),tone((value(sx+1,sy)+value(sx,sy+1)+1)//2),tone(value(sx+1,sy+1))
    yplane=bytes(max(16,min(235,((66*r+129*g+25*b+128)>>8)+16)) for r,g,b in (rgb(x,0) for x in range(32)))
    uv=bytearray()
    for x in range(0,32,2):
        cells=[rgb(x+dx,dy) for dy in range(2) for dx in range(2)]
        r,g,b=((sum(c[i] for c in cells)+2)//4 for i in range(3))
        uv.extend((max(16,min(240,((-38*r-74*g+112*b+128)>>8)+128)),
                   max(16,min(240,((112*r-94*g-18*b+128)>>8)+128))))
    return yplane,bytes(uv)


def fill_guards(s):
    for ch,(w,h,stride,uv) in enumerate(GEOMETRY):
        for address in set(OUTPUTS[ch]):
            for base,size in ((address,stride*h),(address+uv,stride*h//2)):
                s.access(f'memset {base-16:#x} {size+32:#x} 0xa5')


def check(binary):
    result={}
    with session(binary,False) as s:
        configure(s);new_raw(s);advance(s)
        assert get(s,'batches')==get(s,'outputs')==0
        assert read(s,0x20100020)==read(s,0x20380024)==0
        result['default_off']=True
    with session(binary) as s:
        configure(s);advance(s)
        assert get(s,'batches')==0  # register writes alone cannot complete work
        fill_guards(s)
        new_raw(s)
        assert get(s,'batches')==0
        advance(s)
        assert get(s,'reason')=='success',get(s,'reason')
        assert get(s,'batches')==1 and get(s,'outputs')==12 and get(s,'bytes')==BATCH_BYTES
        assert read(s,0x20100020)==8 and read(s,0x20380024)==0x1002
        assert 'IRQ raise 70' in s.irqs and 'IRQ raise 67' in s.irqs
        for ch,(w,h,stride,uv) in enumerate(GEOMETRY):
            yprefix,uvprefix=expected_prefix(w,h)
            for address in set(OUTPUTS[ch]):
                assert s.read(address,32)==yprefix,(ch,'Y',s.read(address,32).hex(),yprefix.hex())
                assert s.read(address+uv,32)==uvprefix,(ch,'UV')
                for base,size in ((address,stride*h),(address+uv,stride*h//2)):
                    assert s.read(base-16,16)==b'\xa5'*16
                    assert s.read(base+size,16)==b'\xa5'*16
        new_raw(s);advance(s)
        assert get(s,'batches')==1 and get(s,'blocked')>0
        s.write(0x20100014,0);s.write(0x20380020,0);acknowledge(s);s.irqs.clear();advance(s)
        assert get(s,'batches')==2
        assert read(s,0x20100020)==8 and read(s,0x20380024)==0x1002
        assert 'IRQ raise 70' not in s.irqs and 'IRQ raise 67' not in s.irqs
        s.write(0x20100014,8);s.write(0x20380020,0x1002)
        assert 'IRQ raise 70' in s.irqs and 'IRQ raise 67' in s.irqs
        acknowledge(s)
        new_raw(s);s.write(0x20102100,0);advance(s)
        assert get(s,'batches')==2 and get(s,'cancelled')>0
        s.write(0x20102100,0x121);advance(s)
        assert get(s,'batches')==3
        assert not (read(s,0x20100020)&4)  # statistics command bank0 was not completed
        stream.frame(s,path=s.slave)
        assert get(s,'batches',s.slave)==0
        s.query('qom-set',{'path':s.master,'property':'preview-batches','value':0},error=True)
        acknowledge(s)
        s.write(0x20380020,0x014A0002)
        s.write(0x203800F0,0xFC400)
        for address in (0x20380054,0x20380060,0x2038006C): s.write(address,1)
        advance(s);assert get(s,'drains')==0
        s.write(0x20380078,1);advance(s)
        assert get(s,'drains')==1 and read(s,0x20380024)==0x014A0000
        assert get(s,'batches')==3
        s.write(0x20380024,0x014A0000)
        for address,value in ((0x20380048,0x0014000E),(0x20380300,2),(0x2038030C,32),
                              (0x20380310,SLOTS[0]),(0x203803E8,2),(0x20380410,0),(0x20380420,0),(0x20380008,1)):
            s.write(address,value)
        advance(s)
        assert get(s,'flushes')==1 and read(s,0x20380024)==2
        assert get(s,'batches')==3
        s.query('system_reset');advance(s)
        assert all(get(s,n)==0 for n in ('attempts','batches','outputs','bytes','blocked','drains','flushes'))
        assert read(s,0x20100020)==read(s,0x20380024)==0
        result.update(native_pixels=True,three_geometries=True,all_twelve_outputs=True,guards_preserved=True,
            irq99_irq102=True,masked_pending=True,w1c=True,backpressure=True,cancel_restart=True,
            no_statistics_completion=True,slave_isolation=True,readonly=True,reset=True,
            four_channel_drain=True,actual_dummy_read_flush=True,command=s.command)
    with session(binary) as s:
        configure(s)
        first=OUTPUTS[0][0]
        s.access(f'memset {first:#x} 0x100 0xa5')
        s.write(0x20102200+3*64+4*4,0xC1800000)
        new_raw(s);advance(s)
        assert get(s,'reason')=='destination' and get(s,'outputs')==0
        assert s.read(first,256)==b'\xa5'*256
        assert read(s,0x20100020)==read(s,0x20380024)==0
        s.write(0x20102200+3*64+4*4,OUTPUTS[0][0]+16)
        new_raw(s);advance(s)
        assert get(s,'reason')=='overlap' and get(s,'outputs')==0
        s.write(0x20102200+3*64+4*4,OUTPUTS[1][3])
        s.write(0x20380310,SLOTS[0]+16)
        new_raw(s);advance(s)
        assert get(s,'reason')=='source' and get(s,'outputs')==0
        assert s.read(first,256)==b'\xa5'*256
        result.update(last_destination_preflight=True,overlap_rejected=True,unproduced_source_rejected=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qemu',type=Path,default=host.DEFAULT_QEMU)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    manifest=host.verify_build(args.qemu.resolve())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as handle:
        result={'completed':False,'binary_sha256':manifest['binary_sha256'],
                'firmware_loaded':False,'synthetic_arm_loops_executed':True}
        try: result.update(check(args.qemu),completed=True)
        except Exception as exc:
            result['failure']={'type':type(exc).__name__,'message':str(exc)};raise
        finally: json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2))
