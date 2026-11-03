"""Preserve the exact generated host, commands and logs of an isolated session."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.error
import urllib.parse
import urllib.request

from z62_paired_console import private_staging


def archive(session,output,url=None):
    source=private_staging(session/'source'); session=source.parent
    require=json.loads((session/'session.json').read_text(encoding='utf-8'))
    if require.get('profile')!='z62':
        raise ValueError('Not a Z62 session')
    output.mkdir(parents=True,exist_ok=False)
    if url is not None:
        parsed=urllib.parse.urlsplit(url)
        if (parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or not parsed.port or
                parsed.path not in ('','/') or parsed.query or parsed.fragment):
            raise ValueError('Only the explicitly selected local console may be observed')
        snapshot={}
        for endpoint in ('/status','/software/status'):
            try:
                with urllib.request.urlopen(url.rstrip('/')+endpoint,timeout=40) as response:
                    snapshot[endpoint]={'status':response.status,'value':json.load(response)}
            except urllib.error.HTTPError as exc:
                snapshot[endpoint]={'status':exc.code,'body':exc.read().decode('utf-8','replace')}
            except (OSError,ValueError) as exc:
                snapshot[endpoint]={'error':type(exc).__name__,'message':str(exc)}
        with (output/'http-snapshot.json').open('x',encoding='utf-8') as handle:
            json.dump(snapshot,handle,ensure_ascii=False,indent=2)
    names=['session.json']
    names += [p.relative_to(session).as_posix() for pattern in
        ('effective-command-*.json','source/tools/*.py','source/web-z62/*',
         'runs/*/command.json','runs/*/console.txt') for p in session.glob(pattern) if p.is_file()]
    hashes={}
    if url is not None:
        hashes['http-snapshot.json']=hashlib.sha256((output/'http-snapshot.json').read_bytes()).hexdigest()
    for name in names:
        path=session/name
        if path.is_symlink():
            raise ValueError('Linked artifact is protected')
        data=path.read_bytes(); target=output/name
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as handle:
            handle.write(data)
        hashes[name]=hashlib.sha256(data).hexdigest()
    result={'schema':1,'session':str(session),'snapshot':True,'process_closed_verified':False,
        'file_sha256':hashes,'firmware_included':False,'camera_accessed':False}
    with (output/'archive.json').open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    print(json.dumps({'files':len(hashes),'output':str(output)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--url')
    args=parser.parse_args(); archive(args.session,args.output,args.url)
