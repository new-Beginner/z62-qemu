"""Preserve exact bound sources, allowing an identical saved command copy.

Does not recreate a deleted runtime directory or alter the original receipt.
Missing non-command sources and any hash mismatch remain explicit errors.
"""
import argparse
import json
from pathlib import Path
from record_z62_action_evidence import workspace,digest,require

ROOT=Path(__file__).resolve().parents[1]


def archive(result_path):
    result_path=workspace(result_path);record=json.loads(result_path.read_text(encoding='utf-8'))
    output=result_path.parent/'source-snapshot';receipt=result_path.parent/'source-archive.json'
    require(not output.exists() and not receipt.exists(),'An existing source archive is immutable')
    prepared=[];fallbacks={}
    for name,sha in record['source_sha256'].items():
        path=Path(name);physical=path.resolve()
        require(physical.is_relative_to(ROOT) and path.suffix in ('.py','.c','.h','.json','.cmd'),
            'Only workspace runtime/source metadata may be preserved')
        actual=path
        if not actual.is_file() and actual.name=='command.json':
            choices=[result_path.parent/'closed-command.json',result_path.parent/'command.json']
            actual=next((p for p in choices if p.is_file() and digest(p)==sha),path)
            if actual!=path:fallbacks[name]=str(actual)
        require(actual.is_file() and digest(actual)==sha,'Bound source missing or changed: '+name)
        prepared.append((physical.relative_to(ROOT),actual.read_bytes(),sha))
    output.mkdir();rows={}
    for relative,data,sha in prepared:
        target=output/relative;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as handle:handle.write(data)
        rows[relative.as_posix()]=sha
    result={'schema':1,'result_sha256':digest(result_path),'source_sha256':rows,
        'original_bytes_preserved':True,'resolved_from_identical_saved_copy':fallbacks,'camera_accessed':False}
    with receipt.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({'files':len(rows),'saved_copy_fallbacks':len(fallbacks)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--result',type=Path,required=True)
    archive(parser.parse_args().result)
