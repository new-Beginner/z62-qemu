"""r94d verify the provider's RAM source against the actual staged group17.

All reads remain passive. A full image comparison supplies stronger evidence
than matching an all-zero resource slice alone.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from unittest.mock import patch
import probe_z62_group_provider_context as parent
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,output,duration=8,wall_limit=300):
    qemu,card,group23,output=map(workspace,(qemu,card,group23,output))
    origin=parent.parent.parent;before_capture=origin.capture;source_hash=digest(Path(__file__));images={}
    def capture(machine):
        running=machine.qmp.command('query-status')['running']
        if running:machine.qmp.command('stop')
        try:
            result=before_capture(machine);pointer=machine._words(parent.CONTEXT,12)[6]
            candidate=pointer-0x11500
            if 0xc0000000<=candidate<=0xe0000000-0x20000 and not candidate&3:
                if candidate not in images:
                    raw=bytearray()
                    for offset in range(0,0x20000,2048):
                        raw.extend(struct.pack('<512I',*machine._words(candidate+offset,512)))
                    baseline=Path(machine.args.parameters)/'group17.bin';original=baseline.read_bytes()
                    path=output/f'group17-mirror-{candidate:08x}.bin'
                    with path.open('xb') as handle:handle.write(raw)
                    images[candidate]={'mirror_base':hex(candidate),'provider_source':hex(pointer),'resource_offset':0x11500,
                        'mirror_path':path.name,'mirror_sha256':hashlib.sha256(raw).hexdigest(),
                        'staged_input':str(baseline),'staged_sha256':digest(baseline),'bytes':len(raw),
                        'complete_image_matches_staged_group17':raw==original,
                        'resource_slice_sha256':hashlib.sha256(raw[0x11500:0x14100]).hexdigest(),
                        'input_is_synthetic_not_factory_calibration':True}
                    print('PARAMETER_IMAGE_BINDING',hex(candidate),raw==original,flush=True)
                result['parameter_image_binding']=images[candidate]
            return result
        finally:
            if running:machine.qmp.command('cont')
    with patch.object(origin,'capture',capture):result,receipt=parent.run(qemu,card,group23,output,duration,wall_limit)
    require(digest(Path(__file__))==source_hash,'Parameter-image observer changed')
    summary={'schema':1,'version':'2026.11.04-group-parameter-image-r94d',
        'result_sha256':digest(output/'result.json'),'provider_context_sha256':digest(output/'provider-context.json'),
        'source_sha256':{str(Path(__file__)):source_hash},'images':images,
        'guest_memory_or_registers_written':False,'parameters_replaced':False,'camera_accessed':False}
    with (output/'parameter-image.json').open('x',encoding='utf-8') as handle:json.dump(summary,handle,ensure_ascii=False,indent=2)
    return result,receipt,summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=parent.parent.parent.hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--duration',type=float,default=8)
    parser.add_argument('--wall-limit',type=float,default=300);args=parser.parse_args()
    result,receipt,summary=run(args.qemu,args.card,args.group23,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and
        result.get('process_exit_code')==0 and summary['images'] and
        all(row['complete_image_matches_staged_group17'] for row in summary['images'].values()) else 1)
