"""r110 original request comparison and bounded parameter-19 qualification."""
import struct
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
import z62_cw_app_transition_observer as parent
from record_z62_action_evidence import require

BASE_CONTRACT=parent.contract
FUNCTIONS={0x10542b48:'applv-transition',0x1054297e:'transition-request',0x105b3358:'observed-flag-setter'}
EXTRA_CALLS={0x10542992:'request-mode-conversion',0x10542a04:'changed-mode-query',
    0x10542a46:'changed-mode-operation',0x10542a7c:'changed-mode-dispatch',0x10540f3c:'parameter-19-query'}
EXTRA_MARKERS={0x10634902:'conversion-compare-old-new',0x1063490a:'conversion-stability-branch',
    0x1063490e:'conversion-changed-assignment',0x10634922:'conversion-result',
    0x105429e2:'request-special-zero',0x10542a02:'request-changed-gate',0x10542aa8:'request-result',
    0x10540f68:'parameter-19-branch',0x10541366:'parameter-clear-call-marker'}
POINTS={**parent.POINTS,**FUNCTIONS,**EXTRA_CALLS,**EXTRA_MARKERS}
CALLS={**parent.CALLS,**{pc:4 for pc in EXTRA_CALLS}}
MARKERS={**parent.MARKERS,**EXTRA_MARKERS}
MODE_STATE=0xc181b47c


def contract(image):
    anchors=BASE_CONTRACT(image);decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
    for pc in EXTRA_CALLS:
        insn=next(iter(decoder.disasm(image[pc-parent.BASE:pc-parent.BASE+4],pc,count=1)),None)
        require(insn and insn.mnemonic=='bl' and insn.size==4,'Original qualification BL differs')
    for pc,(mnemonic,operands) in {0x10634902:('cmp','r8, r5'),0x1063490a:('beq','#0x10634914'),
            0x10634922:('mov','r0, sb'),0x10542a02:('cbz','r4, #0x10542a6c'),
            0x10542aa8:('mov','r0, r4'),0x10540f68:('beq','#0x1054104e')}.items():
        insn=next(decoder.disasm(image[pc-parent.BASE:pc-parent.BASE+4],pc,count=1))
        require((insn.mnemonic,insn.op_str)==(mnemonic,operands),'Original qualification marker differs')
    require(struct.unpack_from('<I',image,0x10634a44-parent.BASE)[0]==MODE_STATE,'Original mode-state literal differs')
    return anchors


class RequestQualificationObserver(parent.AppTransitionObserver):
    def __init__(self,binary):
        super().__init__(binary);self.snapshot_sequences=set();self.parameter_branch_samples=0
        self.record.update(version='2026.11.04-request-qualification-r110',parameter_query_sample_limit=4,
            scope='Original request comparisons and first four parameter-19 branches; setter/clear marker remain active')

    def registers(self):
        data=self.remote.regs();names=('pc','lr','sp',*(f'r{i}' for i in range(13)),'cpsr')
        return {name:self.remote.get(data,name) if name in self.remote.offsets else self.remote.read_register(name) for name in names}

    def resume(self):
        if self.record['hits']:
            row=self.record['hits'][-1];sequence=row['sequence']
            if sequence not in self.snapshot_sequences:
                row['mode_state_c181b47c_after_step_hex']=self.remote.read(MODE_STATE,64).hex()
                row['mode_snapshot_after_original_single_step']=True
                if row['label'].startswith('parameter-19-query'):
                    source=row
                    if row.get('call_sequence'):
                        source=next(c for c in self.record['calls'] if c['sequence']==row['call_sequence'])
                    pointer=source['registers']['r1']
                    require(0xc0000000<=pointer<=0xdffffff8 and not pointer&3,'Parameter output pointer outside original RAM')
                    row['parameter_output_pointer']=hex(pointer)
                    row['parameter_output_after_step_hex']=self.remote.read(pointer,8).hex()
                if row['label']=='parameter-19-branch':
                    self.parameter_branch_samples+=1
                    if self.parameter_branch_samples==4:
                        self.disarm(0x10540f3c);self.disarm(0x10540f68)
                        self.record['parameter_sampling_closed_after_branch']=sequence
                        self.record['setter_and_clear_call_still_armed']=0x105b3358 in self.active and 0x10541366 in self.active
                self.snapshot_sequences.add(sequence)
        super().resume()
