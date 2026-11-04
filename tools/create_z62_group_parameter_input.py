"""Explicit virtual group17/resource39 inputs; never camera calibration.

Marker mode diagnoses the original loader path without providing a valid
numerical profile. Reference mode supplies the declared C LUT/FIR operator.
Original firmware, baseline inputs, headers and all other bytes are preserved.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from record_z62_action_evidence import workspace,digest,require

BASE=0x11500
LENGTH=0x2c00
CURVE=0x1a1c
COEFFICIENTS=(0x186c,0x18cc,0x192c,0x198c,0x26b0)
BASELINE_SHA='cf841bf675c03e6fd514121bcd130f05ae67039083ca7c3c5a203de052279ee4'
MASTER_SHA='bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4'


def transform(data,mode):
    require(mode in ('marker','reference'),'Choose explicit marker or C-reference input')
    require(len(data)==0x20000 and data[-4:]==b'ENDM','Expected complete virtual group17 image')
    require(not any(data[BASE:BASE+LENGTH]),'Only the known zero virtual resource may be transformed')
    out=bytearray(data)
    if mode=='marker':struct.pack_into('<H',out,BASE+CURVE+17*2,0x123)
    else:
        for i in range(65):struct.pack_into('<H',out,BASE+CURVE+i*2,min(i*1024,65535))
        for variant in COEFFICIENTS:
            for row in range(3):
                for tap in range(8):
                    value=1 if tap==3 else 0xffffffff if tap==4+row else 0
                    struct.pack_into('<I',out,BASE+variant+(row*8+tap)*4,value)
    return bytes(out)


def create(source,output,contract_path,mode):
    source,output,contract_path=map(workspace,(source,output,contract_path));manifest=output.with_name(output.name+'.json')
    require(not source.is_symlink() and source.is_file() and not output.exists() and not manifest.exists(),
        'Use an ordinary source and new workspace output')
    require(source.resolve()!=output.resolve(),'Baseline cannot be overwritten')
    contract=json.loads(contract_path.read_text(encoding='utf-8'))
    require(contract['completed_static_analysis'] and contract['master_sha256']==MASTER_SHA and
        contract['resource_row']['resource_id']==39 and contract['resource_row']['offset']==BASE and
        contract['resource_row']['length']==LENGTH and contract['resource_curve_offset']==CURVE and
        contract['resource_coefficient_variants']==list(COEFFICIENTS),'Z62 resource contract differs')
    original=source.read_bytes();require(hashlib.sha256(original).hexdigest()==BASELINE_SHA,'Use the frozen synthetic baseline')
    data=transform(original,mode);changed=[i for i,(a,b) in enumerate(zip(original,data)) if a!=b]
    allowed=set(range(BASE+CURVE,BASE+CURVE+130))
    if mode=='reference':
        for offset in COEFFICIENTS:allowed.update(range(BASE+offset,BASE+offset+96))
    require(changed and all(i in allowed for i in changed),'Unexpected parameter mutation')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as handle:handle.write(data)
    result={'schema':1,'version':'2026.11.04-group-input-r95','mode':mode,'source':str(source),
        'source_sha256':BASELINE_SHA,'output':str(output),'output_sha256':digest(output),'bytes':len(data),
        'contract_sha256':digest(contract_path),'changed_byte_offsets':changed,
        'outside_declared_fields_unchanged':True,'original_firmware_modified':False,
        'factory_calibration':False,'nor_dump':False,'camera_accessed':False,
        'physical_AF_or_ISP_equivalence':False,
        'operator':'isolated diagnostic curve tag' if mode=='marker' else 'C-reference linear LUT and three difference FIRs',
        'generator_sha256':digest(Path(__file__))}
    with manifest.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ('mode','output','output_sha256','outside_declared_fields_unchanged')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--contract',type=Path,required=True)
    parser.add_argument('--mode',choices=('marker','reference'),required=True);args=parser.parse_args()
    create(args.source,args.output,args.contract,args.mode)
