"""r101: original C18A7634/0x800 wait and sensor producer, read-only RSP."""
import importlib
import json
from pathlib import Path
import re
import select
from z62_live_ready_observer import ReadyObserver
from z62_kernel_event_layout import contract,resolve
from probe_z62_capture_submit import owner
from record_z62_action_evidence import digest,require

OBJECT=0xc18a7634;MASK=0x800
CALL=0x102dbbac;RETURN=0x102dbbb0;RAW_RETURN=0x1035d450
WAIT_ENTRY=0x10111410;CALLBACK=0x102d7e26;PRODUCER=0x102d7e52
SET_ENTRY=0x101110ec;STORE=0x101111c4
ARM={WAIT_ENTRY,SET_ENTRY,STORE}


def sensor_state(machine):
    props=('functional-raw-completion','laboratory-frame-completion','raw-source-events',
        'raw-completions','raw-ignored','raw-coalesced','raw-completion-last-reason',
        'frame-completions','init-completions','init-submissions','mode-completions','mode2-completions')
    return {prop:machine.qmp.command('qom-get',{'path':'/machine/master-sensor','property':prop}) for prop in props}


class StopWaitObserver(ReadyObserver):
    def __init__(self,binary):
        super().__init__(binary,target=2)
        self.record.update(version='2026.11.04-stop-wait-r101',callbacks=[],publications=[])

    def attach(self,machine,layout):
        path=Path(machine.work)/'command.json';command=json.loads(path.read_text(encoding='utf-8'))
        require(Path(command[0]).samefile(self.binary),'Stop observer belongs to another QEMU')
        endpoint=command[command.index('-gdb')+1]
        require(re.fullmatch(r'tcp:127\.0\.0\.1:[0-9]+',endpoint),'Own loopback GDB endpoint required')
        port=int(endpoint.rsplit(':',1)[1]);self.record['owner']=owner(port,self.binary)
        self.remote=importlib.import_module('analyze.qemu_display').Remote(port);self.machine=machine
        self.record['attachment_stop']=self.remote.command('?');self.running=False
        require(self.record['attachment_stop'].startswith(('T05','S05','T02','S02')),'Missing attachment stop')
        self.remote.select_thread(1)
        image=Path(machine.args.master).read_bytes();require(contract(image)==layout,'Kernel layout changed')
        self.layout=dict(layout,object=OBJECT);self.record['initial_event']=resolve(self.remote,self.layout)
        self.record['live_anchors']=[]
        for pc in sorted({CALL,RETURN,RAW_RETURN,WAIT_ENTRY,CALLBACK,PRODUCER,SET_ENTRY,STORE}):
            raw=image[pc-0x10020000:pc-0x10020000+4]
            require(self.remote.read(pc,4)==raw,'Stop observation original instruction differs')
            self.record['live_anchors'].append({'pc':hex(pc),'bytes':raw.hex(),'mode':'ARM' if pc in ARM else 'Thumb'})
        self.record['source_sha256']={str(p):digest(p) for p in (Path(__file__),path,
            Path(importlib.import_module('z62_live_ready_observer').__file__),
            Path(machine.args.master).parent.parent/'source/analyze/qemu_display.py')}
        self.arm(CALL);self.arm(CALLBACK);self.arm(PRODUCER);self.resume()

    def hit(self,label,r,thread):
        ticks,frequency=self.machine._key_clock()
        row={'sequence':len(self.record['hits'])+1,'label':label,'thread':thread,'registers':r,
            'virtual_time_ns':ticks*1_000_000_000//frequency,'event':resolve(self.remote,self.layout),
            'sensor':sensor_state(self.machine),
            'sensor_config':self.machine._words(0x20065400,1),
            'sensor_mode_status_mask':self.machine._words(0x20065504,3),
            'input_controls':self.machine._words(0x20068000,7),
            'input_geometry':self.machine._words(0x20069d00,2)}
        self.record['hits'].append(row)
        print('STOP_WAIT',label,hex(r['r0']),row['event']['pattern'],row['virtual_time_ns'],flush=True)
        return row

    def process_stop(self):
        stop=self.remote.receive();self.running=False;self.record['stops']+=1
        require(stop.startswith('T05'),'Unexpected stop-wait RSP result')
        match=re.search(r'thread:([0-9a-f]+)',stop);require(match,'Stop CPU missing')
        thread=match.group(1);self.remote.select_thread(int(thread,16));r=self.registers();pc=r['pc']
        require(pc in self.active,'Unowned stop-wait breakpoint')
        accepted=False;stepped=False
        if pc==CALL and r['r0']==OBJECT and r['r1']==MASK and self.outer is None:
            self.outer=self.hit('wait-call',r,thread);self.kernel=None
            self.outer.update(output_pointer=r['r2'],timeout_argument=r['r3'])
            self.disarm(CALL);self.arm(RETURN);self.arm(WAIT_ENTRY);accepted=True
        elif pc==WAIT_ENTRY and self.outer and r['r0']==int(self.outer['event']['identifier'],16) and r['r1']==MASK:
            self.kernel=self.hit('kernel-wait-entry',r,thread)
            self.kernel['timeout_at_sp']=int.from_bytes(self.remote.read(r['sp'],4),'little')
            require(r['r2']==0,'Original stop wait is not the decoded AND mode')
            self.disarm(WAIT_ENTRY);self.arm(RAW_RETURN);accepted=True
        elif pc==CALLBACK and r['r0']==0x41081004 and r['r1']&2:
            self.record['callbacks'].append(self.hit('sensor-callback-bit1',r,thread));accepted=True
        elif pc==PRODUCER and r['r0']==OBJECT and r['r1']==MASK:
            self.setter={'producer':self.hit('sensor-800-publication',r,thread),'entry':None}
            self.arm(SET_ENTRY);accepted=True
        elif pc==SET_ENTRY and self.setter and r['r0']==int(self.setter['producer']['event']['identifier'],16) and r['r1']==MASK:
            self.setter['entry']=self.hit('kernel-set-entry',r,thread)
            self.disarm(SET_ENTRY);self.arm(STORE);accepted=True
        elif pc==STORE and self.setter and self.setter['entry'] and r['sp']==self.setter['entry']['registers']['sp']-40 and r['r4']==int(self.setter['producer']['event']['control_block'],16):
            row=self.hit('kernel-pattern-store',r,thread)
            require(r['r0']==int(row['event']['pattern'],16)|r['r6'],'Original event OR differs')
            self.disarm(STORE);self.step(thread);stepped=True
            row['after_original_store']=resolve(self.remote,self.layout)
            require(int(row['after_original_store']['pattern'],16)==r['r0'],'Original pattern store differs')
            self.record['publications'].append(row);self.setter=None;accepted=True
        elif pc==RAW_RETURN and self.outer and self.kernel and r['sp']==self.outer['registers']['sp']-16:
            row=self.hit('kernel-wait-result',r,thread);self.outer['kernel_result']=row
            self.disarm(RAW_RETURN);accepted=True
        elif pc==RETURN and self.outer and r['sp']==self.outer['registers']['sp']:
            row=self.hit('wait-return',r,thread)
            row['output_bits']=int.from_bytes(self.remote.read(self.outer['output_pointer'],4),'little')
            self.outer['return']=row;self.record['waits'].append(self.outer);self.outer=None;self.kernel=None
            for point in tuple(self.active):self.disarm(point)
            if len(self.record['waits'])<self.target:
                self.arm(CALL);self.arm(CALLBACK);self.arm(PRODUCER)
            else:self.finished=True
            accepted=True
        if not accepted:self.record['outside_stops'].append({'pc':hex(pc),'thread':thread,'sp':hex(r['sp'])})
        if not stepped:self.step(thread)
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
        if not self.finished and self.record['stops']>=384:
            self.record['scope_limit_reached']=True;self.finished=True;self.close()
