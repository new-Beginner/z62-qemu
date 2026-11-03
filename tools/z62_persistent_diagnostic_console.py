"""Keep fault evidence outside the VM directory deleted by normal cleanup."""
from copy import deepcopy
import json
from pathlib import Path

try:
    from .z62_paired_diagnostic_console import PairedDiagnosticMixin,host_capture
except ImportError:
    from z62_paired_diagnostic_console import PairedDiagnosticMixin,host_capture

VERSION='2026.11.03-persistent-diagnostic-r74'


class PersistentDiagnosticMixin(PairedDiagnosticMixin):
    persistent_diagnostic_profile={}

    def _persistent_folder(self):
        profile=self.persistent_diagnostic_profile
        workspace=Path(profile['workspace']).absolute().resolve()
        root=Path(profile['output_root']).absolute()
        if not root.resolve().is_relative_to(workspace):
            raise ValueError('Fault evidence must stay in the workspace')
        folder=root/self.work.name
        folder.mkdir(parents=True,exist_ok=True)
        return folder

    def _diagnostic_timeout(self,name,arguments,message):
        row={'command':name,'arguments':deepcopy(arguments),'message':message,'replayed':False,
             'vm_directory':str(self.work),'evidence_version':VERSION}
        self._diagnostic_timeout_events.append(row)
        first=not self._diagnostic_capture_attempted
        self._diagnostic_capture_attempted=True
        folder=self._persistent_folder()
        with (folder/('timeout-%04d.json'%len(self._diagnostic_timeout_events))).open('x',encoding='utf-8') as handle:
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
        row=super().paired_diagnostics()
        row['persistent_diagnostic_profile']=deepcopy(self.persistent_diagnostic_profile)
        with self.io:
            self._ready()
            target=self._capture_input_target()
            # These are the actual r69 property names; r72's two unavailable
            # video-isp-* observations remain recorded separately in row.
            for name in ('video-batches','video-reason'):
                row[name]=self.qmp.command('qom-get',{'path':target,'property':name})
        return row


def apply_console(source,profile):
    from reference_updates import replace_once
    source=Path(source); target=source/'tools/z62_console.py'
    content=replace_once(target.read_text(encoding='utf-8'),
        'class Z62Machine(PairedDiagnosticMixin, ModeInputMixin, shared.Machine):',
        'from tools.z62_persistent_diagnostic_console import PersistentDiagnosticMixin\n\n\n'
        'class Z62Machine(PersistentDiagnosticMixin, ModeInputMixin, shared.Machine):\n'
        '    persistent_diagnostic_profile = '+repr(profile))
    target.write_text(content,encoding='utf-8',newline='\n')
    (source/'tools/z62_persistent_diagnostic_console.py').write_bytes(Path(__file__).read_bytes())
