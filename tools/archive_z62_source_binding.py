"""Preserve exact bound observer/native source bytes before later development."""
import argparse
import hashlib
import json
from pathlib import Path

from record_z62_action_evidence import workspace,digest,require

ROOT=Path(__file__).resolve().parents[1]


def archive(result_path):
    result_path=workspace(result_path); record=json.loads(result_path.read_text(encoding='utf-8'))
    table=record['source_sha256']; output=result_path.parent/'source-snapshot'
    require(not output.exists(),'An existing source snapshot is immutable')
    prepared=[]
    for name,expected in table.items():
        path=Path(name); physical=path.resolve()
        require(physical.is_relative_to(ROOT) and path.suffix in ('.py','.c','.h','.json','.cmd'),
                'Only bound workspace source or command metadata may be archived')
        raw=path.read_bytes(); require(hashlib.sha256(raw).hexdigest()==expected,'Bound source already changed: '+name)
        prepared.append((physical.relative_to(ROOT),raw,expected))
    output.mkdir()
    rows={}
    for relative,data,expected in prepared:
        target=output/relative; target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as handle: handle.write(data)
        rows[relative.as_posix()]=expected
    receipt={'schema':1,'result_sha256':digest(result_path),'source_sha256':rows,
        'original_bytes_preserved':True,'camera_accessed':False}
    with (result_path.parent/'source-archive.json').open('x',encoding='utf-8') as handle:
        json.dump(receipt,handle,ensure_ascii=False,indent=2)
    print(json.dumps({'files':len(rows),'result':str(result_path)}),flush=True)
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result',type=Path,required=True); args=parser.parse_args(); archive(args.result)
