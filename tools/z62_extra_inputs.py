"""Original C1.70 AF-ON/Fn/movie GPIOs and the independent sub-selector."""
import hashlib
from pathlib import Path
from z62_encoder_input import discover_gpio_ports

VERSION='2026.10.30-extra-input-r21'
GPIO_KEYS={
    26: {'name':'AF-ON','port':0x40021800,'pin':2,'wire_offset':0x1B},
    27: {'name':'Fn1','port':0x40020400,'pin':15,'wire_offset':0x3B},
    28: {'name':'Fn2','port':0x40020000,'pin':10,'wire_offset':0x3C},
    29: {'name':'录像','port':0x40020400,'pin':1,'wire_offset':0x09},
}
JOY_MASK=sum(1<<pin for pin in range(11,16))
JOY_PINS={
    'neutral':(), 'center':(11,),
    'right':(11,14), 'left':(11,15), 'up':(11,13), 'down':(11,12),
    'right-up':(11,14,13), 'right-down':(11,14,12),
    'left-up':(11,15,13), 'left-down':(11,15,12),
}
JOY_WIRE={'right':0x2B,'left':0x2C,'up':0x2D,'down':0x2E,
          'right-up':0x2F,'right-down':0x30,'left-up':0x31,'left-down':0x32,'center':0x33}


def initialize(machine):
    machine._body_gpio_ports=discover_gpio_ports(machine.qmp.command)
    machine._body_gpio_levels={key:1 for key in GPIO_KEYS}
    for key in GPIO_KEYS:
        drive_gpio(machine,key,1)


def drive_gpio(machine,key,level):
    if type(key) is not int or key not in GPIO_KEYS or type(level) is not int or level not in (0,1):
        raise ValueError('Invalid extra body GPIO input')
    config=GPIO_KEYS[key]
    target=machine._body_gpio_ports[config['port']]['path']
    machine._qtest(f"set_irq_in {target} unnamed-gpio-in {config['pin']} {level}")
    machine._body_gpio_levels[key]=level


def joystick_levels(previous,position):
    if type(previous) is not int or not 0 <= previous <= 0xffffff or position not in JOY_PINS:
        raise ValueError('Invalid joystick state or expander level')
    return (previous | JOY_MASK) & ~sum(1<<pin for pin in JOY_PINS[position])


def drive_joystick(machine,position):
    if not isinstance(position,str) or position not in JOY_PINS:
        raise ValueError('Unknown joystick position')
    target='/machine/peripheral/keys'
    previous=machine.qmp.command('qom-get',{'path':target,'property':'input-levels'})
    levels=joystick_levels(previous,position)
    machine.qmp.command('qom-set',{'path':target,'property':'input-levels','value':levels})
    actual=machine.qmp.command('qom-get',{'path':target,'property':'input-levels'})
    if actual != levels:
        raise ValueError('Joystick physical input readback mismatch')
    return {'position':position,'before_levels':previous,'after_levels':actual}


def identity():
    return {'version':VERSION,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'gpio_keys':GPIO_KEYS,'joystick_pins':JOY_PINS,'guest_software_patched':False,
            'af_lens_or_recording_verified':False}


def apply_console(source):
    from reference_updates import replace_once
    path=source/'tools/z62_console.py'
    content=replace_once(path.read_text(encoding='utf-8'),'        self.qmp = shared.QmpClient(qmp_port)',
        '        self.qmp = shared.QmpClient(qmp_port)\n'
        '        from tools.z62_extra_inputs import initialize as initialize_body_gpio\n'
        '        initialize_body_gpio(self)')
    path.write_text(content,encoding='utf-8',newline='\n')
    (source/'tools/z62_extra_inputs.py').write_bytes(Path(__file__).read_bytes())
    (source/'tools/z62_encoder_input.py').write_bytes(Path(__file__).with_name('z62_encoder_input.py').read_bytes())
