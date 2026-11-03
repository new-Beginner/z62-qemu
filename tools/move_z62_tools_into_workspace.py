"""Relocate the task-owned toolchain and sessions on the same D volume."""
import hashlib
import json
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parent/'z62-qemu-tools'
TARGET=ROOT/'.runtime/tools'


def inventory(root):
    result={}; last=0
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            raise ValueError('Linked tool entry requires separate review: '+str(path))
        if not path.is_file():
            continue
        sha=hashlib.sha256()
        with path.open('rb') as handle:
            while data:=handle.read(4*1024*1024):
                sha.update(data)
        result[path.relative_to(root).as_posix()]={'bytes':path.stat().st_size,'sha256':sha.hexdigest()}
        if time.monotonic()-last>=15:
            print(json.dumps({'root':str(root),'hashed_files':len(result)}),flush=True); last=time.monotonic()
    return result


if __name__=='__main__':
    if not SOURCE.is_dir() or TARGET.exists() or SOURCE.is_symlink() or SOURCE.is_junction():
        raise ValueError('Expected the existing task-owned source and an absent workspace target')
    if not TARGET.resolve().is_relative_to(ROOT.resolve()) or SOURCE.resolve()!=ROOT.parent/'z62-qemu-tools':
        raise ValueError('Relocation paths differ from the named workspace targets')
    owner=json.loads((SOURCE/'z62-toolchain-owner.json').read_text(encoding='utf-8'))
    if Path(owner['workspace']).resolve()!=ROOT.resolve():
        raise ValueError('The toolchain belongs to another workspace')
    before=inventory(SOURCE)
    plan=ROOT/'.runtime/tools-relocation.json'
    with plan.open('x',encoding='utf-8') as handle:
        json.dump({'schema':1,'source':str(SOURCE),'target':str(TARGET),'state':'verified-before-move','files':before},handle,indent=2)
    # Both named paths are verified; same-volume rename preserves file contents.
    SOURCE.rename(TARGET)
    after=inventory(TARGET)
    if before!=after:
        raise ValueError('Relocated inventory differs; preserve both the plan and destination')
    with (ROOT/'.runtime/tools-relocation-verified.json').open('x',encoding='utf-8') as handle:
        json.dump({'schema':1,'source':str(SOURCE),'target':str(TARGET),'verified':True,'files':after},handle,indent=2)
    print(json.dumps({'verified':True,'files':len(after),'bytes':sum(row['bytes'] for row in after.values()),'target':str(TARGET)}),flush=True)
