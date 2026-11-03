"""Read-only C1.70 selector snapshots and retained-owner QMP timeout captures."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct

try:
    from .z62_paired_console import PairedSceneMixin, private_staging
    from .z62_qmp_transport import QmpClient
    from . import z62_host_timeout_capture as host_capture
except ImportError:
    from z62_paired_console import PairedSceneMixin, private_staging
    from z62_qmp_transport import QmpClient
    import z62_host_timeout_capture as host_capture

VERSION='2026.11.03-paired-diagnostic-r72'
RANGES={'scalar':(0xC1F7A628,2),'cache':(0xC1F7A740,16),'decoded':(0xC25D6FE4,1),
        'inhibit':(0xC1821EB8,1),'join':(0xC1868AE8,1),'processor':(0xC1864CD0,1),
        'groups':(0x20102600,4)}


def decode_selector(blocks):
    if (not isinstance(blocks,dict) or set(blocks)!=set(RANGES) or
        any(not isinstance(blocks[name],list) or len(blocks[name])!=count or
            any(type(v) is not int or not 0<=v<=0xffffffff for v in blocks[name])
            for name,(_,count) in RANGES.items())):
        raise ValueError('Incomplete or malformed selector read')
    scalar=blocks['scalar']; cache=struct.pack('<16I',*blocks['cache'])
    return {'scalar':{'current':scalar[0]&0xffff,'previous':scalar[0]>>16,'changed':scalar[1]},
        'cached':{'current':struct.unpack_from('<H',cache,6)[0],'previous':struct.unpack_from('<H',cache,58)[0]},
        'decoded_master':blocks['decoded'][0]>>16,'input_inhibit':blocks['inhibit'][0],
        'ready_join':blocks['join'][0],'processor_state_byte':(blocks['processor'][0]>>8)&255,
        'command_group_0':blocks['groups'],
        'original_observed_gate':blocks['inhibit'][0]==0 and blocks['join'][0]==3,
        'gate_scope':'prior bounded selector experiment; not whole-camera readiness'}


class ObservedQmp(QmpClient):
    def __init__(self,owner,port):
        self.owner=owner
        super().__init__(port)

    def command(self,name,arguments=None,**kwargs):
        try:
            return super().command(name,arguments,**kwargs)
        except TimeoutError as exc:
            try:
                self.owner._diagnostic_timeout(name,arguments,str(exc))
            except Exception as capture_error:
                self.owner._diagnostic_capture={'completed_capture':False,'failure':{
                    'type':type(capture_error).__name__,'message':str(capture_error)}}
            raise


class PairedDiagnosticMixin(PairedSceneMixin):
    diagnostic_profile={}

    def __init__(self,*args,**kwargs):
        self._diagnostic_timeout_events=[]
        self._diagnostic_capture_attempted=False
        self._diagnostic_capture=None
        super().__init__(*args,**kwargs)

    def _diagnostic_timeout(self,name,arguments,message):
        row={'command':name,'arguments':deepcopy(arguments),'message':message,'replayed':False}
        self._diagnostic_timeout_events.append(row)
        first=not self._diagnostic_capture_attempted
        self._diagnostic_capture_attempted=True  # any launch attempt invalidates functional qualification
        folder=self.work/'host-diagnostics'
        folder.mkdir(exist_ok=True)
        target=folder/('timeout-%04d.json'%len(self._diagnostic_timeout_events))
        with target.open('x',encoding='utf-8') as handle:
            json.dump(row,handle,indent=2)
        if not first:
            return
        try:
            process=self.process
            self._diagnostic_capture=host_capture.capture(process,process.pid,
                Path(self.diagnostic_profile['runtime_binary']),self.diagnostic_profile['binary_sha256'],
                folder/'first-timeout',gdb=Path(self.diagnostic_profile['gdb']),console=self.work/'console.txt')
        except Exception as exc:
            self._diagnostic_capture={'completed_capture':False,'failure':{
                'type':type(exc).__name__,'message':str(exc)}}
        with (folder/'first-timeout-result.json').open('x',encoding='utf-8') as handle:
            json.dump(self._diagnostic_capture,handle,indent=2)

    def paired_diagnostics(self):
        with self.io:
            self._ready()
            ticks,frequency=self._key_clock()
            blocks={name:self._words(address,count) for name,(address,count) in RANGES.items()}
            master=self._capture_input_target()
            row={'version':VERSION,'virtual_time_ns':ticks*1_000_000_000//frequency,
                'selector':decode_selector(blocks),'raw_words':blocks,
                'input_levels':self.qmp.command('qom-get',{'path':'/machine/peripheral/keys','property':'input-levels'}),
                'output':json.loads(self.qmp.command('qom-get',{'path':master,'property':'paired-output-lineage'})),
                'pipeline_mode':self._paired_state(),'atomic_cross_device_snapshot':False,
                'guest_memory_written':False,'guest_functions_called':False,'camera_accessed':False}
            # These reads describe two engines separately; they are not an atomic snapshot.
            for name in ('raw-stream-active','raw-stream-frames','paired-ingress-frames',
                         'paired-ingress-reason','video-isp-batches','video-isp-reason'):
                try:
                    row[name]=self.qmp.command('qom-get',{'path':master,'property':name})
                except RuntimeError as exc:
                    row[name]={'unavailable':str(exc)}
            row['timeout_events']=deepcopy(self._diagnostic_timeout_events)
            row['host_capture_attempted']=self._diagnostic_capture_attempted
            row['host_capture']=deepcopy(self._diagnostic_capture)
            row['functional_acceptance_eligible']=not self._diagnostic_capture_attempted
            row['monitor']=self.qmp.diagnostics()
            return row


def apply_console(source,profile):
    from reference_updates import replace_once
    source=private_staging(source); target=source/'tools/z62_console.py'
    content=replace_once(target.read_text(encoding='utf-8'),
        'class Z62Machine(PairedSceneMixin, ModeInputMixin, shared.Machine):',
        'from tools.z62_paired_diagnostic_console import PairedDiagnosticMixin, ObservedQmp\n\n\n'
        'class Z62Machine(PairedDiagnosticMixin, ModeInputMixin, shared.Machine):\n'
        '    diagnostic_profile = '+repr(profile))
    content=replace_once(content,'        self.qmp = shared.QmpClient(qmp_port)',
                        '        self.qmp = ObservedQmp(self, qmp_port)')
    content=replace_once(content,'        for device in devices:',
        '        command[0] = self.diagnostic_profile["runtime_binary"]\n        for device in devices:')
    content=replace_once(content,"                elif self.path == '/software/status':",
        "                elif self.path == '/paired/diagnostics':\n"
        "                    self.send(200, json.dumps(machine.paired_diagnostics(), ensure_ascii=False).encode())\n"
        "                elif self.path == '/software/status':")
    target.write_text(content,encoding='utf-8',newline='\n')
    for name in ('z62_paired_diagnostic_console.py','z62_host_timeout_capture.py'):
        (source/'tools'/name).write_bytes(Path(__file__).with_name(name).read_bytes())
