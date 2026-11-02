"""Verify the scoped r9 pixel path; keep resume and complete-camera gates separate."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image
import run_z62_preview as host

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'analysis/z62-isp-r9'


def expected_lcd_pixel(x,y,width=1024,height=682):
    def tone(n):
        v=max(0,min(1,(n-64)/4031))
        return round(255*(12.92*v if v<=.0031308 else 1.055*v**(1/2.4)-.055))
    def rgb(x,y):
        sx=2+(x*755//width)*2;sy=2+(y*501//height)*2
        value=lambda a,b:(3*a+5*b+256)&4095
        return tone(value(sx,sy)),tone((value(sx+1,sy)+value(sx,sy+1)+1)//2),tone(value(sx+1,sy+1))
    r,g,b=rgb(x,y)
    lum=max(16,min(235,((66*r+129*g+25*b+128)>>8)+16))
    cells=[rgb((x&~1)+dx,(y&~1)+dy) for dy in range(2) for dx in range(2)]
    r,g,b=((sum(c[k] for c in cells)+2)//4 for k in range(3))
    u=max(16,min(240,((-38*r-74*g+112*b+128)>>8)+128))
    v=max(16,min(240,((112*r-94*g-18*b+128)>>8)+128))
    c=lum-16;d=u-128;e=v-128
    return tuple(max(0,min(255,n)) for n in
        ((298*c+409*e+128)>>8,(298*c-100*d-208*e+128)>>8,(298*c+516*d+128)>>8))


def check():
    manifest=host.verify_build(host.DEFAULT_QEMU.resolve())
    evidence={}
    def read(name):
        data=(BASE/name).read_bytes();evidence[name]=hashlib.sha256(data).hexdigest()
        return json.loads(data)
    for name in ('qtest2.json','raw-regression.json','finite-regression.json'):
        record=read(name)
        if not record.get('completed') or record.get('binary_sha256')!=manifest['binary_sha256']:
            raise ValueError('Native test did not pass on this binary: '+name)
    if not read('pixels-test2/report.json').get('completed'): raise ValueError('C pixel tests incomplete')
    native=read('native/report.json')
    session=read('native/session.json')
    if session.get('capcom_device',{}).get('binary_sha256')!=manifest['binary_sha256']:
        raise ValueError('Original-firmware session used a different binary')
    if not native.get('observation_completed') or not native.get('clean_exit'):
        raise ValueError('Original firmware run incomplete')
    if native.get('raw_transactions') or native.get('metadata_events') or native.get('guest_software_patched'):
        raise ValueError('Unexpected host-side completion or software patch')
    final=native['samples'][-1]
    status=final['capture']['preview_status'];m=status['engines']['master']
    if not status['known'] or m['preview-batches']<=0 or m['preview-rejected']:
        raise ValueError('Preview transactions failed or unknown')
    if m['preview-outputs']!=12*m['preview-batches'] or m['preview-bytes']!=20809728*m['preview-batches']:
        raise ValueError('Incomplete preview output accounting')
    if status['engines']['slave']['preview-batches'] or status['statistics_bank0_completed']:
        raise ValueError('Unexpected scope of completion')
    frame=native['frames'][-1];png=BASE/'native'/frame['file']
    if hashlib.sha256(png.read_bytes()).hexdigest()!=frame['sha256']:
        raise ValueError('LCD screenshot identity changed')
    with Image.open(png) as image:
        image=image.convert('RGB')
        if image.size!=(1024,682): raise ValueError('Unexpected LCD geometry')
        points=[]
        for y in (200,300,400,500):
            for x in (200,400,600,800):
                expected=expected_lcd_pixel(x,y)
                actual=image.getpixel((x,y))
                if actual!=expected: raise ValueError(f'LCD video pixel mismatch at {x},{y}: {actual} != {expected}')
                points.append({'xy':[x,y],'rgb':actual})
    result={'schema':1,'binary_sha256':manifest['binary_sha256'],'evidence_sha256':evidence,
        'native_preview_batches':m['preview-batches'],'native_preview_outputs':m['preview-outputs'],
        'native_preview_bytes':m['preview-bytes'],'lcd_video_points':points,
        'native_pixel_path_verified':True,'statistics_bank0_completed':False,
        'silicon_pixel_math_verified':False,'complete_emulator':False,'flash_safety_verified':False,
        'preview_resume_verified':False,'menu_cycle_verified':False,'release_gate_passed':False}
    menu_path=BASE/'menu/report.json'
    if menu_path.exists():
        menu=read('menu/report.json')
        result['menu_cycle_verified']=bool(menu.get('process_closed') and menu.get('menu_cycle_state_passed') and
            len(menu.get('cycles',[]))==3 and all(c.get('navigation_passed') for c in menu['cycles']))
        result['menu_final_preview_batches']=menu['samples'][-1]['capture']['preview_status']['engines']['master']['preview-batches']
    lifecycle_path=BASE/'lifecycle/trace.json'
    if lifecycle_path.exists():
        life=read('lifecycle/trace.json')
        rows=[r for r in life['observations'] if r['stage']=='after-exit' and r['index']==3]
        counts=[r['capture']['preview_status']['engines']['master']['preview-batches'] for r in rows]
        result['lifecycle_closed']=life.get('process_closed') is True
        if rows:
            result['applv_dwell']={'first':rows[0]['virtual_seconds'],'last':rows[-1]['virtual_seconds'],
                                  'first_batches':counts[0],'last_batches':counts[-1]}
            result['preview_resume_verified']=bool(result['lifecycle_closed'] and rows[-1]['virtual_seconds']-rows[0]['virtual_seconds']>=5
                and counts[-1]>counts[0] and not life.get('failure') and not life.get('cleanup_error'))
    result['release_gate_passed']=result['preview_resume_verified'] and result['menu_cycle_verified']
    for filename in ('entry/report.json','candidate-entry/report.json'):
        if (BASE/filename).exists():
            entry=read(filename)
            if not entry.get('completed') or not entry.get('process_closed') or entry.get('forced_cleanup'):
                raise ValueError('Research HTTP entry failed: '+filename)
            if entry.get('expected_version')!='2026.10.29-r9':
                raise ValueError('Wrong entry version')
            if filename.startswith('candidate-') and entry['status'].get('firmware_health_known') is not False:
                raise ValueError('Candidate health must remain unknown')
    if (BASE/'lifecycle-menu-toggle/trace.json').exists():
        toggle=read('lifecycle-menu-toggle/trace.json')
        result['menu_toggle_control']={'closed':toggle.get('process_closed') is True,
            'returned_applv':any(r['stage']=='after-exit' and r['index']==3 for r in toggle['observations'])}
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path);p.add_argument('--require-resume',action='store_true')
    args=p.parse_args();result=check()
    if args.output:
        with args.output.open('x',encoding='utf-8') as handle: json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2))
    if args.require_resume and not result['release_gate_passed']: raise SystemExit(1)
