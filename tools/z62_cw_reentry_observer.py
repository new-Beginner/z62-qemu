"""Scoped original-code reentry calls after actual MENU, on frozen C1.70."""
import importlib
import json
from pathlib import Path
import re
import select
import struct
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
from z62_live_ready_observer import ReadyObserver
from probe_z62_capture_submit import owner
from record_z62_action_evidence import digest,require

BASE=0x10020000
MASTER_SHA='bb83613121f843d65101da936d942acdc513d86dbd3abc26259d0d870d03f5d4'
WAIT_CALLS=(0x103999ba,0x103999fc,0x10399bd8,0x1039c1f4,0x1039c318)
FUNCTIONS={0x10397e78:'mode-request',0x102dbb9c:'capture-stop',
    0x102dd9c8:'mode0-stop',0x102dd964:'mode2-stop',0x1023881e:'channels-stop-core'}
STORES={0x1020aafe:'input-start-store'}
POINTS={**FUNCTIONS,**STORES,**{pc:'upper-wait-'+str(i+1) for i,pc in enumerate(WAIT_CALLS)}}


def contract(image):
    require(__import__('hashlib').sha256(image).hexdigest()==MASTER_SHA,'Original full master differs')
    decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB);anchors=[]
    for pc,label in sorted(POINTS.items()):
        raw=image[pc-BASE:pc-BASE+4];insn=next(iter(decoder.disasm(raw,pc,count=1)),None)
        require(insn is not None,'Original point does not decode')
        if pc in WAIT_CALLS:require((insn.mnemonic,insn.op_str)==('bl','#0x1035d43a'),'Original upper wait BL differs')
        if pc in STORES:require(insn.mnemonic=='str' and insn.op_str=='r1, [r0, #8]','Original input-start store differs')
        anchors.append({'pc':hex(pc),'label':label,'bytes':raw.hex(),'mnemonic':insn.mnemonic,'operands':insn.op_str})
    return anchors


class ReentryObserver(ReadyObserver):
    def __init__(self,binary):
        super().__init__(binary);self.pending={};self.image=None;self.half_ns=None;self.entered_menu=False
        self.record.update(version='2026.11.04-CW-reentry-r106',attached=False,calls=[],returns=[],
            stores=[],outside_stops=[],incomplete_calls=[],scope='Actual MENU entry through first post-half index3 or bounded end')

    def check_anchor(self,pc):
        require(pc%2==0 and BASE<=pc<=BASE+len(self.image)-4,'Point outside original Thumb image')
        raw=self.image[pc-BASE:pc-BASE+4]
        require(self.remote.read(pc,4)==raw,'Live original instruction differs')
        return {'pc':hex(pc),'bytes':raw.hex(),'mode':'Thumb'}

    def attach(self,machine,layout):
        process=machine.process;actual=Path(process.args[0]).resolve()
        require(process.poll() is None and digest(actual)==digest(self.binary),'Retained reentry process identity differs')
        command_path=Path(machine.work)/'command.json'
        command=json.loads(command_path.read_text(encoding='utf-8'))
        require(Path(command[0]).samefile(self.binary),'Logical command belongs to another kernel')
        endpoint=command[command.index('-gdb')+1]
        require(re.fullmatch(r'tcp:127\.0\.0\.1:[0-9]+',endpoint),'Own loopback GDB endpoint required')
        observed=owner(int(endpoint.rsplit(':',1)[1]),actual)
        require(observed['ProcessId']==process.pid,'Listener differs from retained Popen owner')
        self.record.update(owner=observed,actual_binary_sha256=digest(actual),logical_command_sha256=digest(command_path))
        self.machine=machine;self.image=Path(machine.args.master).read_bytes()
        self.record['static_anchors']=contract(self.image)
        self.remote=importlib.import_module('analyze.qemu_display').Remote(int(endpoint.rsplit(':',1)[1]))
        self.record['attachment_stop']=self.remote.command('?');self.running=False
        require(self.record['attachment_stop'].startswith(('T05','S05','T02','S02')),'Missing reentry attachment stop')
        self.remote.select_thread(1)
        self.record['live_anchors']=[self.check_anchor(pc) for pc in POINTS]
        self.record['attached']=True
        self.record['source_sha256']={str(Path(p).resolve()):digest(Path(p)) for p in (__file__,
            __import__('z62_live_ready_observer').__file__,__import__('probe_z62_capture_submit').__file__,
            Path(machine.args.master).parent.parent/'source/analyze/qemu_display.py')}
        for pc in POINTS:self.arm(pc)
        self.resume()

    def process_stop(self):
        stop=self.remote.receive();self.running=False;self.record['stops']+=1
        require(stop.startswith('T05'),'Unexpected reentry stop')
        found=re.search(r'thread:([0-9a-f]+)',stop);require(found,'Stopped CPU missing')
        thread=found.group(1);self.remote.select_thread(int(thread,16));r=self.registers();pc=r['pc']
        require(pc in self.active,'Unowned reentry breakpoint')
        ticks,frequency=self.machine._key_clock();sp=r['sp']
        require(0xc0000000<=sp<=0xdfffff00 and not sp&3,'Bounded original stack required')
        status=struct.unpack('<69I',self.remote.read(0xc253e0c0,276));count=status[-1]
        row={'sequence':len(self.record['hits'])+1,'pc':hex(pc),'thread':thread,'registers':r,
            'virtual_time_ns':ticks*1_000_000_000//frequency,'stack_hex':self.remote.read(sp,256).hex(),
            'application_words':list(struct.unpack('<5I',self.remote.read(0xc1811e50,20))),
            'status_codes':list(status[:count]) if count<=68 else None}
        matches=[p for p in self.pending.get(pc,[]) if p['thread']==thread and p['sp']==sp]
        if matches:
            require(len(matches)==1,'Ambiguous reentry return frame')
            call=matches[0];self.pending[pc].remove(call)
            row.update(label=call['label']+'-return',call_sequence=call['sequence'],
                elapsed_virtual_ns=row['virtual_time_ns']-call['virtual_time_ns'])
            self.record['returns'].append(row)
            if not self.pending[pc] and pc not in POINTS:self.disarm(pc)
        elif pc in STORES:
            row.update(label=STORES[pc],store_base_matches=r['r0']==0x20068000,
                store_value=r['r1'],instruction_not_yet_executed=True)
            self.record['stores'].append(row)
        elif pc in POINTS:
            row['label']=POINTS[pc];return_pc=pc+4 if pc in WAIT_CALLS else r['lr']&~1
            row['return_anchor']=self.check_anchor(return_pc)
            self.pending.setdefault(return_pc,[]).append({'sequence':row['sequence'],'label':row['label'],
                'thread':thread,'sp':sp,'virtual_time_ns':row['virtual_time_ns']})
            self.arm(return_pc);self.record['calls'].append(row)
        else:self.record['outside_stops'].append(row)
        self.record['hits'].append(row)
        print('REENTRY_TRACE',row.get('label','outside-return'),hex(r['r0']),hex(r['lr']),row['virtual_time_ns'],flush=True)
        self.step(thread)
        if self.record['stops']>=192:
            self.record['scope_limit_reached']=True;self.close('stop-budget')
        else:self.resume()

    def tick(self):
        if self.remote is None or self.finished:return
        for _ in range(8):
            if self.remote is None or not select.select([self.remote.sock],[],[],.001)[0]:break
            self.process_stop()

    def close(self,reason='cleanup'):
        self.record['incomplete_calls']=[dict(p,return_pc=hex(pc)) for pc,items in self.pending.items() for p in items]
        if self.remote is None:return
        self.record['close_reason']=reason;super().close();self.finished=True
