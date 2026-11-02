"""Native firmware-free bank0 data, provenance, IRQ and lifecycle checks."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import probe_z62_preview as preview
import probe_z62_continuous_stats as statistics
import run_z62_preview_results_format as parent

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'qemu/z62-grid/observed-profile.json'
FIXTURE_SHA='f12c8922e5b66667c7567ba7c0d12a26418e75c1ee1a8399e9ac9b24b289fc55'
PARAMETER=0xC2400000
RGB_BASE=0x88EDF000
RGB_PITCH=0x36000


def observed():
    data=FIXTURE.read_bytes()
    if hashlib.sha256(data).hexdigest()!=FIXTURE_SHA: raise ValueError('Grid fixture changed')
    return json.loads(data)


@contextmanager
def session(binary,enabled=True):
    old=preview.host.configure_command
    def configure(command,*a,**kw):
        result=old(command,*a,**kw)
        result=statistics.host.configure_command(result,True)
        if enabled: result+=['-global','nikon-z72-boot-config.z62-grid-process=on']
        return result
    with patch.object(preview.host,'configure_command',configure),preview.session(binary) as s:
        yield s


def get(s,name,path=None): return s.get('grid-'+name,path or s.master)
def read(s,address): return preview.read(s,address)


def configure(s):
    f=observed()
    for port in f['ports']:
        for i,v in enumerate(port['words']): s.write(int(port['address'],16)+i*4,v)
    data=bytearray.fromhex(f['unit53_parameters_0a0'])
    data[0x8c:0x94]=bytes.fromhex('efbeaddebeab0df0')
    s.access(f'write {PARAMETER:#x} {len(data):#x} 0x{data.hex()}')
    for i,v in enumerate(f['unit53_registers']): s.write(0x201009C0+i*4,PARAMETER if i==4 else v)
    for frame,(slot,dst) in enumerate(zip(f['source_slots'],f['outputs'])):
        s.write(0x20102200+frame*64+4,RGB_BASE+slot*RGB_PITCH)
        s.write(0x20102200+frame*64+8,int(dst,16))
        s.access(f'memset {int(dst,16)-16:#x} {3840+32:#x} 0xa5')
    for address,value in ((0x20100004,1),(0x20100010,0x10),(0x20100014,4),
                          (0x20102000,f['control']),(0x20102640,f['command'][0]),
                          (0x20102644,f['command'][1]),(0x20102648,f['command'][2])):
        s.write(address,value)


def input_bytes(slot,channel,shift=0):
    raw=bytearray(b'\xa5'*5120)
    for y in range(40):
        for x in range(60):
            value=(111,527,2000)[channel]+17*slot+3*x+5*y+shift
            raw[y*128+x*2:y*128+x*2+2]=value.to_bytes(2,'little')
    return bytes(raw)


def fill_inputs(s,shift=0):
    hashes={}
    for slot in observed()['source_slots']:
        for c,offset in enumerate((0,0x12000,0x24000)):
            raw=input_bytes(slot,c,shift)
            p=RGB_BASE+slot*RGB_PITCH+offset
            s.access(f'write {p:#x} {len(raw):#x} 0x{raw.hex()}')
            assert s.read(p,len(raw))==raw
            hashes[p]=hashlib.sha256(raw).hexdigest()
    return hashes


def pulse(s,slot,path=None):
    for level in (1,0): s.access(f'set_irq_in {path or s.master} z62-grid-source {slot} {level}')


def supplied(s):
    for slot in observed()['source_slots']: pulse(s,slot)


def acknowledge(s):
    s.write(0x20100020,4)
    s.write(0x2010001C,0x10)


def expected(slot,shift=0):
    raw=bytearray(3840)
    for y in range(40):
        for x in range(0,60,2):
            a=(111+527+2000+3*(17*slot+3*x+5*y+shift)+1)//3
            b=(111+527+2000+3*(17*slot+3*(x+1)+5*y+shift)+1)//3
            off=y*96+x//2*3
            raw[off:off+3]=bytes((a&255,(a>>8)|((b&15)<<4),b>>4))
    return bytes(raw)


def verify_outputs(s,shift=0):
    for slot,value in zip(observed()['source_slots'],observed()['outputs']):
        p=int(value,16)
        assert s.read(p,3840)==expected(slot,shift)
        assert s.read(p-16,16)==s.read(p+3840,16)==b'\xa5'*16


def check(binary):
    result={}
    with session(binary,False) as s:
        assert get(s,'groups')==0
        configure(s);fill_inputs(s);supplied(s);preview.advance(s)
        assert get(s,'groups')==0 and read(s,0x20100020)==read(s,0x2010001C)==0
        result['default_off']=True
    with session(binary) as s:
        configure(s);hashes=fill_inputs(s);preview.advance(s)
        assert get(s,'groups')==0  # RAM contents alone do not prove source supply.
        supplied(s)
        assert read(s,0x201009C0)==3
        preview.advance(s)
        assert get(s,'groups')==1 and get(s,'outputs')==4 and get(s,'bytes')==15360
        assert read(s,0x20100020)==4 and read(s,0x2010001C)==0x10
        verify_outputs(s)
        for p,h in hashes.items(): assert hashlib.sha256(s.read(p,5120)).hexdigest()==h
        assert s.read(PARAMETER+0x8c,8)==bytes.fromhex('efbeaddebeab0df0')
        s.irqs.clear();s.write(0x20100020,4)
        assert 'IRQ lower 70' not in s.irqs
        s.write(0x2010001C,0x10);assert 'IRQ lower 70' in s.irqs
        preview.advance(s);assert get(s,'groups')==1  # no stale replay after ACK
        pulse(s,3);preview.advance(s);assert get(s,'groups')==1  # unselected source is not new input
        events=get(s,'source-events')
        s.access(f'set_irq_in {s.master} z62-grid-source 5 1')
        s.access(f'set_irq_in {s.master} z62-grid-source 5 1')
        assert get(s,'source-events')==events+1
        s.access(f'set_irq_in {s.master} z62-grid-source 5 0')
        s.write(0x20100010,0);s.write(0x20100014,0)
        supplied(s);s.irqs.clear();preview.advance(s)
        assert get(s,'groups')==2 and read(s,0x20100020)==4 and read(s,0x2010001C)==0x10
        assert 'IRQ raise 70' not in s.irqs
        s.write(0x20100014,4);assert 'IRQ raise 70' in s.irqs
        s.write(0x20100020,4);assert 'IRQ lower 70' in s.irqs
        s.write(0x20100010,0x10);assert s.irqs[-1]=='IRQ raise 70'
        first=int(observed()['outputs'][0],16)
        s.access(f'memset {first:#x} 0x20 0xa6')
        fill_inputs(s,9);supplied(s);preview.advance(s)
        assert get(s,'groups')==2 and get(s,'blocked')>0
        assert s.read(first,32)==b'\xa6'*32
        s.write(0x2010001C,0x10);preview.advance(s)
        assert get(s,'groups')==3;verify_outputs(s,9)
        acknowledge(s);supplied(s);s.write(0x20102648,0);preview.advance(s)
        assert get(s,'groups')==3 and read(s,0x20100020)==read(s,0x2010001C)==0
        s.write(0x20102648,3);preview.advance(s);assert get(s,'groups')==3
        supplied(s);preview.advance(s);assert get(s,'groups')==4
        pulse(s,0,s.slave);assert get(s,'groups',s.slave)==get(s,'source-events',s.slave)==0
        s.query('qom-set',{'path':s.master,'property':'grid-groups','value':0},error=True)
        s.query('system_reset');preview.advance(s)
        assert all(get(s,n)==0 for n in ('groups','outputs','bytes','rejected','blocked','source-events'))
        assert read(s,0x20100020)==read(s,0x2010001C)==0
        result.update(actual_four_outputs=True,full_sample_oracle=True,input_planes_unchanged=True,
            metadata_independent_and_preserved=True,source_provenance_required=True,
            no_stale_replay=True,per_source_w1c=True,masking=True,backpressure=True,
            stop_requires_fresh_source=True,slave_isolation=True,readonly=True,reset=True,command=s.command)
    with session(binary) as s:
        cases=(('bad-parameter-pointer',lambda:s.write(0x201009D0,0x20100000)),
               ('invalid-last-output',lambda:s.write(0x20102200+3*64+8,0xC18647D8)),
               ('overlapping-output',lambda:s.write(0x20102200+64+8,int(observed()['outputs'][0],16)+16)),
               ('unowned-source',lambda:s.write(0x20102204,0xC18647D8)),
               ('bad-geometry',lambda:s.write(0x201004A0,0x0028003E)),
               ('bad-last-sample',lambda:s.write(RGB_BASE+2*RGB_PITCH+0x24000+39*128+116,0x10000000)))
        rejected=[]
        for name,change in cases:
            s.query('system_reset');configure(s);fill_inputs(s);supplied(s);change();preview.advance(s)
            assert get(s,'groups')==get(s,'outputs')==0,name
            assert read(s,0x20100020)==read(s,0x2010001C)==0,name
            assert s.read(int(observed()['outputs'][0],16),32)==b'\xa5'*32,name
            rejected.append(name)
        result['rejected_without_output_or_completion']=rejected
    with session(binary) as s:
        configure(s)
        statistics.configure(s);statistics.arm(s)
        for _ in range(6):
            s.write(0x20068270,0xA0)
            statistics.source(s);s.write(0x20068100,8);statistics.frame(s)
        producer_counts={'raw':s.get('raw-accepted'),'statistics':statistics.get(s,'frames'),
                         'source_events':get(s,'source-events')}
        assert producer_counts=={'raw':6,'statistics':6,'source_events':6},producer_counts
        assert get(s,'groups')==0  # numerical timer has not run yet
        preview.advance(s)
        assert get(s,'groups')==1 and get(s,'outputs')==4
        planes=statistics.expected_outputs()[2:]
        golden=bytearray(3840)
        for y in range(40):
            for x in range(0,60,2):
                values=[]
                for xx in (x,x+1):
                    v=[int.from_bytes(p[y*128+xx*2:y*128+xx*2+2],'little') for p in planes]
                    values.append((sum(v)+1)//3)
                a,b=values;off=y*96+x//2*3
                golden[off:off+3]=bytes((a&255,(a>>8)|((b&15)<<4),b>>4))
        for value in observed()['outputs']:
            assert s.read(int(value,16),3840)==golden
        acknowledge(s)
        s.write(0x20068270,0xA0);s.write(0x20069A08,1);s.submit();statistics.frame(s)
        preview.advance(s)
        assert statistics.get(s,'frames')==6 and get(s,'source-events')==6 and get(s,'groups')==1
        assert read(s,0x20100020)==read(s,0x2010001C)==0
        result.update(real_raw_to_rgb_dma_to_grid=True,all_six_source_notifications=True,
                      real_producer_counts=producer_counts,
                      independent_raw_scene_oracle=True,failed_raw_does_not_notify_or_replay=True,
                      repeated_high_ignored=True,unselected_source_ignored=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--parent',action='store_true')
    args=parser.parse_args()
    if args.parent:
        binary=(args.qemu or parent.DEFAULT_QEMU).resolve();m=parent.verify_build(binary)
    else:
        import run_z62_grid as host
        binary=(args.qemu or host.DEFAULT_QEMU).resolve();m=host.verify_build(binary)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as f:
        result={'schema':1,'completed':False,'binary_sha256':m['binary_sha256'],
                'firmware_loaded':False,'algorithm_level':'C','camera_accessed':False,'parent_under_test':args.parent}
        try: result.update(check(binary),completed=True)
        except Exception as exc:
            result['failure']={'type':type(exc).__name__,'message':str(exc)};raise
        finally: json.dump(result,f,indent=2)
    print(json.dumps(result),flush=True)
