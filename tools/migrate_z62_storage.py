"""Move this project's old runtime into the workspace with per-file SHA checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'.runtime/migrated'
OLD_RUNTIME=Path('<USERPROFILE>/Documents/Z62-QEMU-runtime')
OLD_TEMP=Path('<USERPROFILE>/AppData/Local/Temp')


def plain(path):
    path=Path(path).absolute()
    for part in (path,*path.parents):
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
            raise ValueError('Refusing linked migration path: '+str(part))
    return path


def sources():
    rows=[]
    if OLD_RUNTIME.is_dir():
        rows.append((OLD_RUNTIME,DEST/'c-runtime'))
    for path in sorted(OLD_TEMP.iterdir()):
        if path.name.startswith('z62-') and path.is_dir():
            rows.append((path,DEST/'c-temp'/path.name))
    return rows


def files(root):
    root=plain(root)
    def fail(error):
        raise error
    for directory,children,names in os.walk(root,followlinks=False,onerror=fail):
        directory=plain(directory)
        for name in children:
            plain(directory/name)
        for name in names:
            path=plain(directory/name)
            if not path.is_file():
                raise ValueError('Not a regular file: '+str(path))
            yield path


def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as handle:
        while data:=handle.read(4*1024*1024):
            result.update(data)
    return result.hexdigest()


def inventory(output):
    rows=[]
    for source,target in sources():
        current=list(files(source))
        rows.append({'source':str(source),'target':str(target),'files':len(current),
                     'bytes':sum(path.stat().st_size for path in current)})
    record={'schema':1,'workspace':str(ROOT),'entries':rows,'total_bytes':sum(r['bytes'] for r in rows)}
    with output.open('x',encoding='utf-8') as handle:
        json.dump(record,handle,indent=2)
    print(json.dumps({'directories':len(rows),'files':sum(r['files'] for r in rows),
        'bytes':record['total_bytes'],'largest':sorted(rows,key=lambda r:r['bytes'],reverse=True)[:8]}),flush=True)


def migrate():
    plain(DEST); DEST.mkdir(parents=True,exist_ok=True)
    # NTFS transparent compression preserves all logical bytes, including SD zero regions.
    completed=subprocess.run(['compact.exe','/C','/I','/Q',str(DEST)],capture_output=True)
    if completed.returncode or not (DEST.stat().st_file_attributes & 0x800):
        raise ValueError('Workspace NTFS compression could not be enabled')
    owner=DEST/'migration-owner.json'
    identity={'schema':1,'workspace':str(ROOT),'source_runtime':str(OLD_RUNTIME),'source_temp':str(OLD_TEMP)}
    if owner.exists():
        if json.loads(owner.read_text(encoding='utf-8'))!=identity:
            raise ValueError('Migration owner differs')
    else:
        with owner.open('x',encoding='utf-8') as handle:
            json.dump(identity,handle,indent=2)
    journal_path=DEST/'files.jsonl'
    moved=total=0; next_report=0
    with journal_path.open('a',encoding='utf-8') as journal:
        for source,target in sources():
            source=plain(source); target=plain(target)
            if not target.resolve().is_relative_to(ROOT.resolve()):
                raise ValueError('Migration target escaped workspace')
            source_items=list(files(source))
            for path in source_items:
                relative=path.relative_to(source); destination=plain(target/relative)
                destination.parent.mkdir(parents=True,exist_ok=True)
                before=path.stat()
                if destination.exists():
                    sha=digest(path)
                    if destination.stat().st_size!=before.st_size or digest(destination)!=sha:
                        raise ValueError('Existing destination differs: '+str(destination))
                else:
                    pending=destination.with_name(destination.name+'.z62-migration-part')
                    hasher=hashlib.sha256()
                    # This suffix is reserved for this resumable copy operation.
                    with path.open('rb') as original,pending.open('wb') as copied:
                        while block:=original.read(4*1024*1024):
                            if shutil.disk_usage(ROOT).free<512*1024**2:
                                raise ValueError('Workspace free space fell below 512 MiB; source retained')
                            copied.write(block); hasher.update(block)
                        copied.flush(); os.fsync(copied.fileno())
                    sha=hasher.hexdigest()
                    if pending.stat().st_size!=before.st_size or digest(pending)!=sha:
                        raise ValueError('Copied bytes differ; source retained')
                    after=path.stat()
                    if after.st_size!=before.st_size or after.st_mtime_ns!=before.st_mtime_ns:
                        raise ValueError('Source changed while copying; source retained')
                    if destination.exists():
                        raise ValueError('Concurrent destination creation; source retained')
                    pending.rename(destination)
                    shutil.copystat(path,destination,follow_symlinks=False)
                record={'source':str(path),'target':str(destination),'bytes':before.st_size,'sha256':sha}
                journal.write(json.dumps({**record,'state':'verified-copy'},ensure_ascii=False)+'\n'); journal.flush()
                # This is the move commit: only a byte-verified source is removed.
                plain(path); plain(destination)
                current=path.stat()
                if current.st_size!=before.st_size or current.st_mtime_ns!=before.st_mtime_ns:
                    raise ValueError('Source changed before move commit; source retained')
                path.unlink()
                journal.write(json.dumps({**record,'state':'moved'},ensure_ascii=False)+'\n'); journal.flush()
                moved+=1; total+=before.st_size
                if time.monotonic()>=next_report:
                    print(json.dumps({'moved_files':moved,'logical_bytes':total,'current':str(source),
                        'C_free':shutil.disk_usage('C:/').free,'workspace_free':shutil.disk_usage(ROOT).free}),flush=True)
                    next_report=time.monotonic()+15
            for directory,children,names in os.walk(source,topdown=False,followlinks=False):
                folder=plain(directory)
                if not any(folder.iterdir()):
                    folder.rmdir()
    print(json.dumps({'completed':True,'moved_files':moved,'logical_bytes':total,'journal':str(journal_path)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory',type=Path); parser.add_argument('--migrate-c',action='store_true')
    args=parser.parse_args()
    if args.inventory:
        inventory(args.inventory)
    elif args.migrate_c:
        migrate()
    else:
        parser.error('Choose --inventory or --migrate-c')
