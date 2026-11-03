"""Read original C1.70 capture queue and flow without consuming their work."""
from collections import Counter
from pathlib import Path

try:
    from .z62_persistent_diagnostic_console import PersistentDiagnosticMixin
except ImportError:
    from z62_persistent_diagnostic_console import PersistentDiagnosticMixin

VERSION='2026.11.03-action-queue-r76'
QUEUE=0xC23D9F14
CAPTURE=0xC23E2948


def word_list(values,count):
    if not isinstance(values,list) or len(values)!=count or any(type(v) is not int or not 0<=v<=0xffffffff for v in values):
        raise ValueError('Incomplete or malformed original RAM snapshot')


def queue_layout(header):
    word_list(header,6)
    base,stride,capacity,count,head,mutex=header; stride&=255
    if (stride!=92 or not 1<=capacity<=256 or not 0<=count<=capacity or not 0<=head<capacity or
            not 0xC0000000<=base<=0xE0000000-stride*capacity):
        raise ValueError('Original bounded queue layout differs')
    return {'base':base,'stride':stride,'capacity':capacity,'count':count,'head':head,'mutex':mutex}


def decode_queue(header,storage):
    row=queue_layout(header)
    word_list(storage,row['capacity']*23)
    tasks=[hex(storage[((row['head']+index)%row['capacity'])*23]) for index in range(row['count'])]
    return {**row,'work_ids_in_order':tasks,'work_id_counts':dict(Counter(tasks)),
            'atomic_snapshot_proven':False,'queue_modified_by_reader':False}


def decode_capture(words):
    word_list(words,40)
    return {'active_word':words[0],'flow_word':words[1],'stage':hex(words[2]),'callback':hex(words[3]),
        'callback_result_word':words[4],'outstanding':hex(words[5]),'elapsed':words[6],'deadline':words[7],
        'raw_words':words,'capture_complete_claimed':False}


class ActionQueueMixin(PersistentDiagnosticMixin):
    def paired_diagnostics(self):
        row=super().paired_diagnostics()
        with self.io:
            self._ready()
            before=self._words(QUEUE,6)
            try:
                layout=queue_layout(before)
                storage=self._words(layout['base'],layout['capacity']*23)
                after=self._words(QUEUE,6)
                row['capture_work_queue']={**decode_queue(before,storage),'known_layout':True,
                    'header_before':before,'header_after':after,'header_stable_during_read':before==after}
            except ValueError as exc:
                row['capture_work_queue']={'known_layout':False,'header_before':before,'error':str(exc)}
            row['capture_flow']=decode_capture(self._words(CAPTURE,40))
            application=self._words(0xC181D330,32)
            row['applv_ram']={'base':'0xc181d330','words':application,
                             'action_word_at_c181d388':application[22]}
            ticks,frequency=self._key_clock()
            row['action_snapshot_end_ns']=ticks*1_000_000_000//frequency
        row['action_queue_version']=VERSION
        return row


def apply_console(source):
    from reference_updates import replace_once
    source=Path(source); target=source/'tools/z62_console.py'
    content=replace_once(target.read_text(encoding='utf-8'),
        'class Z62Machine(PersistentDiagnosticMixin, ModeInputMixin, shared.Machine):',
        'from tools.z62_action_queue_console import ActionQueueMixin\n\n\n'
        'class Z62Machine(ActionQueueMixin, ModeInputMixin, shared.Machine):')
    target.write_text(content,encoding='utf-8',newline='\n')
    (source/'tools/z62_action_queue_console.py').write_bytes(Path(__file__).read_bytes())
