"""Apply the C pixel core to synthetic MAIN data with observed Z62 geometry/LUT.

This is a standalone numerical fixture. It performs no QEMU DMA or notification
and does not turn a register readback into commit or sensor-input provenance.
"""
import argparse
import json
from pathlib import Path
import subprocess
import traceback

from record_z62_action_evidence import workspace,digest,require
import z62_capturework_native as native


def profile(state):
    require(state['completed_observation'] and state.get('detach')=='OK' and
            state['sources_unchanged'] and not state.get('failure'),'Valid observed state required')
    front={int(k,16):int(v,16) for k,v in state['frontend'].items()}
    packing={int(k,16):int(v,16) for k,v in state['packing'].items()}
    require(front[0x20068500]==0 and front[0x20069F00]==0x11,'Unsupported correction/geometry enable')
    registers=[front[a] for a in (0x20069D04,0x20069D00,0x20069E7C,0x20069E78)]
    registers += [packing[a] for a in (0x20069518,0x2006951C)]
    require(all(v and not v&0xffff for v in registers),'Unsupported crop or zero extent')
    dimensions=[v>>16 for v in registers]
    require(all(0<v<=4096 and not v&1 for v in dimensions) and dimensions[0]*dimensions[1]<=4*1024*1024,
            'Source fixture exceeds bounded even MAIN profile')
    require(not packing[0x20069514]&~7 and (packing[0x20069514]&3)<=2 and
            all(packing[a]==0 for a in (0x20069520,0x20069524,0x20069528)) and
            packing[0x2006952C]==2,'Unsupported packing controls')
    require(packing[0x20069514]&4,'This observed-LUT fixture requires the enabled curve')
    bits=(16,14,12)[packing[0x20069514]&3]
    lut=[(word>>(16*half))&65535 for word in state['packing_lut_words'] for half in (0,1)]
    require(len(lut)==256 and all(0<=v<1<<bits for v in lut) and all(b>a for a,b in zip(lut,lut[1:])),
            'Unsupported LUT')
    stride=int(state['buffers']['0x20069a08'],16)
    require(stride==(dimensions[4]*bits//8+15)//16*16,'Observed packed stride differs')
    return dimensions,bits,stride,lut


def run(state_path,output):
    state_path,output=map(workspace,(state_path,output)); output.mkdir(parents=True,exist_ok=False)
    record={'schema':1,'version':'2026.11.04-capturework-pixels-r86',
        'scope':'synthetic MAIN numerical fixture using observed register geometry and LUT',
        'completed':False,'camera_accessed':False,'qemu_dma_performed':False,'completion_injected':False,
        'device_integration_complete':False,'source_MAIN_provenance_established':False,
        'configuration_write_provenance_established':False,'physical_sampling_verified':False}
    state=json.loads(state_path.read_text(encoding='utf-8'))
    try:
        dimensions,bits,stride,lut=profile(state)
        exe,environment=native.compile_probe(output/'native')
        packed=output/'synthetic-frame.p12'
        require(not packed.exists(),'Do not replace an output')
        result=native.run(exe,environment,'live',*dimensions,bits,stride,','.join(map(str,lut)),packed)
        require(result['completed'] and result['independent_two_pass_reference'] and result['padding_preserved'],
                'Native numerical comparison failed')
        raw=packed.read_bytes(); require(len(raw)==stride*dimensions[5],'Packed output extent differs')
        record.update(completed=True,dimensions=dimensions,bits=bits,stride=stride,native_result=result,
            transfer_codec='lookup8-high-byte',inverse_transfer_verified=False,
            packed_sha256=digest(packed),observed_state_sha256=digest(state_path),
            executable_sha256=digest(exe),source_sha256={str(p):digest(p) for p in
                (Path(__file__),native.ROOT/'qemu/z62-capturework/nikon-z62-capturework-pixels.h',
                 native.ROOT/'tests/native/z62_capturework_pixels_probe.c',Path(native.__file__))},
            compiler_version=subprocess.run([str(native.ascii_root()/'.runtime/tools/msys64/ucrt64/bin/gcc.exe'),'--version'],
                env=environment,capture_output=True,text=True,check=True).stdout.splitlines()[0])
    except Exception as exc:
        record['failure']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    with (output/'result.json').open('x',encoding='utf-8') as handle: json.dump(record,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in record.items() if k!='source_sha256'},ensure_ascii=False),flush=True)
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); result=run(args.state,args.output)
    raise SystemExit(0 if result['completed'] else 1)
