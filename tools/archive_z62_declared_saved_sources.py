"""Preserve exact sources using a verifier-declared identical command copy.

Unlike the older same-directory helper, a verified receipt may point back to
the original run's closed-command.json. Missing non-command sources still fail.
No original directories or receipts are recreated or modified.
"""
import argparse
import json
from pathlib import Path
from record_z62_action_evidence import workspace,digest,require

ROOT=Path(__file__).resolve().parents[1]


def archive(result_path):
    result_path=workspace(result_path);record=json.loads(result_path.read_text(encoding='utf-8'))
    output=result_path.parent/'source-snapshot';receipt=result_path.parent/'source-archive.json'
    require(not output.exists() and not receipt.exists(),'Existing source archives are immutable')
    require(record['completed_evidence_check'] is True,'Declared source fallback needs a completed verifier')
    fallbacks=record.get('saved_identical_command_fallbacks',{});prepared={};used={}
    for name,sha in record['source_sha256'].items():
        path=Path(name);physical=path.resolve();actual=path
        require(physical.is_relative_to(ROOT) and path.suffix in ('.py','.c','.h','.json','.cmd'),
            'Only workspace sources and metadata are allowed')
        if not actual.is_file() and name in fallbacks:
            actual=workspace(fallbacks[name])
            require(path.name=='command.json' and actual.name=='closed-command.json',
                'Only an identical saved original command may substitute a missing source')
            used[name]=str(actual)
        require(actual.is_file() and digest(actual)==sha,'Missing or changed declared source: '+name)
        relative=physical.relative_to(ROOT)
        if relative in prepared:require(prepared[relative][1]==sha,'Canonical source identity conflict')
        else:prepared[relative]=(actual.read_bytes(),sha)
    output.mkdir();rows={}
    for relative,(data,sha) in prepared.items():
        target=output/relative;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as handle:handle.write(data)
        rows[relative.as_posix()]=sha
    result={'schema':1,'result_sha256':digest(result_path),'source_sha256':rows,
        'archive_tool_sha256':digest(Path(__file__)),'original_bytes_preserved':True,
        'resolved_from_verified_identical_saved_copy':used,'camera_accessed':False}
    with receipt.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({'files':len(rows),'verified_saved_copies':len(used)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--result',type=Path,required=True)
    archive(parser.parse_args().result)
