"""r94b corrected parameter layout; keep the accepted r94 observer immutable."""
import argparse
import json
from pathlib import Path
import struct
from unittest.mock import patch
import probe_z62_group_parameter_origin as parent
from record_z62_action_evidence import workspace,digest,require


def run(qemu,card,group23,output,duration=8,wall_limit=300):
    qemu,card,group23,output=map(workspace,(qemu,card,group23,output))
    before=digest(Path(__file__));previous=parent.capture
    def capture(machine):
        running=machine.qmp.command('query-status')['running']
        if running:machine.qmp.command('stop')
        try:
            result=previous(machine);blob=bytes.fromhex(result['parameter_bytes_hex'])
            result['r94a_legacy_58_block_hex']=result.pop('coefficient_bytes_24_hex')
            result['packed_coefficients_argument']=hex(parent.BASE+0x3e)
            result['packed_coefficients_24_hex']=blob[0x3e:0x56].hex()
            result['configuration_58_block_hex']=blob[0x58:0x80].hex()
            pointer=int(result['curve_pointer'],16)
            if 0xc00000b4<=pointer<0xe0000000-0x200:
                candidate=pointer-0xb4
                words=machine._words(candidate,0x200//4);raw=struct.pack('<128I',*words)
                result['candidate_provider_record']={'address':hex(candidate),'derivation':'curve pointer minus B09E writer offset B4',
                    'bytes_hex':raw.hex(),'curve_at_B4_matches':raw[0xb4:0x136].hex()==result.get('curve_bytes_hex'),
                    'coefficient_low_bytes_at_54':[raw[0x54+i*4] for i in range(24)],
                    'runtime_caller_argument_confirmed':False}
            return result
        finally:
            if running:machine.qmp.command('cont')
    with patch.object(parent,'capture',capture),patch.object(parent,'VERSION','2026.11.04-group-parameter-layout-r94b'):
        result,receipt=parent.run(qemu,card,group23,output,duration,wall_limit)
    require(digest(Path(__file__))==before,'Layout observer changed')
    extra={'schema':1,'version':'2026.11.04-group-parameter-layout-r94b',
        'result_sha256':digest(output/'result.json'),'parameter_origin_sha256':digest(output/'parameter-origin.json'),
        'source_sha256':{str(Path(__file__)):before},'corrected_coefficients_offset':0x3e,
        'legacy_58_is_coefficients':False,'guest_memory_or_registers_written':False,'camera_accessed':False}
    with (output/'parameter-layout.json').open('x',encoding='utf-8') as handle:json.dump(extra,handle,ensure_ascii=False,indent=2)
    return result,receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=parent.hardware.DEFAULT_QEMU)
    parser.add_argument('--card',type=Path,required=True);parser.add_argument('--group23',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--duration',type=float,default=8)
    parser.add_argument('--wall-limit',type=float,default=300);args=parser.parse_args()
    result,receipt=run(args.qemu,args.card,args.group23,args.output,args.duration,args.wall_limit)
    raise SystemExit(0 if result['completed_observation'] and not result.get('failure') and
        result.get('process_exit_code')==0 and receipt['observations'] else 1)
