"""Independently recompute native and original retained-image scalar samples."""
import argparse
import json
from pathlib import Path
import struct
import numpy as np
from PIL import Image
import probe_z62_capturework_finite as native
import run_z62_capturework_finite as hardware
import z62_capturework_finite_device as device
import z62_mmio_filtered_trace as trace
from z62_main_stream import reconstruct
from z62_main_frame import parse_packet
from prepare_reference_firmware import PROFILES
from record_z62_action_evidence import workspace,digest,require


def scalar_grid(linear):
    out=bytearray(768)
    for y in range(12):
        for x in range(30):
            values=linear[y*1006//12:(y+1)*1006//12,x*1514//30:(x+1)*1514//30]
            struct.pack_into('<H',out,y*64+x*2,(int(values.sum())+values.size//2)//values.size)
    return bytes(out)


def verify(native_path,original_path,state_path,output):
    native_path,original_path,state_path,output=map(workspace,(native_path,original_path,state_path,output))
    require(not output.exists(),'Use new finite verifier result')
    n=json.loads(native_path.read_text(encoding='utf-8'));w=json.loads(original_path.read_text(encoding='utf-8'))
    build=hardware.verify_build();require(n['completed'] and len(n['batches'])==2 and all(c==0 for c in n['process_exit_codes']),
        'Native retained-source checks incomplete')
    require(n['binary_sha256']==w['binary_sha256']==build['binary_sha256'],'Retained-source kernel identities differ')
    require(w['completed_observation'] and not w.get('failure') and not w.get('cleanup_failure') and
        w['process_exit_code']==0 and w['source_bytes_unchanged'] and w['original_card_unchanged'],'Original retained-source window incomplete')
    require(digest(state_path)==n['state_sha256'],'Native geometry input changed')
    dims,_,_,_=native.cw.profile(json.loads(state_path.read_text(encoding='utf-8')))
    native_bytes=0
    for batch in n['batches']:
        source=native_path.parent/batch['MAIN'];data=native_path.parent/batch['outputs']
        require(digest(source)==batch['MAIN_sha256'] and digest(data)==batch['outputs_sha256'],'Native retained data changed')
        require(data.read_bytes()==native.expected(source.read_bytes(),dims)*61,'Native 61-sample numerical batch differs')
        meta,_=parse_packet(source.read_bytes());require(meta.publish_id==batch['source']['batch_publication'],'Native source identity differs')
        native_bytes+=data.stat().st_size
    receipt_path=original_path.parent/'retained-dma.json';r=json.loads(receipt_path.read_text(encoding='utf-8'))
    require(r['result_sha256']==digest(original_path) and r['frames'],'Original scalar/source retention missing')
    publications={p['publication']:p for p in w['publications']};original_bytes=0;identities=[]
    for frame in r['frames']:
        source=frame['source'];cw=frame['CW_output'];pub=source['batch_publication']
        packet=reconstruct(original_path.parent/'main-source',publications[pub]);meta,_=parse_packet(packet)
        require((meta.epoch,meta.publish_id,meta.frame_id,meta.virtual_time_ns)==
            (source['batch_epoch'],pub,source['batch_frame'],source['batch_time_ns']),'Original retained source tags differ')
        raw_path=original_path.parent/frame['RAW_path'];scalar_path=original_path.parent/frame['scalar_path']
        require(digest(raw_path)==frame['RAW_sha256'] and digest(scalar_path)==frame['scalar_sha256'],'Original retained DMA bytes changed')
        require((cw['width'],cw['height'],cw['stride'],cw['bits'],cw['codec'])==(1514,1006,2272,12,1),'Unknown retained RAW domain')
        raw=np.frombuffer(raw_path.read_bytes(),dtype=np.uint8).reshape(1006,2272)
        triples=raw[:,:2271].reshape(1006,757,3).astype(np.uint16)
        codes=np.empty((1006,1514),dtype=np.uint16)
        codes[:,0::2]=triples[:,:,0]|((triples[:,:,1]&15)<<8);codes[:,1::2]=(triples[:,:,1]>>4)|(triples[:,:,2]<<4)
        inverse=np.full(4096,-1,dtype=np.int32)
        require(len(cw['lookup'])==256 and len(set(cw['lookup']))==256,'Unknown frozen LUT')
        for index,code in enumerate(cw['lookup']):inverse[code]=index
        indices=inverse[codes];require(np.all(indices>=0),'Retained code is outside frozen transfer')
        linear=(indices.astype(np.uint32)*256+128)//16
        require(scalar_path.read_bytes()==scalar_grid(linear),'Actual original finite scalar mean differs')
        original_bytes+=scalar_path.stat().st_size
        identities.append({'batch_request':source['batches_prepared'],'source_publication':pub,
            'source_frame':source['batch_frame'],'source_time_ns':source['batch_time_ns']})
    final=w['final'];finite=w['samples'][-1]['finite_statistics']
    require(finite['finite-frames']==122 and finite['finite-batches']==2 and finite['finite-rejected']==0,
        'Original two finite requests incomplete')
    require(all(sample['legacy_RAW_accepted']==0 for sample in w['samples']),'Finite samples incremented legacy RAW')
    rows=[]
    for line in (original_path.parent/'closed-console.txt').read_text(encoding='utf-8').splitlines():
        row=trace.parse_line(line)
        if row and row['cpu']==0:rows.append(row)
    ack=sum(row['address']==0x20068270 and bool(row['value']&0x80) for row in rows)
    require(ack>=2,'Original finite batch ACKs not observed')
    session=workspace(w['session'])
    for _,(name,size,sha) in PROFILES['z62']['members'].items():
        path=session/'inputs'/name;require(path.stat().st_size==size and digest(path)==sha,'Original firmware member changed')
    image=Image.open(original_path.parent/'final-lcd.png').convert('RGB')
    sources={str(Path(__file__)):digest(Path(__file__)),**n['source_sha256'],**w['source_sha256'],**r['source_sha256']}
    finite_stream=json.loads((original_path.parent/'finite-stream.json').read_text(encoding='utf-8'));sources.update(finite_stream['source_sha256'])
    work=hardware.DEFAULT_QEMU.parent.parent;reference=work/'reference-build-manifest.json'
    tree=Path(json.loads(reference.read_text(encoding='utf-8'))['source'])
    for path in (Path(hardware.__file__),Path(device.__file__),device.HEADER,device.ROOT/'tools/build_z62_capturework_finite.py',
            reference,work/'capturework-finite-build-manifest.json',*(tree/name for name in build['generated_source_sha256'])):
        sources[str(path)]=digest(path)
    for name,sha in sources.items():require(digest(Path(name))==sha,'Finite evidence source changed')
    result={'schema':1,'completed_evidence_check':True,'binary_sha256':build['binary_sha256'],
        'native_result_sha256':digest(native_path),'original_result_sha256':digest(original_path),
        'native_inputs':2,'native_finite_samples':122,'native_output_bytes_independently_recomputed':native_bytes,
        'original_finite_samples':122,'original_finite_batches':2,'original_finite_batch_bit7_ACKs':ack,
        'original_scalar_DMA_snapshots':len(r['frames']),'original_scalar_bytes_independently_verified':original_bytes,
        'scalar_byte_mismatches':0,'retained_source_identities':identities,
        'samples_are_not_new_RAW_acquisitions':True,'legacy_RAW_accepted_always_zero':True,
        'original_window_ns':final['virtual_time_ns'],'MAIN_publications':w['accepted_publications'],
        'CW_DMA_completed':final['capturework']['completed'],'LCD_all_black':not np.any(np.asarray(image)),
        'preview_batches':final['other_pipeline_counters']['preview-batches'],'camera_accessed':False,
        'complete_camera_or_AF_or_flash_safety_verified':False,'source_sha256':sources}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--native',type=Path,required=True)
    parser.add_argument('--original',type=Path,required=True);parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();verify(args.native,args.original,args.state,args.output)
