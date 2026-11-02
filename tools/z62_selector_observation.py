"""Read original C1.70 selector fields at verified input stops; never drive them."""
import hashlib
from pathlib import Path
import struct

VERSION = '2026.11.01-selector-route-observation-r29'
POINTS = {0x10436600: 'before-mcu-decode', 0x1038D886: 'before-input-merge',
          0x102A583C: 'after-change-getter', 0x10540246: 'before-applv-handler'}


def capture(remote, registers):
    pc = registers.get('pc')
    if type(pc) is not int or pc not in POINTS:
        raise ValueError('Not a verified selector observation stop')

    def read(address, size):
        data = remote.read(address, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('Incomplete selector memory read')
        return data

    def scalar(data, offset=0):
        current, previous, changed = struct.unpack_from('<HHI', data, offset)
        return {'current': current, 'previous': previous, 'changed': changed}

    row = {'stage': POINTS[pc], 'scalar': scalar(read(0xC1F7A628, 8)),
           'cached': {'current': struct.unpack('<H', read(0xC1F7A746, 2))[0],
                      'previous': struct.unpack('<H', read(0xC1F7A77A, 2))[0]},
           'decoded_master': struct.unpack('<H', read(0xC25D6FE6, 2))[0],
           'read_only': True}
    value = registers['r0']
    if pc == 0x10436600:
        if type(value) is not int or not 0xC0000000 <= value <= 0xDFFFFF84:
            raise ValueError('MCU input is outside bounded original RAM')
        payload = read(value, 124)
        row.update(input_payload=payload.hex(), wire_selector_57=payload[0x57])
    elif pc == 0x102A583C:
        row['getter_return'] = value
    elif pc == 0x10540246:
        valid = type(value) is int and 0xC0000000 <= value <= 0xDFFFFF70
        row['application_input'] = {'pointer': hex(value), 'available': valid}
        if valid:
            payload = read(value, 144)
            row['application_input'].update(prefix_144=payload.hex(), scalar_7c=scalar(payload, 0x7C))
    return row


def identity():
    return {'version': VERSION, 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'required_original_master_sha256': 'bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4',
            'points': {hex(pc): label for pc, label in POINTS.items()},
            'guest_memory_written': False, 'guest_functions_called': False,
            'physical_selector_identity_verified': False}
