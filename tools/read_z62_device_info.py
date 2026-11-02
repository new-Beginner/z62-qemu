"""Restricted Windows WPD diagnostic: Z6II identity and PTP GetDeviceInfo only.
Default is offline self-test. --read-camera permits one 0x1001 attempt.
--read-write-handle explicitly expands host access; no camera write operations.
comtypes and its generated bindings are confined to PI_SCRATCH_DIR.
"""
import argparse
import ctypes as C
from datetime import datetime
import json
import os
from pathlib import Path
import struct
import sys

VERSION = '0.1.2'
CLIENT_GUID = '{204D9F0C-2292-4080-9F42-40664E70F859}'
DEVICE_GUID = '{26D4979A-E643-4626-9E2B-736DC0C92FDC}'
COMMON_GUID = '{F0422A9C-5DC8-4440-B5BD-5DF28835658A}'
MTP_GUID = '{4D545058-1A2E-4106-A357-771E0819FC56}'
MAX_DATA = 1024 * 1024


class WpdCommandError(RuntimeError):
    def __init__(self, hresult):
        self.hresult = hresult
        super().__init__('WPD command failed')


def error_record(exc):
    hr = getattr(exc, 'hresult', None)
    return {'type': type(exc).__name__,
            'hresult': None if hr is None else f'0x{hr & 0xFFFFFFFF:08X}'}


def parse_device_info(data):
    pos = 0

    def take(n):
        nonlocal pos
        if n < 0 or pos + n > len(data):
            raise ValueError('truncated DeviceInfo')
        value = data[pos:pos+n]
        pos += n
        return value

    def number(fmt):
        return struct.unpack('<' + fmt, take(struct.calcsize('<' + fmt)))[0]

    def string():
        n = number('B')
        if not n:
            return ''
        raw = take(n * 2)
        if raw[-2:] != b'\0\0':
            raise ValueError('unterminated PTP string')
        return raw[:-2].decode('utf-16-le', errors='strict')

    def codes():
        n = number('I')
        if n > 32768:
            raise ValueError('oversized code array')
        return [f'0x{number("H"):04X}' for _ in range(n)]

    result = {'standard_version': number('H'), 'vendor_extension_id': number('I'),
              'vendor_extension_version': number('H'), 'vendor_extension_description': string(),
              'functional_mode': number('H')}
    for key in ('operations_supported', 'events_supported', 'device_properties_supported',
                'capture_formats', 'image_formats'):
        result[key] = codes()
    for key in ('manufacturer', 'model', 'device_version'):
        result[key] = string()
    string()  # Consume but NEVER retain or print the serial number.
    result['serial_number'] = '[redacted]'
    if pos != len(data):
        raise ValueError('unexpected trailing DeviceInfo bytes')
    return result


def self_test():
    def s(text):
        return bytes([len(text)+1]) + text.encode('utf-16-le') + b'\0\0'
    fixture = struct.pack('<HIH', 100, 10, 100) + s('test') + struct.pack('<H', 0)
    fixture += struct.pack('<IH', 1, 0x1001) + struct.pack('<I', 0) * 4
    fixture += s('Nikon') + s('Z 6_2') + s('1.70') + s('PRIVATE-SERIAL')
    result = parse_device_info(fixture)
    assert result['operations_supported'] == ['0x1001']
    assert result['device_version'] == '1.70'
    assert 'PRIVATE-SERIAL' not in json.dumps(result)
    for invalid in (fixture[:-1], fixture + b'X', b''):
        try:
            parse_device_info(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError('malformed input accepted')
    print('OFFLINE PASS: valid parser, serial redaction, 3 malformed inputs; no camera access')


def query(output, read_write_handle=False):
    access = 0xC0000000 if read_write_handle else 0x80000000
    access_name = 'GENERIC_READ|GENERIC_WRITE' if read_write_handle else 'GENERIC_READ'
    scratch = Path(os.environ['PI_SCRATCH_DIR'])
    sys.path.insert(0, str(scratch / 'wpd-python'))
    import comtypes
    import comtypes.client as client
    cache = scratch / 'wpd-com-cache'
    cache.mkdir(exist_ok=True)
    client.gen_dir = str(cache)
    api = client.GetModule('C:/Windows/System32/PortableDeviceApi.dll')
    types = client.GetModule('C:/Windows/System32/PortableDeviceTypes.dll')
    free = C.windll.ole32.CoTaskMemFree
    free.argtypes = [C.c_void_p]
    free.restype = None
    result = {'tool_version': VERSION, 'started': datetime.now().astimezone().isoformat(),
              'requested_access': access_name, 'explicit_ptp_allowlist': ['0x1001'],
              'photos_accessed': False, 'settings_written': False,
              'notes': ['WPD may manage its own protocol session/cache.',
                        'No vendor opcodes are executed, even if advertised.',
                        'Raw DeviceInfo and serial number are not saved.'],
              'steps': [], 'wpd_properties': {}, 'device_info': None}
    device = None
    opened = False

    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def record(name, **fields):
        result['steps'].append({'step': name, 'time': datetime.now().astimezone().isoformat(), **fields})
        save()
        print(name, fields, flush=True)

    error = error_record

    def key(guid, pid):
        return api._tagpropertykey(comtypes.GUID(guid), pid)

    def values():
        return client.CreateObject(types.PortableDeviceValues, interface=api.IPortableDeviceValues)

    def command(pid):
        if pid not in (13, 15, 17):
            raise ValueError('WPD command outside read allowlist')
        v = values()
        v.SetGuidValue(key(COMMON_GUID, 1001), comtypes.GUID(MTP_GUID))
        v.SetUnsignedIntegerValue(key(COMMON_GUID, 1002), pid)
        return v

    def send(pid, params):
        record('WPD_SendCommand_begin', command_id=pid)
        response = device.SendCommand(0, params)
        hr = response.GetErrorValue(key(COMMON_GUID, 1003)) & 0xFFFFFFFF
        record('WPD_SendCommand_result', command_id=pid, hresult=f'0x{hr:08X}')
        if hr & 0x80000000:
            raise WpdCommandError(hr)
        return response

    try:
        record('enumerate_WPD')
        manager = client.CreateObject(api.PortableDeviceManager, interface=api.IPortableDeviceManager)
        count = C.c_ulong(0)
        raw_get = manager._IPortableDeviceManager__com_GetDevices
        raw_get(None, C.byref(count))
        if not 0 < count.value <= 64:
            raise RuntimeError('unexpected device count')
        ids = (C.c_wchar_p * count.value)()
        raw_get(ids, C.byref(count))
        candidates = []
        try:
            for i in range(count.value):
                value = ids[i]
                if 'VID_04B0&PID_044C' in value.upper():
                    candidates.append(value)
        finally:
            addresses = C.cast(ids, C.POINTER(C.c_void_p))
            for i in range(count.value):
                if addresses[i]:
                    free(addresses[i])
        record('target_match', count=len(candidates), vid_pid='04B0:044C')
        if len(candidates) != 1:
            raise RuntimeError('require exactly one Z6II')
        ci = values()
        ci.SetStringValue(key(CLIENT_GUID, 2), 'Z62 read-only diagnostic')
        for pid, value in ((3, 0), (4, 1), (5, 2), (9, access)):
            ci.SetUnsignedIntegerValue(key(CLIENT_GUID, pid), value)
        device = client.CreateObject(api.PortableDevice, interface=api.IPortableDevice)
        record('WPD_Open_begin', access=access_name)
        device.Open(candidates[0], ci)
        opened = True
        record('WPD_Open_success')
        keys = client.CreateObject(types.PortableDeviceKeyCollection, interface=api.IPortableDeviceKeyCollection)
        names = {3: 'firmware_version', 7: 'manufacturer', 8: 'model'}
        for pid in names:
            keys.Add(key(DEVICE_GUID, pid))
        props = device.Content().Properties().GetValues('DEVICE', keys)
        for pid, name in names.items():
            try:
                result['wpd_properties'][name] = props.GetStringValue(key(DEVICE_GUID, pid))
            except Exception as exc:
                result['wpd_properties'][name] = {'unavailable': error(exc)}
        record('WPD_identity_read', **result['wpd_properties'])
        p = command(13)
        p.SetUnsignedIntegerValue(key(MTP_GUID, 1001), 0x1001)
        empty = client.CreateObject(types.PortableDevicePropVariantCollection,
                                   interface=api.IPortableDevicePropVariantCollection)
        p.SetIPortableDevicePropVariantCollectionValue(key(MTP_GUID, 1002), empty)
        response = send(13, p)
        context = response.GetStringValue(key(MTP_GUID, 1006))
        data = bytearray()
        try:
            total = response.GetUnsignedLargeIntegerValue(key(MTP_GUID, 1007))
            record('DeviceInfo_transfer_size', bytes=total)
            if total > MAX_DATA:
                raise ValueError('DeviceInfo exceeds diagnostic size limit')
            while len(data) < total:
                size = min(65536, total - len(data))
                p = command(15)
                p.SetStringValue(key(MTP_GUID, 1006), context)
                p.SetUnsignedIntegerValue(key(MTP_GUID, 1008), size)
                buffer = (C.c_ubyte * size)()
                p.SetBufferValue(key(MTP_GUID, 1012), buffer, size)
                response = send(15, p)
                ptr, actual = response.GetBufferValue(key(MTP_GUID, 1012))
                try:
                    if not 0 < actual <= size:
                        raise ValueError('invalid data length')
                    data.extend(C.string_at(ptr, actual))
                finally:
                    free(C.cast(ptr, C.c_void_p))
        finally:
            p = command(17)
            p.SetStringValue(key(MTP_GUID, 1006), context)
            response = send(17, p)
            code = response.GetUnsignedIntegerValue(key(MTP_GUID, 1003))
            result['ptp_response'] = f'0x{code:04X}'
            record('DeviceInfo_end', response=result['ptp_response'])
        if code != 0x2001:
            raise RuntimeError('PTP non-success response')
        result['device_info'] = parse_device_info(data)
        result['outcome'] = 'device_info_read'
        record('DeviceInfo_parsed', model=result['device_info']['model'],
               version=result['device_info']['device_version'],
               operations=len(result['device_info']['operations_supported']))
    except Exception as exc:
        result['outcome'] = 'partial_or_failed'
        result['failure'] = error(exc)
        record('query_stopped', **result['failure'])
    finally:
        if opened:
            try:
                device.Close()
                record('WPD_Close_success')
            except Exception as exc:
                record('WPD_Close_failure', **error(exc))
        result['finished'] = datetime.now().astimezone().isoformat()
        save()
    print('LOG:', output)
    return 0 if result.get('outcome') == 'device_info_read' else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--read-camera', action='store_true')
    parser.add_argument('--read-write-handle', action='store_true',
                        help='Explicitly authorize a read/write WPD handle; only GetDeviceInfo is sent')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.read_write_handle and not args.read_camera:
        parser.error('--read-write-handle requires --read-camera')
    if args.read_camera:
        if args.output is None or args.output.exists():
            parser.error('--output must name a new log file')
        sys.exit(query(args.output, read_write_handle=args.read_write_handle))
    self_test()
