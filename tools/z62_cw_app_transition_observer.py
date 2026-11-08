"""r108 observe actual manager stores, notifications and optional callback past index3."""
import struct
import re
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
from z62_cw_reentry_observer import ReentryObserver,WAIT_CALLS,FUNCTIONS,MASTER_SHA,BASE
from record_z62_action_evidence import require

CALLS={**{pc:4 for pc in WAIT_CALLS},0x1029a92a:4,0x1029a94e:4,0x1029a906:2}
MARKERS={0x1029a8ea:'manager-active-index-store',0x1029a916:'manager-request-index-store',
    0x1020aafe:'input-start-store'}
POINTS={**FUNCTIONS,**{pc:'upper-wait-'+str(i+1) for i,pc in enumerate(WAIT_CALLS)},
    0x1029a92a:'manager-call-1035cb1e',0x1029a94e:'manager-call-1035cb1a',
    0x1029a906:'manager-optional-callback',**MARKERS}


def contract(image):
    require(__import__('hashlib').sha256(image).hexdigest()==MASTER_SHA,'Original master differs')
    decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB);anchors=[]
    for pc,label in sorted(POINTS.items()):
        raw=image[pc-BASE:pc-BASE+4];insn=next(iter(decoder.disasm(raw,pc,count=1)),None)
        require(insn is not None,'Manager point does not decode')
        if pc in WAIT_CALLS:require((insn.mnemonic,insn.op_str)==('bl','#0x1035d43a'),'Original wait differs')
        if pc in (0x1029a92a,0x1029a94e):require(insn.mnemonic=='bl' and insn.size==4,'Original manager BL differs')
        if pc==0x1029a906:require((insn.mnemonic,insn.op_str,insn.size)==('blx','r3',2),'Original callback BLX differs')
        if pc==0x1029a8ea:require((insn.mnemonic,insn.op_str)==('strb','r3, [r4]'),'Original active-index store differs')
        if pc==0x1029a916:require((insn.mnemonic,insn.op_str)==('strb','r1, [r4, #1]'),'Original requested-index store differs')
        anchors.append({'pc':hex(pc),'label':label,'bytes':raw.hex(),'mnemonic':insn.mnemonic,'operands':insn.op_str})
    return anchors


class AppTransitionObserver(ReentryObserver):
    def __init__(self,binary):
        super().__init__(binary)
        self.record.update(version='2026.11.04-CW-app-transition-r108',
            scope='Actual MENU through bounded end, including original operations after index3 assignment')

    def process_stop(self):
        stop=self.remote.receive();self.running=False;self.record['stops']+=1
        require(stop.startswith('T05'),'Unexpected manager stop')
        found=re.search(r'thread:([0-9a-f]+)',stop);require(found,'Stopped CPU missing')
        thread=found.group(1);self.remote.select_thread(int(thread,16));r=self.registers();pc=r['pc'];sp=r['sp']
        require(pc in self.active and 0xc0000000<=sp<=0xdfffff00 and not sp&3,'Unowned manager point or stack')
        ticks,frequency=self.machine._key_clock();status=struct.unpack('<69I',self.remote.read(0xc253e0c0,276));count=status[-1]
        row={'sequence':len(self.record['hits'])+1,'pc':hex(pc),'thread':thread,'registers':r,
            'virtual_time_ns':ticks*1_000_000_000//frequency,'stack_hex':self.remote.read(sp,256).hex(),
            'manager_words':list(struct.unpack('<32I',self.remote.read(0xc1811e50,128))),
            'observed_C1821EB8':int.from_bytes(self.remote.read(0xc1821eb8,4),'little'),
            'status_codes':list(status[:count]) if count<=68 else None}
        matches=[p for p in self.pending.get(pc,[]) if p['thread']==thread and p['sp']==sp]
        if matches:
            require(len(matches)==1,'Ambiguous manager return')
            call=matches[0];self.pending[pc].remove(call)
            row.update(label=call['label']+'-return',call_sequence=call['sequence'],
                elapsed_virtual_ns=row['virtual_time_ns']-call['virtual_time_ns'])
            self.record['returns'].append(row)
            if not self.pending[pc] and pc not in POINTS:self.disarm(pc)
        elif pc in MARKERS:
            row['label']=MARKERS[pc];self.record['stores'].append(row)
        elif pc in POINTS:
            row['label']=POINTS[pc];return_pc=pc+CALLS[pc] if pc in CALLS else r['lr']&~1
            row['return_anchor']=self.check_anchor(return_pc)
            self.pending.setdefault(return_pc,[]).append({'sequence':row['sequence'],'label':row['label'],
                'thread':thread,'sp':sp,'virtual_time_ns':row['virtual_time_ns']})
            self.arm(return_pc);self.record['calls'].append(row)
        else:self.record['outside_stops'].append(row)
        self.step(thread)
        row['after_original_step_registers']=self.registers()
        if pc==0x1029a906:
            target=r['r3']&~1;row['callback_target']=hex(target)
            require(row['after_original_step_registers']['pc']==target,'Original BLX did not enter its actual target')
            row['callback_target_anchor']=self.check_anchor(target)
        self.record['hits'].append(row)
        print('APP_TRANSITION',row['label'],hex(r['r0']),hex(r['r3']),row['virtual_time_ns'],flush=True)
        if self.record['stops']>=192:self.record['scope_limit_reached']=True;self.close('stop-budget')
        else:self.resume()

    def close(self,reason='cleanup'):
        if reason=='actual-post-half-index3':
            self.record.setdefault('first_post_half_index3_ns',self.record['post_half_index3_ns'])
            self.record['index_assignment_did_not_end_observation']=True
            return
        super().close(reason)
