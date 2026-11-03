"""Fixed-image/control-trace evidence for r89, without running any firmware.

Trace rows are attempted writes. Their order supplies a finite C profile;
it is not a claim that every write completed or that Nikon silicon is known.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import analyze_z62_ingress_contract as image_contract
import z62_mmio_filtered_trace as trace
from record_z62_action_evidence import workspace,digest,require

ANCHORS={
    0x1020a510:('str','r1, [r0, #4]'),0x1020a514:('str','r1, [r0]'),
    0x1020a51c:('str','r1, [r0, #0x10]'),0x1020a520:('str','r1, [r0, #0x14]'),
    0x102092e4:('bic','r1, r1, #1'),0x102092e8:('str','r1, [r0]'),
    0x102092ec:('orrs','r1, r2'),0x102092ee:('str','r1, [r0]'),
    0x1020b17c:('bfi','r3, r4, #1, #2'),0x1020b180:('str','r3, [r1]'),
}
TRACE_SHA='6464a5a0c6ba0d877ab1771eb3b367840849362cf2ef9bfc5685d6ed71695f5e'


def analyze(image_path,trace_path,output):
    image_path,trace_path,output=map(workspace,(image_path,trace_path,output))
    require(not output.exists(),'Use a new contract result')
    image=image_path.read_bytes(); image_contract.verify_image(image); image_contract.verify_anchors(image)
    require(digest(trace_path)==TRACE_SHA,'Use the preserved full r64b trace')
    md=image_contract.decoder(); anchors=[]
    for pc,expected in ANCHORS.items():
        instruction=next(md.disasm(image[pc-image_contract.BASE:pc-image_contract.BASE+4],pc))
        require((instruction.mnemonic,instruction.op_str)==expected,'Original control instruction differs: '+hex(pc))
        anchors.append({'pc':hex(pc),'bytes':instruction.bytes.hex(),'mnemonic':instruction.mnemonic,
            'operands':instruction.op_str})
    require(image_contract.u32(image,0x10209350)==0x20069a14,'Channel2 pointer literal differs')
    rows=trace.parse_lines(trace_path.read_text(encoding='utf-8').splitlines())
    master=[r for r in rows if r['board_view']=='master']
    configuration={}; selected=[]
    wanted={0x20068500,0x20069d00,0x20069d04,0x20069e78,0x20069e7c,0x20069f00,
        *range(0x20069514,0x20069534,4),*range(0x20069600,0x20069800,4),
        0x20069a08,0x20069a14,0x20069a18,0x20069a24,0x20069a3c,0x20069a40,
        0x20069a44,0x20069a48,0x20069a4c,*range(0x20069a50,0x20069a70,4),0x20069a80}
    for row in master:
        if row['address'] in wanted:
            configuration[row['address']]=row['value']
        if row['address'] in (0x20068100,0x20068104) and row['value']&0x85 and len(selected)<24:
            selected.append({'trace_entry':row['trace_entry'],'file_line':row['file_line'],
                'address':hex(row['address']),'mask':hex(row['value']),
                'known_profile_words':len(configuration),
                'packing_and_geometry':{hex(k):hex(configuration[k]) for k in sorted(configuration)
                    if k<0x20069600 or k>=0x20069800},
                'LUT_words_seen':sum(0x20069600<=k<0x20069800 for k in configuration)})
    counter=Counter(row['value'] for row in master if row['address']==0x20069a3c)
    require(counter[0] and counter[1] and not (set(counter)-{0,1}),'Unexpected bank trace values')
    result={'schema':1,'version':'2026.11.04-capturework-control-r89','completed':True,
        'master_sha256':digest(image_path),'image_base':hex(image_contract.BASE),
        'format':'raw Nikon module, not a PE/ELF import-table image',
        'IAT_analysis_applicable':False,'existing_geometry_anchors_verified':True,
        'anchors':anchors,'channel2_bank_pointer':hex(0x20069a14+0x28),
        'bank_selector_bit0_separate_from_parameter_bits1_2':True,
        'trace_sha256':digest(trace_path),'trace_entries':len(rows),
        'bank_values':{hex(k):v for k,v in sorted(counter.items())},
        'selected_publication_writes':selected,'trace_rows_are_attempts':True,
        'all_trace_writes_accepted_verified':False,'physical_commit_semantics_complete':False,
        'firmware_executed_this_run':False,'camera_accessed':False,
        'source_sha256':{str(path):digest(path) for path in
            (Path(__file__),Path(image_contract.__file__),Path(trace.__file__),Path(trace.base.__file__))}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle: json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('anchors','selected_publication_writes','source_sha256')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--trace',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); analyze(args.image,args.trace,args.output)
