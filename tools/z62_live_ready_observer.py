"""Scoped RSP reads on the current original-code experiment, no inferior writes.

Reuse established ARM/Thumb breakpoint widths, stack deltas and all-point
removal around one original single-step. Never wait for a host UI ready gate.
"""
import importlib
import json
from pathlib import Path
import re
import select
import struct
from z62_kernel_event_layout import contract,resolve,OBJECT
from trace_z62_upper_waits import validate_single_step_reply
from probe_z62_capture_submit import owner
from record_z62_action_evidence import digest,require

CALL=0x10238804
RETURN=0x10238808
RAW_RETURN=0x1035d450
WAIT_ENTRY=0x10111410
AND=0x10111628
SET_ENTRY=0x101110ec
STORE=0x101111c4
PRODUCERS={0x10239080:0x100000,0x1023909e:0x200000,0x102392b2:0x1000000,
    0x102392fc:0x800000,0x10239180:0x4000000}
ARM={WAIT_ENTRY,AND,SET_ENTRY,STORE}
MASK=0x5b00000


class ReadyObserver:
    def __init__(self,binary,target=3):
        self.binary=Path(binary);self.target=target;self.remote=None;self.active=set();self.running=False
        self.machine=None;self.outer=None;self.kernel=None;self.setter=None;self.finished=False
        self.record={'schema':1,'version':'2026.11.04-ready-observer-r96','waits':[], 'hits':[],
            'outside_stops':[],'guest_memory_written':False,'guest_registers_written':False,
            'inferior_calls':False,'completion_or_ready_injected':False,'camera_accessed':False,
            'debug_timing_perturbed':True,'functional_acceptance_eligible':False,'stops':0}

    def arm(self,pc):
        if pc not in self.active:
            require(self.remote.command(f'Z1,{pc:x},{4 if pc in ARM else 2}')=='OK','Cannot install execution breakpoint')
            self.active.add(pc)

    def disarm(self,pc):
        if pc in self.active:
            require(self.remote.command(f'z1,{pc:x},{4 if pc in ARM else 2}')=='OK','Cannot remove execution breakpoint')
            self.active.remove(pc)

    def registers(self):
        raw=self.remote.regs()
        return {n:self.remote.get(raw,n) for n in ('pc','lr','sp','r0','r1','r2','r3','r4','r5','r6','r7')}

    def resume(self):
        self.remote.sock.sendall(b'$c#63')
        require(self.remote.sock.recv(1)==b'+','Missing RSP continue ACK');self.running=True

    def step(self,thread,rearm=True):
        points=set(self.active)
        for pc in tuple(self.active):self.disarm(pc)
        require(self.remote.command('Hc'+thread)=='OK','Cannot select stopped CPU')
        validate_single_step_reply(self.remote.command('s'))
        require(self.remote.command('Hc-1')=='OK','Cannot restore all-CPU continuation')
        if rearm:
            for pc in sorted(points):self.arm(pc)

    def attach(self,machine,layout):
        path=Path(machine.work)/'command.json';command=json.loads(path.read_text(encoding='utf-8'))
        require(Path(command[0]).samefile(self.binary),'Observer command belongs to another kernel')
        endpoint=command[command.index('-gdb')+1]
        require(re.fullmatch(r'tcp:127\.0\.0\.1:[0-9]+',endpoint),'Only own local GDB endpoint is allowed')
        port=int(endpoint.rsplit(':',1)[1]);self.record['owner']=owner(port,self.binary)
        Remote=importlib.import_module('analyze.qemu_display').Remote
        self.remote=Remote(port);self.machine=machine;self.layout=layout
        self.record['attachment_stop']=self.remote.command('?');self.running=False
        require(self.record['attachment_stop'].startswith(('T05','S05','T02','S02')),'No attachment stop')
        self.remote.select_thread(1)
        image=(Path(machine.args.master)).read_bytes();require(contract(image)==layout,'Kernel CB layout differs')
        points={CALL,RETURN,RAW_RETURN,WAIT_ENTRY,AND,SET_ENTRY,STORE,*PRODUCERS}
        self.record['live_anchors']=[]
        for pc in sorted(points):
            raw=image[pc-0x10020000:pc-0x10020000+4]
            require(self.remote.read(pc,4)==raw,'Live original instruction differs')
            self.record['live_anchors'].append({'pc':hex(pc),'bytes':raw.hex(),'mode':'ARM' if pc in ARM else 'Thumb'})
        self.record['initial_event']=resolve(self.remote,layout)
        self.record['source_sha256']={str(p):digest(p) for p in (Path(__file__),path,
            Path(machine.args.master).parent.parent/'source/analyze/qemu_display.py')}
        self.arm(CALL);self.resume()

    def hit(self,label,reg,thread):
        row={'sequence':len(self.record['hits'])+1,'label':label,'thread':thread,'registers':reg,
            'virtual_time_ns':self.machine._key_clock()[0]*1_000_000_000//self.machine._key_clock()[1],
            'event':resolve(self.remote,self.layout)}
        self.record['hits'].append(row)
        print('READY_TRACE',label,hex(reg['r0']),row['event']['pattern'],flush=True)
        return row

    def process_stop(self):
        stop=self.remote.receive();self.running=False;self.record['stops']+=1
        require(stop.startswith('T05'),'Unexpected RSP stop: '+stop)
        match=re.search(r'thread:([0-9a-f]+)',stop);require(match,'Stop lacks CPU identity')
        thread=match.group(1);self.remote.select_thread(int(thread,16));r=self.registers();pc=r['pc']
        require(pc in self.active,'Unowned execution breakpoint')
        accepted=False;already_stepped=False
        if pc==CALL and r['r0']==OBJECT and r['r1']==MASK and self.outer is None:
            self.outer=self.hit('wait-call',r,thread);self.kernel=None
            self.outer['output_pointer']=r['r2'];self.outer['timeout_argument']=r['r3']
            self.disarm(CALL);self.arm(RETURN);self.arm(WAIT_ENTRY)
            for point in PRODUCERS:self.arm(point)
            accepted=True
        elif pc==WAIT_ENTRY and self.outer and r['r0']==int(self.outer['event']['identifier'],16) and r['r1']==MASK:
            self.kernel=self.hit('kernel-wait-entry',r,thread)
            self.kernel['timeout_at_sp']=int.from_bytes(self.remote.read(r['sp'],4),'little')
            require(r['r2']==0,'Target wait is not the recovered AND mode')
            self.disarm(WAIT_ENTRY);self.arm(AND);self.arm(RAW_RETURN);accepted=True
        elif pc==AND and self.kernel and r['sp']==self.kernel['registers']['sp']-48 and r['r4']==int(self.outer['event']['control_block'],16):
            row=self.hit('kernel-and-test',r,thread)
            require(r['r3']==int(row['event']['pattern'],16),'Kernel test/CB pattern differs')
            self.disarm(AND);self.step(thread);already_stepped=True
            after=self.registers();row['missing_after_original_bics']=after['r2']
            require(after['r2']==r['r7']&~r['r3'],'Original BICS result differs');accepted=True
        elif pc in PRODUCERS and self.outer and r['r0']==OBJECT and r['r1']==PRODUCERS[pc]:
            row=self.hit('producer-'+hex(r['r1']),r,thread);accepted=True
            if self.setter is None:
                self.setter={'mask':r['r1'],'producer':row,'entry':None}
                self.arm(SET_ENTRY)
        elif pc==SET_ENTRY and self.setter and r['r0']==int(self.outer['event']['identifier'],16) and r['r1']==self.setter['mask']:
            self.setter['entry']=self.hit('kernel-set-entry',r,thread)
            self.disarm(SET_ENTRY);self.arm(STORE);accepted=True
        elif pc==STORE and self.setter and self.setter['entry'] and r['sp']==self.setter['entry']['registers']['sp']-40 and r['r4']==int(self.outer['event']['control_block'],16):
            row=self.hit('kernel-pattern-store',r,thread)
            require(r['r0']==int(row['event']['pattern'],16)|r['r6'],'Original setter OR differs')
            self.disarm(STORE);self.step(thread);already_stepped=True
            row['after_original_store']=resolve(self.remote,self.layout)
            require(int(row['after_original_store']['pattern'],16)==r['r0'],'Original store result differs')
            self.setter=None;accepted=True
        elif pc==RAW_RETURN and self.outer and self.kernel and r['sp']==self.outer['registers']['sp']-16:
            row=self.hit('kernel-wait-result',r,thread)
            row['signed_result']=r['r0']-(1<<32) if r['r0']&0x80000000 else r['r0']
            self.outer['kernel_result']=row;self.disarm(RAW_RETURN);accepted=True
        elif pc==RETURN and self.outer and r['sp']==self.outer['registers']['sp']:
            row=self.hit('wait-return',r,thread)
            row['output_bits']=int.from_bytes(self.remote.read(self.outer['output_pointer'],4),'little')
            self.outer['return']=row;self.record['waits'].append(self.outer)
            self.outer=None;self.kernel=None;self.setter=None
            for point in tuple(self.active):self.disarm(point)
            accepted=True
            if len(self.record['waits'])<self.target:self.arm(CALL)
            else:self.finished=True
        if not accepted:self.record['outside_stops'].append({'pc':hex(pc),'thread':thread,'sp':hex(r['sp'])})
        if not already_stepped:self.step(thread)
        if self.finished:self.close()
        else:self.resume()

    def tick(self,machine,layout):
        if self.finished:return
        if self.remote is None:
            state=json.loads(machine.qmp.command('qom-get',{'path':'/machine/master-input','property':'capture-group-status'}))
            if state['completed']<2:return
            self.attach(machine,layout)
        for _ in range(8):
            if self.finished or not select.select([self.remote.sock],[],[],.005)[0]:break
            self.process_stop()
        if not self.finished and (self.record['stops']>=384 or machine._key_clock()[0]*1_000_000_000//machine._key_clock()[1]>=7_500_000_000):
            self.record['scope_limit_reached']=True;self.finished=True;self.close()

    def close(self):
        if self.remote is None:return
        try:
            if self.running:self.record['final_interrupt']=self.remote.interrupt();self.running=False
            for pc in tuple(self.active):self.disarm(pc)
            self.record['detach']=self.remote.command('D')
        finally:
            self.remote.sock.close();self.remote=None
