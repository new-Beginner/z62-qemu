"""r107 original RAM writers at actual application transitions, no state writes."""
import importlib
import json
from pathlib import Path
import re
import struct
from z62_cw_reentry_observer import ReentryObserver,MASTER_SHA
from z62_live_ready_observer import ReadyObserver
from trace_z62_upper_waits import memory_watch_address
from z62_statistics_control_snapshot import caller
from probe_z62_capture_submit import owner
from record_z62_action_evidence import digest,require

WATCHES={0xc1811e60:'application-index-word',0xc1821eb8:'observed-C1821EB8-word'}


class ReentryWriteObserver(ReentryObserver):
    def __init__(self,binary):
        super().__init__(binary);self.watches=set()
        self.record.update(version='2026.11.04-CW-reentry-write-r107',memory_writes=[],
            scope='Write observations of original index and C1821EB8 after actual MENU entry',
            watched_words={hex(k):v for k,v in WATCHES.items()})

    def watch(self,address,enable):
        require(address in WATCHES,'Unowned RAM observation')
        require(self.remote.command(f'{"Z" if enable else "z"}2,{address:x},4')=='OK','Cannot update RAM write observation')
        if enable:self.watches.add(address)
        else:self.watches.remove(address)

    def attach(self,machine,layout):
        process=machine.process;actual=Path(process.args[0]).resolve()
        require(process.poll() is None and digest(actual)==digest(self.binary),'Retained process identity differs')
        path=Path(machine.work)/'command.json';command=json.loads(path.read_text(encoding='utf-8'))
        require(Path(command[0]).samefile(self.binary),'Original logical kernel differs')
        endpoint=command[command.index('-gdb')+1];require(re.fullmatch(r'tcp:127\.0\.0\.1:[0-9]+',endpoint),'Own GDB only')
        port=int(endpoint.rsplit(':',1)[1]);observed=owner(port,actual)
        require(observed['ProcessId']==process.pid,'Listener differs from retained process')
        self.machine=machine;self.image=Path(machine.args.master).read_bytes()
        require(__import__('hashlib').sha256(self.image).hexdigest()==MASTER_SHA,'Original master differs')
        self.record.update(owner=observed,actual_binary_sha256=digest(actual),logical_command_sha256=digest(path))
        self.remote=importlib.import_module('analyze.qemu_display').Remote(port)
        self.record['attachment_stop']=self.remote.command('?');self.running=False
        require(self.record['attachment_stop'].startswith(('T05','S05','T02','S02')),'Missing attachment stop')
        self.remote.select_thread(1)
        self.record['initial_words']={hex(a):int.from_bytes(self.remote.read(a,4),'little') for a in WATCHES}
        self.record['attached']=True
        self.record['source_sha256']={str(Path(p).resolve()):digest(Path(p)) for p in (__file__,
            __import__('z62_live_ready_observer').__file__,__import__('z62_cw_reentry_observer').__file__,
            __import__('z62_statistics_control_snapshot').__file__,
            Path(machine.args.master).parent.parent/'source/analyze/qemu_display.py')}
        for address in WATCHES:self.watch(address,True)
        self.resume()

    def registers(self):
        data=self.remote.regs()
        r={name:self.remote.get(data,name) for name in ('pc','lr','sp','r0','r1','r2','r3','r4','r5','r6','r7')}
        r['cpsr']=self.remote.get(data,'cpsr') if 'cpsr' in self.remote.offsets else self.remote.read_register('cpsr')
        return r

    def process_stop(self):
        stop=self.remote.receive();self.running=False;self.record['stops']+=1
        address=memory_watch_address(stop,{a:4 for a in self.watches})
        require(address in WATCHES,'Stop is not an owned write observation')
        found=re.search(r'thread:([0-9a-f]+)',stop);require(found,'Stopped CPU missing')
        thread=found.group(1);self.remote.select_thread(int(thread,16));r=self.registers();pc=r['pc'];sp=r['sp']
        require(0xc0000000<=sp<=0xdfffff00 and not sp&3,'Bounded original stack required')
        require(0x10020008<=pc<=0x10020000+len(self.image)-24,'Writer outside original image')
        ticks,frequency=self.machine._key_clock();start=pc-8
        expected=self.image[start-0x10020000:start-0x10020000+32];actual=self.remote.read(start,32)
        require(actual==expected,'Original writer instruction window differs')
        row={'sequence':len(self.record['hits'])+1,'label':WATCHES[address],'address':hex(address),'thread':thread,
            'registers':r,'virtual_time_ns':ticks*1_000_000_000//frequency,'stop_reply':stop,
            'word_before_original_step':int.from_bytes(self.remote.read(address,4),'little'),
            'all_watched_words_before':{hex(a):int.from_bytes(self.remote.read(a,4),'little') for a in WATCHES},
            'stack_hex':self.remote.read(sp,256).hex(),'original_instruction_window_start':hex(start),
            'original_instruction_window_hex':actual.hex(),'caller':caller(self.remote,r,self.image)}
        # Remove every watched address before one original instruction, including
        # a possible multi-store. A remaining watch must not retrap that step.
        for watched in tuple(self.watches):self.watch(watched,False)
        self.step(thread,rearm=False)
        row['after_original_step_registers']=self.registers()
        row['word_after_original_step']=int.from_bytes(self.remote.read(address,4),'little')
        row['all_watched_words_after']={hex(a):int.from_bytes(self.remote.read(a,4),'little') for a in WATCHES}
        for watched in WATCHES:self.watch(watched,True)
        self.record['hits'].append(row);self.record['memory_writes'].append(row)
        print('REENTRY_WRITE',row['label'],hex(pc),hex(row['word_before_original_step']),
            hex(row['word_after_original_step']),row['virtual_time_ns'],flush=True)
        if self.record['stops']>=64:self.record['scope_limit_reached']=True;self.close('write-budget')
        else:self.resume()

    def close(self,reason='cleanup'):
        if self.remote is not None:
            if self.running:self.record['final_interrupt']=self.remote.interrupt();self.running=False
            self.record['final_words']={hex(a):int.from_bytes(self.remote.read(a,4),'little') for a in WATCHES}
            for address in tuple(self.watches):self.watch(address,False)
        super().close(reason)
