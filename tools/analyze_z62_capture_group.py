"""Fixed Z62 code/trace evidence for unit20/event96; no firmware execution.

Raw ARM module has no PE/ELF import table. Bounded original Thumb windows
and literal-pool assertions are the equivalent source evidence here.
"""
import argparse
import json
from pathlib import Path
import struct
import analyze_z62_ingress_contract as image
import z62_mmio_filtered_trace as trace
from record_z62_action_evidence import workspace,digest,require

ROOT=Path(__file__).resolve().parents[1]


def analyze(image_path,trace_path,output):
    image_path,trace_path,output=map(workspace,(image_path,trace_path,output))
    require(not output.exists(),'Use new group contract evidence')
    raw=image_path.read_bytes();image.verify_image(raw);md=image.decoder()
    anchors={0x102393a4:('movs','r0, #0x20'),0x102393a6:('bl','#0x1020c034'),
        0x1023929c:('ldrb','r0, [r1, #0xc]'),0x1023929e:('lsls','r0, r0, #0x1f'),
        0x102392a4:('mov.w','r1, #0x1000000'),0x102392b2:('b.w','#0x1035d374'),
        0x1020c082:('movs','r1, #0x10'),0x1020c088:('bl','#0x1020ab28'),
        0x1020c090:('bl','#0x1020ab20'),0x10208c48:('movs','r1, #0x20'),
        0x10208c4c:('b.w','#0x1020aafc')}
    decoded=[]
    for pc,expected in anchors.items():
        i=next(md.disasm(raw[pc-image.BASE:pc-image.BASE+4],pc))
        require((i.mnemonic,i.op_str)==expected,'Original group anchor differs: '+hex(pc))
        decoded.append({'pc':hex(pc),'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str})
    require(struct.unpack_from('<I',raw,0x1023940c-image.BASE)[0]==0x1023926f,
        'Unit20 callback literal differs')
    rows=[r for r in trace.parse_lines(trace_path.read_text(encoding='utf-8').splitlines()) if r['board_view']=='master']
    profile={r['address']-0x2006b800:r['value'] for r in rows if 0x2006b800<=r['address']<=0x2006bd80}
    curve=[profile.get(0x80+i*4) for i in range(65)]
    coefficients=[[profile.get(0x20+f*32+i*4) for i in range(8)] for f in range(3)]
    require(None not in curve and all(None not in row for row in coefficients),'Incomplete parameter writes')
    result={'schema':1,'completed_analysis':True,'firmware_executed':False,'camera_accessed':False,
        'E-imports':{'format':'raw Nikon ARM module','PE_ELF_IAT_applicable':False,'base':hex(image.BASE)},
        'master_sha256':digest(image_path),'trace_sha256':digest(trace_path),'anchors':decoded,
        'unit_mask':0x20,'selected_commit':0x10,'input_event':96,'event_object_mask':0x1000000,
        'profile':{hex(offset):value for offset,value in sorted(profile.items())},
        'observed_curve_65':curve,'observed_coefficients_3x8':coefficients,
        'curve_and_coefficients_explicitly_written_zero':not any(curve) and not any(v for row in coefficients for v in row),
        'zero_parameters_prove_physical_erasure':False,'reference_operator_is_C_hypothesis':True,
        'original_statistics_payload_layout_complete':False,'all_trace_writes_accepted_verified':False,
        'source_sha256':{str(Path(path)):digest(Path(path)) for path in (__file__,image.__file__,trace.__file__)}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ('completed_analysis','unit_mask','input_event',
        'curve_and_coefficients_explicitly_written_zero','zero_parameters_prove_physical_erasure')}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--trace',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();analyze(args.image,args.trace,args.output)
