"""Preserve Z62-specific group parameter call/literal anchors for follow-up.

The Z72 resource39/descriptor17 recipe is a reference, not authority to patch
the same offsets or call entries in a different camera's parameter input.
"""
import argparse
import json
from pathlib import Path
import struct
import analyze_z62_ingress_contract as image
from record_z62_action_evidence import workspace,digest,require


def analyze(master,output):
    master,output=map(workspace,(master,output));require(not output.exists(),'Use new parameter-source evidence')
    raw=master.read_bytes();image.verify_image(raw);md=image.decoder()
    expected={0x10239c10:('add.w','r0, r4, #0x58'),0x10239c14:('bl','#0x1020c13e'),
        0x10239c64:('ldr','r6, [pc, #0x74]'),0x10239c66:('ldr','r0, [r6, #0x80]!'),
        0x10239c6a:('bl','#0x1020c14a')}
    anchors=[]
    for pc,wanted in expected.items():
        i=next(md.disasm(raw[pc-image.BASE:pc-image.BASE+4],pc))
        require((i.mnemonic,i.op_str)==wanted,'Z62 parameter source anchor differs: '+hex(pc))
        anchors.append({'pc':hex(pc),'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str})
    base=struct.unpack_from('<I',raw,0x10239cdc-image.BASE)[0]
    require(base==0xc26a0884,'Z62 parameter structure literal differs')
    windows=[]
    for start,end in ((0x10239bec,0x10239c4a),(0x10239c4a,0x10239cdc),
            (0x10208cb0,0x10208cf4),(0x10208db6,0x10208dd8)):
        windows.append({'start':hex(start),'end_exclusive':hex(end),'instructions':[
            {'pc':hex(i.address),'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str}
            for i in md.disasm(raw[start-image.BASE:end-image.BASE],start)]})
    result={'schema':1,'completed_static_anchor_check':True,'master_sha256':digest(master),
        'E-imports':{'format':'raw Nikon ARM module','IAT_applicable':False,'base':hex(image.BASE)},
        'anchors':anchors,'parameter_structure':hex(base),'packed_coefficient_argument':hex(base+0x58),
        'curve_pointer_slot':hex(base+0x80),'coefficient_setter':hex(0x1020c13e),'curve_setter':hex(0x1020c14a),
        'windows':windows,'provider_or_NOR_resource_number_proven':False,
        'Z72_resource39_offsets_validated_for_Z62':False,'guest_RAM_or_parameter_inputs_modified':False,
        'runtime_curve_pointer_value_observed':False,'camera_accessed':False,
        'source_sha256':{str(Path(p)):digest(Path(p)) for p in (__file__,image.__file__)}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ('completed_static_anchor_check','parameter_structure',
        'packed_coefficient_argument','curve_pointer_slot','provider_or_NOR_resource_number_proven')}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--master',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();analyze(args.master,args.output)
