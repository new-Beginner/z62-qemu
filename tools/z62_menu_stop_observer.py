"""r111 real stop calls, attached before the first external MENU request."""
import json
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
import z62_cw_app_transition_observer as parent
from z62_kernel_event_layout import resolve
from z62_stop_wait_observer import sensor_state
from record_z62_action_evidence import require

BASE_CONTRACT=parent.contract
STOP_FUNCTIONS={0x102dbb9c:'capture-stop',0x102dd9c8:'mode0-stop',0x102dd964:'mode2-stop',
    0x102fb6e6:'mode0-substop-a',0x102fb640:'mode0-substop-b',0x102fcbae:'mode0-substop-c',
    0x102fb41c:'cleanup-a',0x102fb62a:'cleanup-b',0x102fb702:'cleanup-c',0x102fca50:'cleanup-d',
    0x1054008e:'applv-object-method-1054008e'}
POINTS={**parent.POINTS,**STOP_FUNCTIONS}


def contract(image):
    anchors=BASE_CONTRACT(image);decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
    for pc in STOP_FUNCTIONS:
        require(next(iter(decoder.disasm(image[pc-parent.BASE:pc-parent.BASE+4],pc,count=1)),None) is not None,
            'Stop entry does not decode')
    return anchors


class MenuStopObserver(parent.AppTransitionObserver):
    last_created=None
    def __init__(self,binary):
        super().__init__(binary);type(self).last_created=self;self.snapshot_sequences=set();self.stop_layout=None
        self.record.update(version='2026.11.04-menu-stop-r111',
            scope='Initial preview before first external MENU through bounded end, original stop/control calls')

    def attach(self,machine,layout):
        self.stop_layout=dict(layout,object=0xc18a7634)
        super().attach(machine,layout)

    def resume(self):
        if self.record['hits']:
            row=self.record['hits'][-1]
            if row['sequence'] not in self.snapshot_sequences:
                row['stop_context_after_original_single_step']=True
                row['sensor']=sensor_state(self.machine)
                row['original_stop_event']=resolve(self.remote,self.stop_layout)
                row['sensor_mode_status_mask']=self.machine._words(0x20065504,3)
                row['input_last_control_writes']=self.machine._words(0x20068000,7)
                for key,prop in (('CW','capturework-status'),('readout','input-readout-status'),
                        ('finite_input','input-readout-statistics-status')):
                    row[key]=json.loads(self.machine.qmp.command('qom-get',{'path':'/machine/master-input','property':prop}))
                self.snapshot_sequences.add(row['sequence'])
        super().resume()
