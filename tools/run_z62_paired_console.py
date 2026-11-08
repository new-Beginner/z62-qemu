"""Independent interactive C scene/media profile with observed firmware modes."""
import argparse
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import run_z62_async_video_console as host
import run_z62_capture_console as capture
import run_z62_capcom as capcom
import run_z62_output_lineage as hardware
import z62_paired_console as paired

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=Path('<USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures')
GROUP23_SHA256='c7dd14358b45b2813fdee85fc587bcdd5899f7a81e0d5830513d631235bcc700'


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    parser=argparse.ArgumentParser(description=__doc__,add_help=False)
    parser.add_argument('--qemu',type=Path,default=hardware.DEFAULT_QEMU)
    parser.add_argument('--group23-fixture',type=Path,default=FIXTURES/'group23.bin')
    parser.add_argument('--help',action='store_true')
    if '--version' in argv:
        print(paired.VERSION); return
    own,rest=parser.parse_known_args(argv)
    if own.help:
        parser.print_help()
        print('Other options: --port 8685 --software-card DIR --software-no-card --photo-format jpeg|nef|jpeg-nef')
        print('  --software-scene IMAGE --software-width 640 --software-height 424 --sd-card RAW_IMAGE')
        return
    forbidden=('--parameters','--capture-preset','--sampling-source','--main-screen-experiment',
               '--no-raw-stream','--no-finite-stats','--no-preview')
    if any(v.split('=',1)[0] in forbidden for v in rest):
        raise ValueError('This isolated profile requires its fixed baseline device configuration')
    build=hardware.verify_build(own.qemu)
    fixture=own.group23_fixture.absolute()
    if fixture.is_symlink() or hashlib.sha256(fixture.read_bytes()).hexdigest()!=GROUP23_SHA256:
        raise ValueError('This profile requires the reviewed r68 synthetic group23 fixture')
    globals_=hardware.configure_command([],retained=True,video=True,origin=(0,76),
        stop_control=True,paired=True,lineage=True)
    globals_+=['-global','nikon-z72-boot-config.z62-preview=on',
               '-global','nikon-z72-boot-config.z62-preview-results=on',
               '-global','nikon-z72-boot-config.z62-raw-boundary=on',
               '-global','nikon-z72-input-config.functional-continuous-stats=on',
               '-global','nikon-z62-sensor-config.laboratory-init-completion=on',
               '-global','nikon-z62-sensor-config.laboratory-mode-completion=on',
               '-global','nikon-z62-sensor-config.functional-raw-completion=on',
               '-global','nikon-z72-boot-config.z62-capcom-sync=on']
    profile={'version':paired.VERSION,'hardware_version':build['version'],
        'binary_sha256':build['binary_sha256'],'group23':str(fixture),'group23_sha256':GROUP23_SHA256,
        'globals':globals_,'implementation_level':'C','factory_capture_chain_verified':False,
        'physical_selector_identity_verified':False,'camera_accessed':False}
    original=host.asynchronous.apply_console
    staged=[]
    original_launch=capcom.main
    def launch(*args,**kwargs):
        kwargs.update(display_version=paired.VERSION,
            description='原厂固件执行与C级场景成像实验。模式以实际输出确认；JPEG、NEF和静音MP4为软件编码，完整切换与拍摄流程仍在验收。')
        return original_launch(*args,**kwargs)
    def apply(source):
        original(source)
        paired.apply_console(source,profile)
        staged.append(Path(source))
    if '--software-card' not in rest and '--software-no-card' not in rest and not any(v.startswith('--software-card=') for v in rest):
        rest+=['--software-card',str(ROOT/'artifacts/z62-paired-card-r71')]
    if '--port' not in rest and not any(v.startswith('--port=') for v in rest):
        rest+=['--port','8685']
    if '--sd-card' not in rest and not any(v.startswith('--sd-card=') for v in rest):
        rest+=['--sd-card',str(FIXTURES/'card-r22-4096.raw')]
    for flag in ('--experimental-parameters','--no-auto-menu'):
        if flag not in rest: rest.append(flag)
    with patch.object(host.asynchronous,'apply_console',apply), \
         patch.object(capture,'verified_hardware_version',lambda qemu:hardware.verify_build(qemu)['version']), \
         patch.object(capcom,'main',launch), \
         patch.dict(os.environ,{'PI_SCRATCH_DIR':tempfile.gettempdir()}):
        try:
            host.main(['--qemu',str(own.qemu)]+rest)
        finally:
            for source in staged:
                paired.finalize_parameters(source.parent,profile)


if __name__=='__main__':
    main()
