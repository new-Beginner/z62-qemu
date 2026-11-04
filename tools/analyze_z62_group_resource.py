"""Z62 original-byte contract for the group resource and corrected field map.

No resource input is generated here. Static offsets are kept distinct from
the runtime whole-image binding supplied by the separate passive observer.
"""
import argparse
import json
from pathlib import Path
import struct
import analyze_z62_ingress_contract as image
from record_z62_action_evidence import workspace,digest,require


def analyze(master,output):
    master,output=map(workspace,(master,output));require(not output.exists(),'Use new resource contract output')
    raw=master.read_bytes();image.verify_image(raw);md=image.decoder()
    anchors={
        0x1020c13a:('b.w','#0x10208cb0'),0x1020c146:('b.w','#0x10208cf4'),
        0x1020c152:('b.w','#0x10208db6'),0x10239c5e:('adds','r0, #0x3e'),
        0x10239c60:('bl','#0x1020c132'),0x10239c10:('add.w','r0, r4, #0x58'),
        0x10239c14:('bl','#0x1020c13e'),0x1023b092:('add.w','r0, r4, #0xb4'),
        0x1023b09e:('str.w','r0, [r2, #0x80]'),0x10231e44:('bl','#0x1021f3e2'),
        0x1021f3e6:('bl','#0x103dfc14'),0x103dfc30:('b.w','#0x102abbc0'),
        0x102abbc0:('b.w','#0x102ab28a'),0x102ab2b4:('ldr','r2, [r1, #0x18]'),
        0x102ab2c4:('add.w','r6, r2, #0x1800'),
        0x102ab9b6:('add.w','r0, r0, r0, lsl #1'),0x102ab9ba:('add.w','r0, r6, r0, lsl #5'),
        0x102ab9be:('ldr','r1, [r0, #0x6c]'),0x102ab9c0:('str','r1, [r4, #0x54]'),
        0x102ab298:('movw','r5, #0x26b0'),0x102ab2bc:('add','r5, r2'),
        0x102abb26:('movs','r2, #0x82'),0x102abb2c:('add.w','r1, r6, #0x21c'),
        0x102abb3a:('add.w','r0, r4, #0xb4'),0x102abb3e:('blx','#0x1035d1ec'),
        0x10208dba:('ldrh.w','r3, [r1, r0, lsl #1]'),0x10208dc0:('cmp','r0, #0x41'),
    }
    decoded=[]
    for pc,expected in anchors.items():
        i=next(md.disasm(raw[pc-image.BASE:pc-image.BASE+4],pc))
        require((i.mnemonic,i.op_str)==expected,'Z62 resource anchor differs: '+hex(pc))
        decoded.append({'pc':hex(pc),'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str})
    resource=struct.unpack_from('<4I',raw,0x118d74c0-image.BASE)
    require(resource==(0,0x11500,0x2c00,0x00270300),'Z62 resource row differs')
    require(struct.unpack_from('<I',raw,0x102ac2b0-image.BASE)[0]==0xc21835d4,'Provider context literal differs')
    require(struct.unpack_from('<I',raw,0x103dfe04-image.BASE)[0]-4==0xc1861ef0,'Published context slot differs')
    result={'schema':1,'completed_static_analysis':True,'master_sha256':digest(master),
        'E-imports':{'format':'raw Nikon ARM module','IAT_applicable':False,'base':hex(image.BASE)},
        'anchors':decoded,'resource_row_VA':hex(0x118d74c0),
        'resource_row':{'flags':resource[0],'offset':resource[1],'length':resource[2],
            'tag':hex(resource[3]),'resource_id':resource[3]>>16},
        'resource_curve_offset':0x1800+0x21c,'resource_curve_bytes':130,
        'resource_coefficient_variants':[0x1800+0x6c+96*i for i in range(4)]+[0x26b0],
        'resource_coefficient_words_per_variant':24,
        'corrected_packed_coefficients_argument':hex(0xc26a0884+0x3e),
        'packed_coefficients_setter':hex(0x1020c132),'configuration_58_setter':hex(0x1020c13e),
        'r93_58_block_is_coefficients_label_correct':False,
        'provider_context':hex(0xc21835d4),'provider_context_slot':hex(0xc1861ef0),
        'provider_resource_field':0x18,'provider_output_curve_offset':0xb4,
        'curve_pointer_slot':hex(0xc26a0904),'runtime_primary_image_binding_verified_here':False,
        'guest_or_parameter_inputs_modified':False,'physical_factory_calibration_recovered':False,
        'camera_accessed':False,'source_sha256':{str(Path(p)):digest(Path(p)) for p in (__file__,image.__file__)}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ('completed_static_analysis','resource_row','resource_curve_offset',
        'resource_coefficient_variants','corrected_packed_coefficients_argument')}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--master',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();analyze(args.master,args.output)
