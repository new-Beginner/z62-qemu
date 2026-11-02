"""Read controller input descriptors during an original master startup stop.

All operations on guest memory and registers are reads. GPIO port/mask evidence
is collected from the executed Z62 controller, not imported from another model.
"""
import argparse
import struct
from pathlib import Path

import trace_z62_preview_lifecycle as lifecycle


def snapshot(remote, registers):
    current = remote.command('qC')
    if not current.startswith('QC'):
        raise RuntimeError('Cannot identify stopped thread')
    thread = int(current[2:], 16)
    before = remote.regs()
    try:
        remote.select_thread(5)
        pointers = struct.unpack('<17I', remote.read(0x200184C8, 68))
        descriptors = []
        for index, pointer in enumerate(pointers):
            if not 0x20000000 <= pointer <= 0x2003FFF0:
                raise ValueError('Controller descriptor not initialized')
            data = remote.read(pointer, 16)
            _, _, port, mask = struct.unpack('<4I', data)
            descriptors.append({'index': index, 'pointer': hex(pointer),
                                'raw': data.hex(), 'port': hex(port),
                                'mask_word': hex(mask), 'pin_mask': hex(mask & 0xffff)})
        return {'controller_thread': 5, 'controller_pc': hex(remote.get(remote.regs(), 'pc')),
                'descriptor_table': '0x200184c8', 'descriptors': descriptors,
                'state_bytes': remote.read(0x200186A6, 46).hex()}
    finally:
        remote.select_thread(thread)
        if remote.regs() != before:
            raise RuntimeError('Stopped thread selection was not restored')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = lifecycle.run(args.output,duration=3,extra_hit_hook=snapshot)
    print(result['summary'])
    raise SystemExit(0 if result['capture_setup_observed'] else 1)
