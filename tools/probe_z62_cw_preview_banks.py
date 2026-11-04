"""Native r104 bank isolation, stale source denial and encoded RAW preservation."""
import argparse
import hashlib
import json
from pathlib import Path
import probe_z62_capturework_preview as base
from record_z62_action_evidence import workspace,digest,require


def check(binary,state_path,output):
    binary,state_path,output=map(workspace,(binary,state_path,output));require(not output.exists(),'Use new bank/domain audit output')
    output.parent.mkdir(parents=True,exist_ok=True)
    proof={'schema':1,'completed':False,'artifact_root':str(output.parent),'camera_accessed':False,
        'firmware_executed':False,'source_sha256':{str(Path(p)):digest(Path(p)) for p in (__file__,base.__file__,base.cw.__file__,base.hardware.__file__)}}
    packets={}
    try:
        proof['binary_sha256']=base.hardware.verify_build(binary)['binary_sha256'];proof['state_sha256']=digest(state_path)
        dims,bits,stride,lut=base.cw.profile(json.loads(state_path.read_text(encoding='utf-8')))
        encoded_checked=0
        with base.session(binary,proof) as s:
            base.configure_preview(s);base.cw.configure(s,dims,bits,stride,lut)
            base.fill(s);base.cw.fill(s,stride*1006);base.initial_guards(s)
            def produce(p):
                color=((p*11+31)%220+16,(p*19+47)%210+16,(p*31+71)%200+16)
                packets[p]=base.cw.upload(s,dims,p,color);base.cw.advance(s,p);base.cw.acknowledge(s)
            def encoded(publications,bank):
                total=0
                for slot,p in enumerate(publications):
                    address=base.cw.raw.SLOTS[slot]+bank*0x300000
                    actual=s.read(address,stride*1006)
                    require(actual==base.cw.expected(packets[p],dims,stride,lut),
                        'Preview normalized or otherwise changed guest LUT-encoded RAW')
                    total+=len(actual)
                return total
            for p in range(1,5):produce(p)
            base.cw.idle(s);require(base.counter(s,'batches')==1,'Initial bank0 source not consumed')
            checked=base.verify_outputs(s,[1,2,3,4],packets,dims,stride);encoded_checked+=encoded([1,2,3,4],0)
            base.preview.acknowledge(s)
            produce(5);produce(6)
            require(base.cohort(s)['collecting_mask']==3,'Two-slot bank0 collection differs')
            s.write(0x20069a3c,1)
            for p in range(7,10):
                produce(p)
                require(base.cohort(s)['cohorts']==1 and base.counter(s,'batches')==1,
                    'Bank switch combined old slots with fewer than four new frames')
            produce(10);base.cw.idle(s)
            current=base.source(s)
            require(current['bank']==1 and [f['publication'] for f in current['frames']]==[9,10,7,8],
                'Bank1 slot identities/address order differ')
            require(base.counter(s,'batches')==1 and base.counter(s,'reason')=='source',
                'Consumer used bank0 descriptors with an unrelated bank1 source')
            for f in current['frames']:
                require(f['linear_sha256']==hashlib.sha256(base.linear(packets[f['publication']],dims,stride)).hexdigest(),
                    'Bank1 private linear view differs')
            encoded_checked+=encoded([9,10,7,8],1)
            for i,address in enumerate(base.cw.raw.SLOTS):s.write(0x20380310+4*i,address+0x300000)
            base.cw.idle(s);require(base.counter(s,'batches')==1,'Descriptor repair replayed an already rejected cohort')
            for level in (1,0):s.access(f'set_irq_in {s.boot} capturework-cohort 0 {level}')
            base.cw.idle(s)
            require(base.counter(s,'batches')==1 and base.source(s)['stale']>0,'Stale source pulse replayed a completed generation')
            for p in range(11,15):produce(p)
            base.cw.idle(s)
            require(base.counter(s,'batches')==2 and [f['publication'] for f in base.source(s)['frames']]==[13,14,11,12],
                'Fresh bank1 cohort did not complete after correct descriptors')
            checked+=base.verify_outputs(s,[13,14,11,12],packets,dims,stride)
            require(s.get('raw-accepted')==0 and s.get('raw-stream-frames',s.boot)==0,'Bank audit changed a legacy acquisition counter')
            proof['final_source']=base.source(s);proof['final_cohort']=base.cohort(s)
        proof.update(actual_CW_frames=14,actual_preview_batches=2,
            encoded_guest_RAW_bytes_independently_verified=encoded_checked,NV12_bytes_independently_verified=checked,
            bank_switch_requires_four_fresh_slots=True,wrong_bank_source_rejected=True,
            corrected_descriptor_no_replay=True,stale_generation_pulse_rejected=True,
            guest_encoded_RAW_preserved=True,legacy_RAW_counters_unchanged=True,completed=True)
    except Exception as exc:proof['failure']={'type':type(exc).__name__,'message':str(exc)}
    with output.open('x',encoding='utf-8') as handle:json.dump(proof,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in proof.items() if k not in ('source_sha256','sessions','effective_commands','final_source','final_cohort')},ensure_ascii=False),flush=True)
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--qemu',type=Path,default=base.hardware.DEFAULT_QEMU)
    parser.add_argument('--state',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();proof=check(args.qemu,args.state,args.output);raise SystemExit(0 if proof['completed'] else 1)
