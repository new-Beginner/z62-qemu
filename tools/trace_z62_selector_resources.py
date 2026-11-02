"""Read original MCU selector/ADC resources at a master input-message stop."""
import argparse
from pathlib import Path
import struct

import probe_z62_no_lens as baseline


def snapshot(remote, registers):
    if registers['pc'] != 0x10436600:
        return {}
    payload = remote.read(registers['r0'],124)
    current = remote.command('qC')
    if not current.startswith('QC'):
        raise ValueError('Cannot identify stopped thread')
    thread = int(current[2:],16)
    before = remote.regs()
    try:
        remote.select_thread(5)
        descriptor = struct.unpack('<I',remote.read(0x20018460,4))[0]
        if not 0x20000000 <= descriptor <= 0x2003FFC0:
            raise ValueError('ADC resource descriptor is not initialized')
        pointers = struct.unpack('<17I',remote.read(0x200184C8,68))
        gpio = []
        for index in (0,1,2,10,16):
            raw = remote.read(pointers[index],16)
            words = struct.unpack('<4I',raw)
            gpio.append({'index':index,'pointer':hex(pointers[index]),'raw':raw.hex(),
                         'port':hex(words[2]),'mask':hex(words[3]&0xffff)})
        return {'input_payload':payload.hex(), 'wire_mode':payload[15],
                'selector_state_48':remote.read(0x20018438,48).hex(),
                'mode_adc_irq_selector':remote.read(0x20018447,1)[0],
                'mode_adc_resource_pointer':hex(descriptor),
                'mode_adc_resource_64':remote.read(descriptor,64).hex(),
                'gpio_descriptors':gpio}
    finally:
        remote.select_thread(thread)
        if remote.regs() != before:
            raise RuntimeError('Thread selection changed the stopped CPU')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--card',type=Path,required=True)
    parser.add_argument('--group23',type=Path,required=True)
    args=parser.parse_args()
    result,receipt=baseline.run(args.output,args.card,args.group23,True,False,3,
        extra_points={0x10436600:'selector-resource-input'},extra_hit_hook=snapshot,max_stops=50)
    print(receipt)
    raise SystemExit(0 if receipt['observation_completed'] else 1)
