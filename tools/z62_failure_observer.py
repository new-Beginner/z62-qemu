"""Read-only r99 original status producer/append and finite consumer windows.

Uses execution breakpoints, original single-steps and source-checked returns.
No software memory/register writes, inferior calls or fabricated completion.
"""
import importlib
import json
from pathlib import Path
import re
import select
import struct
from z62_live_ready_observer import ReadyObserver
from probe_z62_capture_submit import owner
from record_z62_action_evidence import digest,require

POINTS={0x10397ec8:'status-producer',0x103970d4:'status-append-call',
        0x102301bc:'finite-consumer',0x10210b0e:'scalar-consumer'}
BASE=0x10020000


class FailureObserver(ReadyObserver):
    def __init__(self,binary):
        super().__init__(binary)
        self.returns={};self.image=None
        self.record.update(version='2026.11.04-failure-observer-r99',calls=[],returns=[],hits=[],
            incomplete_calls=[],static_points={hex(k):v for k,v in POINTS.items()})

    def check_anchor(self,pc):
        require(pc%2==0 and BASE<=pc<=BASE+len(self.image)-4,'Return outside original Thumb image')
        raw=self.image[pc-BASE:pc-BASE+4]
        require(self.remote.read(pc,4)==raw,'Live original instruction differs')
        return {'pc':hex(pc),'bytes':raw.hex(),'mode':'Thumb'}

    def attach(self,machine,layout):
        path=Path(machine.work)/'command.json';command=json.loads(path.read_text(encoding='utf-8'))
        require(Path(command[0]).samefile(self.binary),'Observer kernel ownership differs')
        endpoint=command[command.index('-gdb')+1]
        require(re.fullmatch(r'tcp:127\.0\.0\.1:[0-9]+',endpoint),'Own loopback GDB only')
        port=int(endpoint.rsplit(':',1)[1]);self.record['owner']=owner(port,self.binary)
        self.remote=importlib.import_module('analyze.qemu_display').Remote(port)
        self.machine=machine;self.image=Path(machine.args.master).read_bytes()
        self.record['attachment_stop']=self.remote.command('?');self.running=False
        require(self.record['attachment_stop'].startswith(('T05','S05','T02','S02')),'No attachment stop')
        self.remote.select_thread(1)
        self.record['live_anchors']=[self.check_anchor(pc) for pc in POINTS]
        self.record['source_sha256']={str(p):digest(p) for p in (Path(__file__),
            Path(importlib.import_module('z62_live_ready_observer').__file__),path,
            Path(machine.args.master).parent.parent/'source/analyze/qemu_display.py')}
        for pc in POINTS:self.arm(pc)
        self.resume()

    def read_ram(self,address,size):
        require(0xc0000000<=address<=0xe0000000-size and 0<size<=512,'Bounded original RAM read required')
        return self.remote.read(address,size)

    def process_stop(self):
        stop=self.remote.receive();self.running=False;self.record['stops']+=1
        require(stop.startswith('T05'),'Unexpected original-code stop: '+stop)
        match=re.search(r'thread:([0-9a-f]+)',stop);require(match,'Stopped CPU missing')
        thread=match.group(1);self.remote.select_thread(int(thread,16));r=self.registers();pc=r['pc']
        require(pc in self.active,'Unowned execution breakpoint')
        ticks,frequency=self.machine._key_clock()
        row={'sequence':len(self.record['hits'])+1,'pc':hex(pc),'thread':thread,'registers':r,
            'virtual_time_ns':ticks*1_000_000_000//frequency,
            'stack_hex':self.read_ram(r['sp'],256).hex()}
        status=struct.unpack('<69I',self.read_ram(0xc253e0c0,276));count=status[-1]
        row['status_count']=count;row['status_codes']=list(status[:count]) if count<=68 else None
        matches=[entry for entry in self.returns.get(pc,[]) if entry['thread']==thread and entry['sp']==r['sp']]
        if matches:
            require(len(matches)==1,'Ambiguous original return frame')
            call=matches[0];self.returns[pc].remove(call)
            row.update(label=call['label']+'-return',call_sequence=call['sequence'])
            if call.get('output_pointer'):
                row['output_hex']=self.read_ram(call['output_pointer'],8).hex()
            self.record['returns'].append(row)
            if not self.returns[pc] and pc not in POINTS:self.disarm(pc)
        else:
            require(pc in POINTS,'Unmatched dynamic return')
            row['label']=POINTS[pc]
            if pc in (0x10210b0e,):
                row['input_hex']=self.read_ram(r['r0'],8).hex()
                row['output_pointer']=r['r1']
            return_pc=pc+4 if pc==0x103970d4 else r['lr']&~1
            row['return_anchor']=self.check_anchor(return_pc)
            key={'sequence':row['sequence'],'label':row['label'],'thread':thread,'sp':r['sp'],
                'output_pointer':row.get('output_pointer')}
            self.returns.setdefault(return_pc,[]).append(key);self.arm(return_pc)
            self.record['calls'].append(row)
        self.record['hits'].append(row)
        print('FAILURE_TRACE',row['label'],hex(r['r0']),hex(r['lr']),row['virtual_time_ns'],flush=True)
        self.step(thread)
        if self.record['stops']>=128:
            self.finished=True;self.record['scope_limit_reached']=True;self.close()
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

    def close(self):
        self.record['incomplete_calls']=[dict(row,return_pc=hex(pc)) for pc,rows in self.returns.items() for row in rows]
        super().close()
