"""Actual native RAW ownership, MAIN/WORK DMA and result lifecycle on r59."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from unittest.mock import patch

import probe_z62_preview_results as results
import run_z62_video_isp as host

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'analysis/z62-frame-source-r57/source-1/pipeline.json'
FIXTURE_SHA='46cb176ab2a3b30102450cd0639c1510e8028f39597570e325dcb905b3a5b433'
MAIN_Y=1520*846; MAIN_BYTES=MAIN_Y*3//2; WORK_BYTES=1520*423


def require(value,message):
    if not value: raise ValueError(message)


def observed():
    data=FIXTURE.read_bytes()
    require(hashlib.sha256(data).hexdigest()==FIXTURE_SHA,'Original video fixture differs')
    return next(c for c in json.loads(data)['captures'] if c['selector_phase_observed']==1)


@contextmanager
def session(binary,enabled=True,origin=(0,76)):
    previous=results.preview.host.configure_command
    def configure(command,*args,**kwargs):
        values=list(previous(command,*args,**kwargs))
        if enabled:
            values+=['-global','nikon-z72-boot-config.z62-video-isp=on',
                     '-global','nikon-z72-boot-config.z62-video-origin-x='+str(origin[0]),
                     '-global','nikon-z72-boot-config.z62-video-origin-y='+str(origin[1])]
        return values
    with patch.object(results.preview.host,'configure_command',configure),results.session(binary) as machine:
        yield machine


def configure_video(s):
    results.preview.configure(s);results.configure_units(s)
    capture=observed()
    # Use actual movie packets, rather than a later photo-format variant.
    for i,off in enumerate((0x9e0,0x940,0xba0)):
        row=next(u for u in capture['unit_parameters'] if u['offset']==hex(off))
        data=bytearray.fromhex(row['payload_candidate']['raw'])
        data[0x8c:0x94]=bytes.fromhex('efbeaddebeab0df0')
        for j in range(0,160,4): s.write(results.PARAMETERS[i]+j,int.from_bytes(data[j:j+4],'little'))
        registers=list(row['registers']);registers[4]=results.PARAMETERS[i]
        for j,value in enumerate(registers): s.write(0x20100000+off+j*4,value)
    for row in capture['ports']:
        for i,value in enumerate(row['words']): s.write(0x20100400+row['index']*64+i*4,value)
    controls=struct.unpack('<256I',bytes.fromhex(capture['core_controls_400']))
    for offset in (0x100,0x110,0x114): s.write(0x20102000+offset,controls[offset//4])
    for table in capture['map_tables']:
        base=int(table['address'],16)
        for slot,row in enumerate(table['rows']):
            for i,value in enumerate(row): s.write(base+slot*64+i*4,value)
    paired=struct.unpack('<512I',bytes.fromhex(capture['paired_raw_800']))
    for i,value in enumerate(paired): s.write(0x20380000+i*4,value)
    for offset,value in ((0x20100004,1),(0x20100010,0x61),(0x20100014,8),
                         (0x20102600,0x300),(0x20102604,846),(0x20102608,3),(0x20380008,1)):
        s.write(offset,value)


def geometry():
    c=observed();raw=struct.unpack('<512I',bytes.fromhex(c['paired_raw_800']))
    outputs=[]
    for f,row in enumerate(c['map_tables'][0]['rows']):
        previews=[]
        for port in (3,4,5):
            p=c['ports'][port]['words'];previews.append((row[port],p[8]&0x7fff,p[8]>>16,p[4],p[10]))
        outputs.append({'main':raw[0x488//4+f],'work':raw[0x430//4+f],'preview':previews})
    return outputs


def regions():
    spans=set()
    for row in geometry():
        spans.add((row['main'],MAIN_BYTES));spans.add((row['work'],2*WORK_BYTES))
        for address,_,h,stride,uv in row['preview']:
            spans.add((address,stride*h));spans.add((address+uv,stride*h//2))
    return sorted(spans)


def fill_guards(s):
    for address,size in regions(): s.access(f'memset {address-16:#x} {size+32:#x} 0xa5')


def guards(s,unchanged=False,full=False):
    for address,size in regions():
        require(s.read(address-16,16)==b'\xa5'*16 and s.read(address+size,16)==b'\xa5'*16,'Video DMA escaped bounds')
        if unchanged:
            require(s.read(address,32)==s.read(address+size-32,32)==b'\xa5'*32,'Rejected video wrote pixels')
            if full: require(s.read(address,size)==b'\xa5'*size,'Late rejection partially published DMA')


def tone(value):
    v=max(0,min(1,(value-64)/(4095-64)))
    return round(255*(12.92*v if v<=.0031308 else 1.055*v**(1/2.4)-.055))


def main_pixel(x,y):
    sx=4+(x//2)*2;sy=80+(y//2)*2
    sample=lambda a,b:(a*3+b*5+256)&4095
    r,g,b=tone(sample(sx,sy)),tone((sample(sx+1,sy)+sample(sx,sy+1)+1)//2),tone(sample(sx+1,sy+1))
    return max(16,min(235,((66*r+129*g+25*b+128)>>8)+16)),\
        max(16,min(240,((-38*r-74*g+112*b+128)>>8)+128)),\
        max(16,min(240,((112*r-94*g-18*b+128)>>8)+128))


def expected_work():
    output=bytearray(2*WORK_BYTES)
    for y in range(423):
        for x in range(754):
            sx=4+x*2;sy=80+y*2
            r=(sx*3+sy*5+256)&4095;g1=((sx+1)*3+sy*5+256)&4095
            g2=(sx*3+(sy+1)*5+256)&4095;b=((sx+1)*3+(sy+1)*5+256)&4095
            offset=y*1520+x*2
            struct.pack_into('<H',output,offset,(r+g1+g2+b+2)//4)
            struct.pack_into('<h',output,WORK_BYTES+offset,(r+b+1)//2-(g1+g2+1)//2)
    return output


def pixels(s):
    expected=expected_work();seen=set()
    for row in geometry():
        address=row['main']
        if address not in seen:
            seen.add(address)
            for y in (0,844):
                require(s.read(address+y*1520,32)==bytes(main_pixel(x,y)[0] for x in range(32)),'MAIN source prefix differs')
                uv=bytearray()
                for x in range(0,32,2): uv.extend(main_pixel(x,y)[1:])
                require(s.read(address+MAIN_Y+(y//2)*1520,32)==uv,'MAIN chroma differs')
        if row['work'] not in seen:
            seen.add(row['work'])
            require(s.read(row['work'],2*WORK_BYTES)==expected,'Computed WORK plane differs from independent oracle')
        for address,w,h,stride,uv in row['preview']:
            require(s.read(address,32)==bytes(main_pixel(x*1508//w,0)[0] for x in range(32)),'Preview did not use MAIN')
            chroma=bytearray()
            for x in range(0,32,2): chroma.extend(main_pixel((x//2)*754//(w//2)*2,0)[1:])
            require(s.read(address+uv,32)==chroma,'Preview chroma differs')
    guards(s)


def get(s,name,path=None): return s.get('video-'+name,path or s.master)


def diagnose(binary):
    host.verify_build(binary)
    with session(binary) as s:
        configure_video(s);fill_guards(s);results.preview.new_raw(s);results.preview.advance(s)
        c=observed();expected=struct.unpack('<512I',bytes.fromhex(c['paired_raw_800']))
        offsets=(0x48,0x88,0x8c,0x94,0x9c,0xa8,0x10c,0x138,0x13c,0x140,0x300,0x30c,
                 0x3d8,0x400,0x404,0x408,0x40c,0x410,0x414,0x420,0x424,0x428,0x42c,0x470,0x4c8)
        offsets=(*offsets,*range(0x500,0x800,4))
        raw_differences=[{'offset':hex(o),'expected':hex(expected[o//4]),'actual':hex(v)}
            for o in offsets if (v:=results.preview.read(s,0x20380000+o))!=expected[o//4]]
        ports=[]
        for port in (3,4,5,8):
            actual=[results.preview.read(s,0x20100400+port*64+j*4) for j in range(13)]
            ports.append({'port':port,'differences':[(j,hex(w),hex(actual[j]))
                for j,w in enumerate(c['ports'][port]['words']) if w!=actual[j]]})
        units=[]
        for i,off in enumerate((0x9e0,0x940,0xba0)):
            registers=[results.preview.read(s,0x20100000+off+j*4) for j in range(6)]
            actual=struct.unpack('<40I',s.read(registers[4],160))
            original=next(u for u in c['unit_parameters'] if u['offset']==hex(off))
            want=struct.unpack('<40I',bytes.fromhex(original['payload_candidate']['raw']))
            units.append({'unit':hex(off),'registers':[hex(v) for v in registers],
                'parameter_differences':[(hex(j*4),hex(w),hex(actual[j])) for j,w in enumerate(want)
                    if j*4 not in (0x8c,0x90,0x9c) and w!=actual[j]]})
        links=[]
        for f in range(4):
            r=lambda o:results.preview.read(s,0x20380000+o+f*4)
            m,u,w,v=r(0x488),r(0x498),r(0x430),r(0x440)
            links.append({'phase':f,'map_main':hex(results.preview.read(s,0x20102200+f*64+8*4)),
                'paired_main':hex(m),'main_delta':u-m,'work_delta':v-w,
                'main_mirror':r(0x4a8)==m and r(0x4b8)==u,
                'work_mirror':r(0x450)==w and r(0x460)==v})
        return {'schema':1,'diagnostic_completed':True,'camera_accessed':False,
            'video':{n:get(s,n) for n in ('batches','source-captures','reason')},
            'core':{hex(o):hex(results.preview.read(s,0x20100000+o)) for o in
                    (0x2100,0x2110,0x2114,0x2600,0x2604,0x2608)},
            'paired_differences':raw_differences,'ports':ports,'units':units,'links':links}


def invalid_start(binary):
    for x,y in ((None,None),(1,76),(0,4098)):
        command=[str(binary),'-M','nikon-z62-dual-lab','-smp','4,maxcpus=5','-display','none','-serial','none',
                 '-monitor','none','-nic','none','-S','-global','nikon-z72-boot-config.z62-preview=on',
                 '-global','nikon-z72-boot-config.z62-preview-results=on',
                 '-global','nikon-z72-boot-config.z62-video-isp=on']
        if x is not None: command+=['-global','nikon-z72-boot-config.z62-video-origin-x='+str(x)]
        if y is not None: command+=['-global','nikon-z72-boot-config.z62-video-origin-y='+str(y)]
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
        require(result.returncode!=0 and 'explicit even' in result.stderr,'Invalid software origin was accepted')


def check(binary,parent_negative=False):
    build=(host.parent.verify_build if parent_negative else host.verify_build)(binary)
    result={'schema':1,'binary_sha256':build['binary_sha256'],'algorithm_level':'C','firmware_executed':False,'camera_accessed':False,
            'physical_work_format_verified':False,'original_isp_equivalent':False,'parent_negative':parent_negative}
    with session(binary,False) as s:
        configure_video(s);fill_guards(s);results.preview.new_raw(s);results.preview.advance(s)
        require(results.preview.get(s,'batches')==0 and results.preview.read(s,0x2010001c)==0,'Default path accepted movie recipe')
        guards(s,True)
        result['default_off_rejects_video']=True
    if parent_negative:
        result.update(completed=True,new_video_implemented=False)
        return result
    invalid_start(binary)
    with session(binary) as s:
        configure_video(s);fill_guards(s);results.preview.advance(s)
        require(get(s,'batches')==0,'Configuration manufactured video pixels')
        results.preview.new_raw(s)
        # A post-DMA CPU write must not replace the source already owned by video.
        for address in results.preview.SLOTS: s.access(f'memset {address:#x} {2272*1006:#x} 0')
        results.preview.advance(s)
        result['first_diagnostic']={n:get(s,n) for n in ('batches','rejected','source-captures','source-rejected','reason')}
        require(get(s,'batches')==1,'Video transaction failed: '+str(result['first_diagnostic']))
        require(get(s,'main-bytes')==4*MAIN_BYTES and get(s,'work-bytes')==8*WORK_BYTES,'Committed output sizes differ')
        require(results.preview.get(s,'outputs')==12,'Twelve preview outputs were not committed')
        require(results.preview.read(s,0x2010001c)==0x61 and results.preview.read(s,0x20100020)==8,'Result/command latches differ')
        require(results.preview.read(s,0x20380024)&0x1002==0x1002,'Paired result latch missing')
        pixels(s)
        for pointer in results.PARAMETERS:
            require(s.read(pointer+0x8c,8)==bytes.fromhex('efbeaddebeab0df0'),'Guest callback payload was patched')
        results.acknowledge(s);results.preview.advance(s)
        require(get(s,'batches')==1,'ACK replayed consumed RAW')
        results.preview.new_raw(s);results.preview.advance(s)
        require(get(s,'batches')==2,'Fresh RAW did not advance video')
        results.preview.acknowledge(s) # Keep unit result causes pending.
        results.preview.new_raw(s);results.preview.advance(s)
        require(get(s,'batches')==2,'Backpressure overwrote pending result')
        s.write(0x2010001c,0x21);results.preview.advance(s)
        require(get(s,'batches')==2,'Partial ACK released the frame')
        s.write(0x2010001c,0x40);results.preview.advance(s)
        require(get(s,'batches')==3,'Final ACK did not release actual queued RAW')
        results.acknowledge(s)
        results.preview.new_raw(s);s.write(0x20102100,0);results.preview.advance(s)
        require(get(s,'batches')==3 and results.preview.read(s,0x2010001c)==0,'Cancel emitted a result')
        s.write(0x20102100,0x121);results.preview.advance(s)
        require(get(s,'batches')==3,'Re-enable replayed cancelled RAW')
        results.preview.new_raw(s);results.preview.advance(s)
        require(get(s,'batches')==4,'Video did not re-enter on real new RAW')
        require(get(s,'batches',s.slave)==0 and not(results.preview.read(s,0x20100020)&4),'Peer or bank0 completion was manufactured')
        s.query('qom-set',{'path':s.master,'property':'video-batches','value':0},error=True)
        s.query('system_reset');results.preview.advance(s)
        require(all(get(s,n)==0 for n in ('batches','source-captures','main-bytes','work-bytes','source-bytes')),'Video reset retained active state')
        require(results.preview.read(s,0x2010001c)==results.preview.read(s,0x20100020)==0,'Reset retained completions')
        result.update(actual_main_and_work=True,actual_twelve_previews=True,independent_work_oracle=True,
            bounded_dma=True,owned_raw_snapshot=True,no_guest_callback_patch=True,ack_no_replay=True,
            partial_ack_backpressure=True,cancel_requires_new_raw=True,slave_and_bank0_isolation=True,
            read_only_counters=True,reset=True,command=s.command)
    negative=(
        ('opaque-change',lambda s:s.write(0x20380708,0)),
        ('late-unmapped-output',lambda s:s.write(0x20102200+3*64+5*4,0xfffc2000)),
        ('output-alias',lambda s:s.write(0x20102200+4*4,geometry()[0]['main'])),
        ('work-ring-mismatch',lambda s:s.write(0x20380450,geometry()[0]['work']+16)),
        ('unqualified-main-second-ring',lambda s:s.write(0x203804a8,geometry()[0]['main'])),
        ('bad-result-parameters',lambda s:s.write(results.PARAMETERS[1]+0x60,0xfe)))
    for name,mutate in negative:
        with session(binary) as s:
            configure_video(s);fill_guards(s);mutate(s);results.preview.new_raw(s);results.preview.advance(s)
            require(get(s,'batches')==0 and get(s,'rejected')>0,'Invalid '+name+' completed video')
            require(results.preview.read(s,0x2010001c)==results.preview.read(s,0x20100020)==0,'Invalid '+name+' latched completion')
            guards(s,True,full=name=='late-unmapped-output')
    result.update(completed=True,negative_cases=[name for name,_ in negative],explicit_origin_rejections=True,
                  late_rejection_all_output_bytes_preserved=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu',type=Path,default=host.DEFAULT_QEMU)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--parent-negative',action='store_true')
    parser.add_argument('--diagnostic',action='store_true')
    args=parser.parse_args()
    if args.output.exists(): raise FileExistsError('Existing video native evidence is immutable')
    try: record=diagnose(args.qemu.resolve()) if args.diagnostic else check(args.qemu.resolve(),args.parent_negative)
    except Exception as exc:
        record={'schema':1,'completed':False,'camera_accessed':False,
                'failure':{'type':type(exc).__name__,'message':str(exc)}}
    with args.output.open('x',encoding='utf-8') as handle: json.dump(record,handle,indent=2)
    print(json.dumps(record),flush=True)
    raise SystemExit(0 if record.get('completed',record.get('diagnostic_completed',False)) else 1)
