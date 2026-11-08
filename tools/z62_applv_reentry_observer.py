"""r109 original APPLV entry/parameter predicates, preserving manager positive controls."""
import struct
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
import z62_cw_app_transition_observer as parent
from record_z62_action_evidence import require

BASE_CONTRACT=parent.contract
EXTRA_FUNCTIONS={0x10542b48:'applv-transition-10542b48',0x10540ed2:'applv-parameter-10540ed2',
    0x105b3358:'observed-flag-setter',0x1054009e:'applv-function-1054009e',
    0x1054297e:'transition-request-1054297e',0x1054564e:'transition-selector-1054564e'}
EXTRA_CALLS={0x1054302a:'transition-status-a',0x10543030:'transition-status-b',0x10543036:'transition-status-c',
    0x105430e4:'transition-flag-2a',0x105430ea:'transition-condition-a',
    0x105430f0:'transition-condition-b',0x105430f6:'transition-condition-c'}
POINTS={**parent.POINTS,**EXTRA_FUNCTIONS,**EXTRA_CALLS}
CALLS={**parent.CALLS,**{pc:4 for pc in EXTRA_CALLS}}


def contract(image):
    anchors=BASE_CONTRACT(image);decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
    for pc in EXTRA_CALLS:
        insn=next(iter(decoder.disasm(image[pc-parent.BASE:pc-parent.BASE+4],pc,count=1)),None)
        require(insn and insn.mnemonic=='bl' and insn.size==4,'Original APPLV predicate call differs')
    return anchors


class ApplvReentryObserver(parent.AppTransitionObserver):
    def __init__(self,binary):
        super().__init__(binary);self.snapshot_sequences=set()
        self.record.update(version='2026.11.04-APPLV-reentry-r109',
            scope='Original APPLV transition/parameter/flag calls after actual MENU through bounded end')

    def resume(self):
        if self.record['hits']:
            row=self.record['hits'][-1];sequence=row['sequence']
            if sequence not in self.snapshot_sequences:
                # Parent is stopped after one unchanged original instruction.
                # This is neither a before-store snapshot nor a global atomic state.
                row['snapshot_after_original_single_step']=True
                row['applv_object_c181d9e4_hex']=self.remote.read(0xc181d9e4,128).hex()
                row['applv_flags_c181d9a0_hex']=self.remote.read(0xc181d9a0,64).hex()
                row['observed_flag_after_step']=int.from_bytes(self.remote.read(0xc1821eb8,4),'little')
                pointer=row['registers']['r0']
                if 0xc0000000<=pointer<=0xdfffff80 and not pointer&3:
                    row['argument_object_hex']=self.remote.read(pointer,128).hex()
                    row['argument_object_pointer']=hex(pointer)
                self.snapshot_sequences.add(sequence)
        super().resume()
