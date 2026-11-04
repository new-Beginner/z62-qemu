"""Verify external input -> original provider/registers -> actual group DMA.

Only classified wire fields are numerically checked in original-window DMA;
native marker tests separately cover preservation of unclassified bytes.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import numpy as np
from PIL import Image
import create_z62_group_parameter_input as fixture
import probe_z62_capture_group as numerical
import run_z62_capture_group as hardware
import z62_mmio_filtered_trace as trace
from prepare_reference_firmware import PROFILES
from z62_main_frame import parse_packet
from record_z62_action_evidence import workspace,digest,require


def load(directory,mode):
    w=json.loads((directory/'result.json').read_text(encoding='utf-8'))
    r=json.loads((directory/'parameter-input.json').read_text(encoding='utf-8'))
    require(w['completed_observation'] and not w.get('failure') and not w.get('cleanup_failure') and
        w['process_exit_code']==0 and w['driver_sources_unchanged'] and w['original_card_unchanged'],
        'Input observation incomplete')
    require(r['result_sha256']==digest(directory/'result.json') and r['captures'] and
        r['fixture_manifest']['mode']==mode and r['explicit_preboot_parameter_input'] and
        not r['post_boot_software_RAM_or_register_fixups'] and not r['ready_or_completion_injected'],
        'Input driver scope or binding differs')
    meta=r['fixture_manifest'];source=Path(meta['source']).read_bytes();data=Path(meta['output']).read_bytes()
    require(meta['generator_sha256']==digest(Path(fixture.__file__)),'Input generator source changed')
    require(hashlib.sha256(source).hexdigest()==fixture.BASELINE_SHA and digest(Path(meta['output']))==meta['output_sha256'] and
        data==fixture.transform(source,mode),'Input bytes or independent transformation differ')
    expected_curve=list(struct.unpack_from('<65H',data,fixture.BASE+fixture.CURVE))
    raw_coeff=struct.unpack_from('<24I',data,fixture.BASE+fixture.COEFFICIENTS[0])
    expected_coeff=[value&((1<<(8 if i%8==0 else 7))-1) for i,value in enumerate(raw_coeff)]
    for capture in r['captures']:
        require(capture['curve_u16_65']==capture['group_curve_words']==expected_curve,
            'Curve input/provider/actual register flow differs')
        require(capture['group_coefficient_words']==expected_coeff,'Actual coefficient registers differ')
        require(capture['packed_coefficients_24_hex']==bytes(value&255 for value in raw_coeff).hex(),
            'Corrected packed coefficient layout differs')
        row=capture['provider_source_file'];payload=(directory/row['path']).read_bytes()
        require(digest(directory/row['path'])==row['sha256'] and payload==data[fixture.BASE:fixture.BASE+fixture.LENGTH],
            'Original provider source differs from explicit resource input')
    session=workspace(w['session'])
    for _,(name,size,sha) in PROFILES['z62']['members'].items():
        path=session/'inputs'/name;require(path.stat().st_size==size and digest(path)==sha,'Original member changed')
    return w,r


def verify(marker,reference,contract_path,output):
    marker,reference,contract_path,output=map(workspace,(marker,reference,contract_path,output))
    require(not output.exists(),'Use new input verification output')
    m,mr=load(marker,'marker');w,r=load(reference,'reference');build=hardware.verify_build()
    require(m['QEMU_binary_sha256']==w['QEMU_binary_sha256']==build['binary_sha256'],'Input experiments used different kernels')
    contract=json.loads(contract_path.read_text(encoding='utf-8'))
    require(contract['completed_static_analysis'] and contract['corrected_packed_coefficients_argument']=='0xc26a08c2',
        'Corrected Z62 contract missing')
    require(m['final']['capture_group']['completed']==0 and m['final']['capture_group']['rejected']>0,
        'Diagnostic tag manufactured successful group work')
    rows=[row for row in trace.parse_lines((reference/'console.txt').read_text(encoding='utf-8').splitlines())
        if row['board_view']=='master']
    # Restore the same 143 committed source words as the real device. Optional
    # B984 is the documented cold-zero convention, never a fabricated write.
    def known(o):
        return o<=0x180 or 0x200<=o<=0x250 or 0x294<=o<=0x2b8 or o in (
            0x318,0x324,0x33c,0x344,0x348,0x34c,0x350,0x360,0x380,0x450,0x460,0x480,0x550,0x560,0x580)
    needed={o for o in range(0,0x584,4) if known(o)};shadow={};profiles={}
    for row in rows:
        if 0x2006b800<=row['address']<0x2006bd84:shadow[row['address']-0x2006b800]=row['value']
        if row['address'] in (0x20068100,0x20068104) and row['value']&0x10 and needed<=shadow.keys():
            p={o:shadow[o] for o in needed};p[0x184]=shadow.get(0x184,0)
            profiles[tuple(sorted(p.items()))]=p
    require(len(profiles)==1,'Original retained DMA needs generation-specific profile assignment')
    profile=next(iter(profiles.values()))
    dma_path=reference/'parameter-dma.json';dma=json.loads(dma_path.read_text(encoding='utf-8'))
    require(dma['result_sha256']==digest(reference/'result.json') and
        dma['input_receipt_sha256']==digest(reference/'parameter-input.json') and dma['frames'],
        'Actual original DMA retention missing')
    byte_count=classified=0
    for frame in dma['frames']:
        state=frame['source'];packet_path=reference/f'inputs/publication-{state["publication"]}.z62m'
        packet=packet_path.read_bytes();meta,_=parse_packet(packet)
        require((meta.epoch,meta.publish_id,meta.frame_id,meta.virtual_time_ns)==
            (state['epoch'],state['publication'],state['frame'],state['time_ns']),'Original group input identity differs')
        expected=numerical.expected(packet,profile,state['cursor'],state['bank'])
        for row in frame['outputs']:
            data=(reference/row['path']).read_bytes();family=row['family']
            require(digest(reference/row['path'])==row['sha256'] and len(data)==len(expected[family]),'Actual group DMA bytes changed')
            stride=40 if family==0 else 24 if family==1 else 32
            for base in range(0,len(data),stride):
                ranges=[(0,20)] if family==1 else [(0,22),(24,30)]+([(32,38)] if family==0 else [])
                for start,end in ranges:
                    require(data[base+start:base+end]==expected[family][base+start:base+end],
                        'Independent original group aggregate/prefix mismatch')
                    classified+=end-start
            byte_count+=len(data)
    ack=sum(row['address']==0x20068270 and bool(row['value']&1) for row in rows)
    final=w['final'];count=final['capture_group']['completed']
    require(count>0 and final['capture_group']['rejected']==0 and ack==count,'Actual group completion/CPU ACK differs')
    require(all(sample['legacy_RAW_accepted']==0 for sample in w['samples']),'Legacy RAW counter manufactured')
    image=Image.open(reference/'final-lcd.png').convert('RGB')
    patterns=Counter(sample.get('kernel_event',{}).get('pattern','unavailable') for sample in w['samples'])
    sources={str(Path(__file__)):digest(Path(__file__)),str(Path(fixture.__file__)):digest(Path(fixture.__file__)),
        str(Path(numerical.__file__)):digest(Path(numerical.__file__))}
    for record in (mr,r,dma,contract,m,w):sources.update(record['source_sha256'])
    for name,sha in sources.items():require(digest(Path(name))==sha,'Bound input analysis/driver source changed')
    result={'schema':1,'completed_evidence_check':True,'binary_sha256':build['binary_sha256'],
        'marker_result_sha256':digest(marker/'result.json'),'reference_result_sha256':digest(reference/'result.json'),
        'resource_contract_sha256':digest(contract_path),'diagnostic_tag_flow_verified':True,
        'marker_group_completed':0,'reference_group_completed':count,'original_CPU_event96_ACKs':ack,
        'original_retained_group_DMA_frames':len(dma['frames']),'original_group_DMA_bytes_retained':byte_count,
        'original_classified_group_bytes_independently_verified':classified,'classified_mismatches':0,
        'original_unclassified_bytes_independent_preservation_verified':False,
        'whole_primary_cache_image_equals_input':False,'resource_slice_equals_explicit_input':True,
        'corrected_coefficients_argument':'0xc26a08c2','C26A08DC_is_coefficients':False,
        'legacy_RAW_accepted_always_zero':True,'original_window_ns':final['virtual_time_ns'],
        'LCD_size':image.size,'LCD_all_black':not np.any(np.asarray(image)),
        'preview_batches':final['other_pipeline_counters']['preview-batches'],
        'kernel_pattern_samples_non_atomic':dict(patterns),'kernel_wait_return_traced':False,
        'factory_calibration':False,'physical_AF_or_ISP_equivalence':False,
        'complete_camera_or_flash_safety_verified':False,'camera_accessed':False,'source_sha256':sources}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_sha256','kernel_pattern_samples_non_atomic')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--marker',type=Path,required=True)
    parser.add_argument('--reference',type=Path,required=True);parser.add_argument('--contract',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    verify(args.marker,args.reference,args.contract,args.output)
