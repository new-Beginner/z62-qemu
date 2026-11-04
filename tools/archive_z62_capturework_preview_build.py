"""Record root/generated source identities for the independent r104 build."""
import argparse
import json
from pathlib import Path
import run_z62_capturework_preview as hardware
import z62_capturework_preview_device as device
from record_z62_action_evidence import workspace,digest,require


def record(output):
    output=workspace(output);require(not output.exists(),'Use new CW preview build binding')
    build=hardware.verify_build();work=hardware.DEFAULT_QEMU.parent.parent
    reference=work/'reference-build-manifest.json';tree=Path(json.loads(reference.read_text(encoding='utf-8'))['source'])
    paths=[Path(__file__),Path(hardware.__file__),Path(device.__file__),*device.HEADERS,
        device.ROOT/'tools/build_z62_capturework_preview.py',reference,work/'capturework-preview-build-manifest.json',
        work/'prepared-capturework-preview.json',device.ROOT/'.runtime/relocated-toolchain-manifest-r73.json',
        *(tree/name for name in build['generated_source_sha256'])]
    result={'schema':1,'completed_build_binding':True,'binary_sha256':build['binary_sha256'],
        'parent_binary_sha256':build['parent_binary_sha256'],'camera_accessed':False,
        'source_sha256':{str(p):digest(p) for p in paths},'default_enabled':False,
        'physical_ISP_equivalence':False,'legacy_RAW_counters_modified':False,'metadata_event6_emitted':False}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({'binary_sha256':build['binary_sha256'],'bound_files':len(paths)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    record(parser.parse_args().output)
