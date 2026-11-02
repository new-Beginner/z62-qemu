"""r10 host input experiment on the unchanged, identity-verified r9 QEMU binary."""
import sys
import run_z62_preview as preview
import z62_shutter_input_v2 as shutter
import z62_qmp_transport as monitor
from reference_updates import replace_once


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--version' in argv:
        print(shutter.identity()['version'])
        return
    original = preview.apply_status
    def apply(source):
        original(source)
        shutter.apply_console(source)
        monitor.apply_console(source)
        path = source / 'tools/z62_console.py'
        content = replace_once(path.read_text(encoding='utf-8'),
            '            state.update(preview_status(self))',
            '            state.update(preview_status(self))\n'
            + '            state["input_adapter"] = ' + repr(shutter.identity()) + '\n'
            + '            state["monitor_transport"] = self.qmp.diagnostics()')
        path.write_text(content, encoding='utf-8', newline='\n')
    preview.apply_status = apply
    if '--port' not in argv and not any(a.startswith('--port=') for a in argv):
        argv += ['--port', '8680']
    try:
        preview.main(argv)
    finally:
        preview.apply_status = original


if __name__ == '__main__':
    main()
