"""Read-only C1.70 parameter-store observations from original ROM descriptors.

10101F52 resolves group/offset; 101017D8 reads the typed RAM value. This module
reproduces only those reads, never invokes a guest function or changes a value.
Item meanings require separate runtime evidence; numeric IDs are retained.
"""
from functools import lru_cache
import hashlib
from pathlib import Path
import struct

from export_z62_body_contract import original

ITEMS=(0x0000,0x0001,0x0204,0x0205,0x0206,0x0208,0x0509)
# 0x2101 is a type-8, 42-byte composite in this firmware, not the scalar
# reported by the Z6III reference. Do not coerce it to an integer here.
GROUP_INDEX=0x11917290
DESCRIPTORS=0x1190B944
BASE=0x10020000


@lru_cache(maxsize=1)
def descriptors():
    firmware,identity=original('master')
    rows={}
    for item in ITEMS:
        group_address=GROUP_INDEX+(item>>8)*28
        start=struct.unpack_from('<H',firmware,group_address-BASE)[0]
        index=start+(item&255)
        address=DESCRIPTORS+index*16
        raw=firmware[address-BASE:address-BASE+16]
        if len(raw)!=16:
            raise ValueError('Parameter descriptor escaped original ROM')
        kind=raw[0]
        if kind not in range(8):
            raise ValueError('Unsupported original parameter type')
        pointer=struct.unpack_from('<I',raw,8)[0]
        if not 0xC0000000<=pointer<=0xDFFFFFFC:
            raise ValueError('Parameter value is outside original RAM')
        width=1 if kind in (1,4) else 2 if kind in (2,5) else 4
        rows[item]={'item':hex(item),'index':index,'descriptor':hex(address),'raw':raw.hex(),
                    'type':kind,'pointer':hex(pointer),'width':width,'signed':kind in (4,5),
                    'firmware_sha256':identity}
    return rows


def observe_machine(machine):
    result={}
    for item,row in descriptors().items():
        pointer=int(row['pointer'],16)
        word=machine._words(pointer,1)[0]
        raw=word.to_bytes(4,'little')[:row['width']]
        result[hex(item)]={'value':int.from_bytes(raw,'little',signed=row['signed']),
                           'pointer':row['pointer'],'width':row['width']}
    return result


def observe_remote(remote):
    return {hex(item):{'value':int.from_bytes(remote.read(int(row['pointer'],16),row['width']),
                                            'little',signed=row['signed']),
                       'pointer':row['pointer'],'width':row['width']}
            for item,row in descriptors().items()}


def identity():
    return {'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'descriptors':descriptors(),'guest_memory_written':False,'guest_functions_called':False}
