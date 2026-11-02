"""Read original system mode interfaces at a startup RAW descriptor stop."""
import argparse
from pathlib import Path
import struct
import trace_z62_preview_lifecycle as lifecycle


def snapshot(remote, registers):
    def words(address, count):
        return list(struct.unpack('<'+'I'*count, remote.read(address,4*count)))
    table = words(0xC1818FC4, 10)
    interfaces = []
    for index, pointer in enumerate(table):
        if 0x10020000 <= pointer <= 0x124F0000 or 0xC0000000 <= pointer <= 0xDFFFFF00:
            data = words(pointer, 64)
            interfaces.append({'index':index,'pointer':hex(pointer),'words':[hex(w) for w in data]})
        else:
            interfaces.append({'index':index,'pointer':hex(pointer),'unmapped_or_uninitialized':True})
    return {'system_context':'0xc1818be0', 'mode_words':[hex(w) for w in words(0xC1818D34,4)],
            'mode_interface_table':'0xc1818fc4','interfaces':interfaces}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=lifecycle.run(args.output,duration=3,extra_hit_hook=snapshot)
    print(result['summary'])
    raise SystemExit(0 if result['capture_setup_observed'] else 1)
