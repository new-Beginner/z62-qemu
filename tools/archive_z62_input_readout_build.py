"""Record the immutable r102 adapter, generated source and build bindings."""
import argparse
import json
from pathlib import Path
import run_z62_input_readout as hardware
import z62_input_readout_device as device
from record_z62_action_evidence import workspace,digest,require


def record(output):
    output=workspace(output);require(not output.exists(),'Use new input-readout build binding')
    build=hardware.verify_build();work=hardware.DEFAULT_QEMU.parent.parent
    reference=work/'reference-build-manifest.json';tree=Path(json.loads(reference.read_text(encoding='utf-8'))['source'])
    paths=[Path(__file__),Path(hardware.__file__),Path(device.__file__),device.HEADER,
        device.ROOT/'tools/build_z62_input_readout.py',reference,work/'input-readout-build-manifest.json',
        work/'prepared-input-readout.json',device.ROOT/'.runtime/relocated-toolchain-manifest-r73.json',
        *(tree/name for name in build['generated_source_sha256'])]
    result={'schema':1,'completed_build_binding':True,'binary_sha256':build['binary_sha256'],
        'parent_binary_sha256':build['parent_binary_sha256'],'camera_accessed':False,
        'source_sha256':{str(p):digest(p) for p in paths},'default_enabled':False,
        'physical_sensor_equivalence':False,'guest_RAW_DMA':False}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({'binary_sha256':build['binary_sha256'],'bound_files':len(paths)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    record(parser.parse_args().output)
