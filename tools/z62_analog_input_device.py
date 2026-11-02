"""Bounded runtime ADC levels on an independent descendant of frozen r18."""
from pathlib import Path
import reference_updates as reference

ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.10.30-r21'
WORK=ROOT/'.build'/('z62-analog-input-'+VERSION)
HEADER=ROOT/'qemu/z62-analog-input/nikon-z62-adc-input.h'
INPUTS={'nikon-z72-controller-adc.c':'1a9c39cd8cc48e0e004621d704f448034d7a17c779a46d17374cdb71103d3d6d'}


def identity():
    return {'schema':1,'version':VERSION,'input_sha256':INPUTS,
            'adapter_sha256':reference.sha(Path(__file__).read_bytes()),
            'header_sha256':reference.sha(HEADER.read_bytes()),
            'input_channels':19,'sample_bits':12,'inflight_conversion_sample_latched':True,
            'reset_preserves_external_inputs':True,'guest_software_patched':False,
            'complete_emulator':False}


def render(data):
    if reference.sha(data) != INPUTS['nikon-z72-controller-adc.c']:
        raise ValueError('Runtime ADC inputs require the frozen parent ADC model')
    text=data.decode('utf-8')
    text=reference.replace_once(text,'#include "qapi/error.h"',
        '#include "qapi/error.h"\n#include "qapi/visitor.h"')
    text=reference.replace_once(text,'static void adc_class_init(ObjectClass *klass, const void *data)',
        '#include "nikon-z62-adc-input.h"\n\nstatic void adc_class_init(ObjectClass *klass, const void *data)')
    text=reference.replace_once(text,'    device_class_set_props(dc, adc_properties);',
        '    device_class_set_props(dc, adc_properties);\n    z62_adc_input_properties(klass);')
    return text


def apply_source(source):
    source=Path(source).resolve()
    if not source.is_relative_to(WORK.resolve()):
        raise ValueError('ADC input extension requires its independent build workspace')
    arm=source/'hw/arm'
    target=arm/'nikon-z72-controller-adc.c'
    target.write_text(render(target.read_bytes()),encoding='utf-8',newline='\n')
    (arm/HEADER.name).write_bytes(HEADER.read_bytes())
    return identity()
