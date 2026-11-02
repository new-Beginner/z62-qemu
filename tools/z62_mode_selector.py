"""C1.70 mode-selector analogue input, names pending original screen evidence."""
import hashlib
from pathlib import Path

VERSION='2026.10.30-mode-input-r21'
BANDS=((0x000,0x0E7,0),(0x0E7,0x2CD,1),(0x2CD,0x4D2,2),(0x4D2,0x6F4,3),
       (0x6F4,0x91F,6),(0x91F,0xB3B,5),(0xB3B,0xD47,4),(0xD47,0x1000,10))
SAMPLES={code:(low+high-1)//2 for low,high,code in BANDS}


def initialize(machine):
    paths=['/machine/unattached/'+item['name'] for item in
           machine.qmp.command('qom-list',{'path':'/machine/unattached'})
           if item['type']=='child<nikon-z72-controller-adc>']
    if len(paths)!=1:
        raise ValueError('Cannot identify mode-selector ADC')
    path=paths[0]
    regions=[item for item in machine.qmp.command('qom-list',{'path':path})
             if item['type']=='child<memory-region>']
    if len(regions)!=1:
        raise ValueError('Unexpected mode-selector ADC region')
    region=path+'/'+regions[0]['name']
    if (machine.qmp.command('qom-get',{'path':region,'property':'addr'})!=0x40012000 or
            machine.qmp.command('qom-get',{'path':region,'property':'size'})!=0x400):
        raise ValueError('Mode-selector ADC address differs')
    sample=machine.qmp.command('qom-get',{'path':path,'property':'input-channel2'})
    if type(sample) is not int or not 0<=sample<=4095:
        raise ValueError('Mode-selector ADC input unavailable')
    machine._mode_adc_path=path


def drive(machine,code):
    if type(code) is not int or code not in SAMPLES:
        raise ValueError('Unknown original mode-selector code')
    args={'path':machine._mode_adc_path,'property':'input-channel2'}
    before=machine.qmp.command('qom-get',args)
    machine.qmp.command('qom-set',{**args,'value':SAMPLES[code]})
    after=machine.qmp.command('qom-get',args)
    if after!=SAMPLES[code]:
        raise ValueError('Physical mode ADC input did not change')
    return {'code':code,'sample_before':before,'sample_after':after}


def identity():
    return {'version':VERSION,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'adc_channel':2,'bands':BANDS,'samples':SAMPLES,'guest_software_patched':False}


def apply_console(source):
    from reference_updates import replace_once
    path=source/'tools/z62_console.py'
    content=replace_once(path.read_text(encoding='utf-8'),'        self.qmp = shared.QmpClient(qmp_port)',
        '        self.qmp = shared.QmpClient(qmp_port)\n'
        '        from tools.z62_mode_selector import initialize as initialize_mode_selector\n'
        '        initialize_mode_selector(self)')
    path.write_text(content,encoding='utf-8',newline='\n')
    (source/'tools/z62_mode_selector.py').write_bytes(Path(__file__).read_bytes())
