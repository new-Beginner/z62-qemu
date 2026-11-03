"""Independently decode the actual native RAW12 fixture and archived source."""
import argparse
import json
from pathlib import Path

import numpy as np
from record_z62_action_evidence import workspace,digest,require


def nearest_edges(source_count,destination_count):
    # Largest source cell whose integer boundary is <= this destination sample.
    edges=np.arange(source_count+1,dtype=np.int64)*destination_count
    positions=np.arange(destination_count,dtype=np.int64)*source_count
    return np.searchsorted(edges,positions,side='right')-1


def tile_resize(image,width,height):
    source_height,source_width=image.shape
    xs=nearest_edges(source_width//2,width//2); ys=nearest_edges(source_height//2,height//2)
    result=np.empty((height,width),dtype=np.uint16)
    for y in range(2):
        for x in range(2): result[y::2,x::2]=image[y::2,x::2][ys[:,None],xs[None,:]]
    return result


def check_archive(result_path):
    data=json.loads((result_path.parent/'source-archive.json').read_text(encoding='utf-8'))
    require(data['original_bytes_preserved'] and data['result_sha256']==digest(result_path),'Source archive/result changed')
    for relative,expected in data['source_sha256'].items():
        require(digest(result_path.parent/'source-snapshot'/relative)==expected,'Archived source bytes differ')
    return len(data['source_sha256'])


def verify(state_path,native_path,output):
    state_path,native_path,output=map(workspace,(state_path,native_path,output))
    state=json.loads(state_path.read_text(encoding='utf-8')); native=json.loads(native_path.read_text(encoding='utf-8'))
    require(state['completed_observation'] and state.get('detach')=='OK' and state['sources_unchanged'] and
            not state['controls_sent'] and not state['completion_injected'],'State observation incomplete')
    require(native['completed'] and native['observed_state_sha256']==digest(state_path),'Native state identity differs')
    for name in ('qemu_dma_performed','completion_injected','device_integration_complete',
                 'source_MAIN_provenance_established','configuration_write_provenance_established',
                 'physical_sampling_verified','inverse_transfer_verified'):
        require(native[name] is False,'Numerical fixture overclaims '+name)
    archived=check_archive(state_path)+check_archive(native_path)
    iw,ih,mw,mh,ow,oh=native['dimensions']; stride=native['stride']
    require(native['bits']==12 and native['transfer_codec']=='lookup8-high-byte','Wrong fixture codec')
    raw_path=native_path.parent/'synthetic-frame.p12'; raw=raw_path.read_bytes()
    require(digest(raw_path)==native['packed_sha256'] and len(raw)==stride*oh,'Packed output changed')
    source_y=np.arange(ih,dtype=np.uint32)[:,None]; source_x=np.arange(iw,dtype=np.uint32)[None,:]
    source=((((3*source_x+5*source_y+17)&255)*256)+((source_x+source_y)&255)).astype(np.uint16)
    middle=tile_resize(source,mw,mh); expected_linear=tile_resize(middle,ow,oh)
    lut=np.array([(word>>(16*half))&65535 for word in state['packing_lut_words'] for half in (0,1)],dtype=np.uint16)
    expected=lut[expected_linear>>8]
    rows=np.frombuffer(raw,dtype=np.uint8).reshape(oh,stride)
    payload=rows[:,:ow*12//8].reshape(oh,ow//2,3).astype(np.uint16)
    actual=np.empty((oh,ow),dtype=np.uint16)
    actual[:,0::2]=payload[:,:,0]|((payload[:,:,1]&15)<<8)
    actual[:,1::2]=(payload[:,:,1]>>4)|(payload[:,:,2]<<4)
    mismatches=int(np.count_nonzero(actual!=expected))
    require(mismatches==0 and np.all(rows[:,ow*12//8:]==0xa5),'Independent RAW12/phase/padding comparison failed')
    require(native['native_result']['pixels_checked']==ow*oh and
            native['native_result']['independent_two_pass_reference'],'Native comparison scope differs')
    output_record={'schema':1,'completed_evidence_check':True,'verifier_sha256':digest(Path(__file__)),
        'state_sha256':digest(state_path),'native_result_sha256':digest(native_path),
        'source_files_archived_and_verified':archived,'pixels_independently_decoded':ow*oh,
        'sample_mismatches':mismatches,'row_padding_preserved':True,'packed_sha256':digest(raw_path),
        'dimensions':native['dimensions'],'bits':12,'stride':stride,
        'reference':'NumPy cell-boundary search, two materialized CFA stages, independent packed12 decoder',
        'QEMU_device_integrated':False,'readiness_completion_emitted':False,
        'MAIN_source_and_commit_provenance_verified':False,'silicon_ISP_equivalence_verified':False,
        'AF_verified':False,'camera_accessed':False}
    with output.open('x',encoding='utf-8') as handle: json.dump(output_record,handle,ensure_ascii=False,indent=2)
    print(json.dumps(output_record,ensure_ascii=False),flush=True)
    return output_record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True); parser.add_argument('--native',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    verify(args.state,args.native,args.output)
