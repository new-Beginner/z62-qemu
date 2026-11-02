"""Prepare a persistent ASCII runtime and new explicitly synthetic fixtures."""
import argparse
import hashlib
import json
from pathlib import Path

import setup_ghidra
from z62_virtual_sd import create_fat32,digest


def prepare(root):
    root=root.resolve()
    if not str(root).isascii() or ',' in str(root) or root.is_symlink():
        raise ValueError('Use a regular ASCII task runtime directory')
    root.mkdir(parents=True,exist_ok=True)
    for name in ('sessions','fixtures'):
        (root/name).mkdir(exist_ok=True)
    destination=root/'fixtures/r21-runtime.json'
    if destination.exists():
        record=json.loads(destination.read_text(encoding='utf-8'))
        for name in ('card','group23'):
            if digest(Path(record[name]['path']))!=record[name]['sha256']:
                raise ValueError('Existing fixture identity changed: '+name)
        if not Path(record['ghidra']['headless']).is_file():
            raise ValueError('Existing persistent Ghidra is missing')
        return record
    group=root/'fixtures/group23.bin'
    data=bytes(0xE0000-4)+b'ENDM'
    expected='c7dd14358b45b2813fdee85fc587bcdd5899f7a81e0d5830513d631235bcc700'
    if hashlib.sha256(data).hexdigest()!=expected:
        raise ValueError('Synthetic fixture definition differs')
    if group.exists():
        if digest(group)!=expected:
            raise ValueError('Existing NOR23 fixture is different')
    else:
        with group.open('xb') as handle:
            handle.write(data)
    card=root/'fixtures/card-r21.raw'
    geometry=create_fat32(card,512)
    print('New 512 MiB synthetic card:',card,flush=True)
    installation=setup_ghidra.setup(root/'ghidra-11.4.2')
    record={'schema':1,'root':str(root),'scratch':str(root/'sessions'),
            'card':{'path':str(card),'sha256':digest(card),'geometry':geometry,'synthetic':True},
            'group23':{'path':str(group),'sha256':expected,'factory_calibration':False},
            'ghidra':installation,'original_deleted_temp_files_recreated':False,'camera_accessed':False}
    with destination.open('x',encoding='utf-8') as handle:
        json.dump(record,handle,indent=2)
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(prepare(args.root),indent=2))
