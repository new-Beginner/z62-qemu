"""Native runtime ADC input tests using a synthetic Thumb loop, no firmware."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time

from probe_z62_functional_raw import Session, free_port, connect
from probe_z62_transaction import close_owned_session
from run_z62_analog_input import DEFAULT_QEMU, verify_build


@contextmanager
def session(binary,completion=True):
    with tempfile.TemporaryDirectory(prefix='z62-analog-native-') as folder:
        root=Path(folder)
        program=bytearray(16)
        struct.pack_into('<IIH',program,0,0x20001000,0x08000009,0xe7fe)
        (root/'loop.bin').write_bytes(program)
        qmp_port,wire_port=free_port(),free_port()
        command=[str(binary),'-M','nikon-z72-controller-lab','-kernel',str(root/'loop.bin'),
                 '-display','none','-serial','none','-monitor','none','-nic','none','-S',
                 '-qmp',f'tcp:127.0.0.1:{qmp_port},server=on,wait=off',
                 '-qtest',f'tcp:127.0.0.1:{wire_port},server=on,wait=off','-qtest-log','NUL',
                 '-global','nikon-z72-controller-adc.channel0=1733',
                 '-global','nikon-z72-controller-adc.channel1=3001',
                 '-global','nikon-z72-controller-adc.channel18=4095']
        if not completion:
            command+=['-global','nikon-z72-controller-adc.completion=off']
        with (root/'qemu.log').open('xb') as log:
            process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=log)
        native=Session()
        streams=[]
        sockets=[]
        ready=False
        try:
            sock=connect(qmp_port,process)
            sockets.append(sock)
            sock.settimeout(10)
            native.qmp=sock.makefile('rwb')
            streams.append(native.qmp)
            json.loads(native.qmp.readline())
            native.query('qmp_capabilities')
            ready=True
            sock=connect(wire_port,process)
            sockets.append(sock)
            sock.settimeout(10)
            native.wire=sock.makefile('rwb')
            streams.append(native.wire)
            native.irqs=[]
            candidates=['/machine/unattached/'+item['name'] for item in
                        native.query('qom-list',{'path':'/machine/unattached'})
                        if item['type']=='child<nikon-z72-controller-adc>']
            if len(candidates)!=1:
                raise ValueError('Cannot identify the single controller ADC')
            native.adc=candidates[0]
            yield native
        finally:
            close_owned_session(process,native,streams,sockets,ready)


def checks(binary):
    result={}
    def read(s,address):
        return int(s.access(f'readl {address:#x}').split()[1],16)
    def set_input(s,channel,value,error=False):
        return s.query('qom-set',{'path':s.adc,'property':f'input-channel{channel}','value':value},error=error)
    def get_input(s,channel):
        return s.get(f'input-channel{channel}',s.adc)
    def complete(s,bank,enabled=True):
        s.query('cont')
        try:
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                if read(s,bank)&2:
                    break
                time.sleep(.001)
                if not enabled and time.monotonic()>deadline-1.98:
                    break
        finally:
            s.query('stop')
        assert bool(read(s,bank)&2) is enabled
    with session(binary) as s:
        assert get_input(s,0)==1733 and get_input(s,1)==3001 and get_input(s,18)==4095
        for channel in range(19):
            value=(channel*197+321)&4095
            set_input(s,channel,value)
            assert get_input(s,channel)==value and s.get(f'channel{channel}',s.adc)==value
        before=[get_input(s,ch) for ch in range(19)]
        for value in (-1,4096,65536,True,'123'):
            set_input(s,2,value,error=True)
        set_input(s,19,1,error=True)
        assert before==[get_input(s,ch) for ch in range(19)]
        assert read(s,0x40012000)==0
        result.update(all_channels_mutable=True,legacy_inputs_preserved=True,invalid_values_atomic=True)
        cases=0
        for bank_index in range(3):
            bank=0x40012000+bank_index*0x100
            for resolution in range(4):
                for left in (False,True):
                    s.write(bank+8,0)
                    s.write(bank,0)
                    old_value=3000+bank_index*100+resolution*10+int(left)
                    new_value=513+bank_index*100+resolution*10+int(left)
                    set_input(s,2,old_value)
                    s.write(bank+4,resolution<<24)
                    s.write(bank+0x34,2)
                    control=0x40000001|(0x800 if left else 0)
                    s.write(bank+8,control)
                    # qtest wrote START while the CPU/virtual clock is stopped.
                    assert read(s,bank)&16 and not read(s,bank)&2
                    set_input(s,2,new_value)
                    assert not read(s,bank)&2
                    complete(s,bank)
                    bits=12-2*resolution
                    shift=16-bits if left else 0
                    assert read(s,bank+0x4c)==(old_value>>(12-bits))<<shift
                    assert not read(s,bank)&2
                    s.write(bank+8,control)
                    complete(s,bank)
                    assert read(s,bank+0x4c)==(new_value>>(12-bits))<<shift
                    cases+=1
        result.update(conversion_cases=cases,inflight_latch_verified=True,next_conversion_uses_new_level=True,
                      all_banks_resolutions_alignments=True,eoc_ack_preserved=True)
        set_input(s,2,777)
        s.query('system_reset')
        assert get_input(s,2)==777 and read(s,0x4001204c)==0 and read(s,0x40012000)==0
        s.write(0x40012034,2)
        s.write(0x40012008,0x40000001)
        s.write(0x40012008,0)
        complete(s,0x40012000,False)
        assert read(s,0x4001204c)==0
        result.update(reset_preserves_external_level=True,disable_cancels_pending_conversion=True)
    with session(binary,False) as s:
        set_input(s,2,2100)
        s.write(0x40012034,2)
        s.write(0x40012008,0x40000001)
        set_input(s,2,3100)
        complete(s,0x40012000,False)
        assert read(s,0x4001204c)==0
        result['disabled_completion_not_forged']=True
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu',type=Path,default=DEFAULT_QEMU)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--parent-negative',action='store_true')
    args=parser.parse_args()
    result={'schema':1,'completed':False,'firmware_executed':False}
    with args.output.open('x',encoding='utf-8') as handle:
        try:
            if not args.parent_negative:
                result['binary_sha256']=verify_build(args.qemu)['binary_sha256']
            result.update(checks(args.qemu),completed=True)
        except Exception as exc:
            result['failure']={'type':type(exc).__name__,'message':str(exc)}
        finally:
            json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['completed'] else 1)
