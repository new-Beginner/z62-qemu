"""Archive the verified r92 adapter, generated headers and build manifests."""
import argparse
import json
from pathlib import Path
import archive_z62_source_binding as archive
import run_z62_capturework_statistics as hardware
import z62_capturework_statistics_device as device
from record_z62_action_evidence import workspace,digest,require


def save(output):
    output=workspace(output); require(not output.exists(),'Use a new build binding result')
    record=hardware.verify_build(); work=hardware.DEFAULT_QEMU.parent.parent
    reference=work/'reference-build-manifest.json'
    source=Path(json.loads(reference.read_text(encoding='utf-8'))['source'])
    files=[Path(__file__),Path(hardware.__file__),Path(device.__file__),device.HEADER,
        device.ROOT/'tools/build_z62_capturework_statistics.py',reference,
        work/'capturework-statistics-build-manifest.json',
        *(source/name for name in record['generated_source_sha256'])]
    result={'schema':1,'binary_sha256':record['binary_sha256'],'version':record['version'],
        'source_sha256':{str(path):digest(path) for path in files},'camera_accessed':False}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle: json.dump(result,handle,ensure_ascii=False,indent=2)
    archive.archive(output)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    save(parser.parse_args().output)
