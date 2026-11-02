"""Read application input method pointers from the initialized original manager."""
import argparse
from pathlib import Path
import struct
import trace_z62_preview_lifecycle as lifecycle


def snapshot(remote, registers):
    manager = remote.read(0xC1811E50, 88)
    applications = []
    for index in range(5):
        getter, context, ready = struct.unpack_from('<III', manager, 28+12*index)
        item = {'index':index,'getter':hex(getter),'context':hex(context),'ready':ready}
        if 0xC0000000 <= context <= 0xDFFFFF00:
            data = remote.read(context, 128)
            item['header_128'] = data.hex()
            item['input_method'] = hex(struct.unpack_from('<I', data, 0x44)[0])
        applications.append(item)
    return {'manager':'0xc1811e50','foreground':manager[16],'applications':applications}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=lifecycle.run(args.output,duration=3,extra_hit_hook=snapshot)
    print(result['summary'])
    raise SystemExit(0 if result['capture_setup_observed'] else 1)
