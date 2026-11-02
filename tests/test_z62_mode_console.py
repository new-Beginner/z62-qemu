"""Mechanical lock, persistent external voltage and non-forged mode reporting."""
from pathlib import Path
import sys
import threading
from unittest.mock import patch
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import z62_mode_console as mode
import z62_mode_selector as selector


class ModeConsoleTests(unittest.TestCase):
    def setUp(self):
        self.machine=mode.ModeInputMixin()
        m=self.machine
        m.io=threading.Lock()
        m._ready=lambda:None
        m._mode_lock_pressed=False
        m.requested_keys=set()
        m._mode_adc_path='/adc'
        self.sample=0
        self.writes=[]
        def command(name,args):
            self.assertEqual(args['path'],'/adc')
            self.assertEqual(args['property'],'input-channel2')
            if name=='qom-get': return self.sample
            self.assertEqual(name,'qom-set')
            self.sample=args['value']
            self.writes.append(self.sample)
        from types import SimpleNamespace
        m.qmp=SimpleNamespace(command=command)

    def test_locked_dial_cannot_change_voltage(self):
        with self.assertRaises(ValueError): self.machine.set_mode('M')
        self.assertEqual(self.sample,0)
        self.assertFalse(self.writes)

    def test_each_detent_uses_the_recovered_ladder(self):
        self.machine.set_mode_lock(True)
        for name,code in mode.MODES.items():
            self.machine.set_mode(name)
            self.assertEqual(self.sample,selector.SAMPLES[code])
            state=self.machine._mode_status()
            self.assertEqual((state['position'],state['code']),(name,code))
            self.assertFalse(state['effective_firmware_mode_known'])
        self.assertIn(mode.LOCK_LEASE,self.machine.requested_keys)

    def test_release_relocks_without_moving_the_physical_dial(self):
        self.machine.set_mode_lock(True)
        self.machine.set_mode('U2')
        with patch.object(mode.ExtraInputMixin,'_release') as release:
            self.machine._release()
            release.assert_called_once()
        self.assertEqual(self.sample,selector.SAMPLES[5])
        self.assertFalse(self.machine._mode_lock_pressed)
        self.assertNotIn(mode.LOCK_LEASE,self.machine.requested_keys)

    def test_invalid_inputs_have_no_effect(self):
        for value in (1,0,'true',None):
            with self.assertRaises(ValueError): self.machine.set_mode_lock(value)
        self.machine.set_mode_lock(True)
        for value in ('Bulb','manual',3,None,[]):
            with self.assertRaises(ValueError): self.machine.set_mode(value)
        self.assertFalse(self.writes)

    def test_unknown_adc_is_not_reported_as_mode_p(self):
        self.sample=4096
        self.assertFalse(self.machine._mode_status()['known'])
        self.assertNotIn('position',self.machine._mode_status())

    def test_all_adc_samples_have_exactly_one_band(self):
        for value in range(4096):
            self.assertEqual(sum(low<=value<high for low,high,_ in selector.BANDS),1)

    def test_complete_staging_keeps_all_input_layers_and_valid_python(self):
        import ast
        import shutil
        import tempfile
        import z62_shutter_input_v2 as shutter
        import z62_capture_input as capture
        import z62_body_controls as body
        import z62_encoder_queue as encoder
        import z62_encoder_labels as labels
        import z62_extra_console as extra
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            stage=Path(folder)
            for name in ('tools/z62_console.py','web-z62/index.html','web-z62/console.js','web-z62/style.css'):
                target=stage/name
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(root/'third_party/z62-qemu'/name,target)
            for adapter in (shutter,capture,body,encoder,labels,extra,mode):
                adapter.apply_console(stage)
            text=(stage/'tools/z62_console.py').read_text(encoding='utf-8')
            ast.parse(text)
            self.assertIn('class Z62Machine(ModeInputMixin, shared.Machine)',text)
            html=(stage/'web-z62/index.html').read_text(encoding='utf-8')
            self.assertEqual(html.count('data-mode='),8)
            self.assertEqual(html.count('data-joystick='),9)
            for pin in (24,25,26,27,28,29):
                self.assertEqual(html.count(f'data-pin="{pin}"'),1)

    def test_candidate_staging_after_mode_adapter_keeps_candidate_identity(self):
        import ast
        import shutil
        import tempfile
        import reference_updates
        import run_z62_transaction as transaction
        import z62_candidate_firmware as candidate
        import z62_shutter_input_v2 as shutter
        import z62_capture_input as capture
        import z62_body_controls as body
        import z62_encoder_queue as encoder
        import z62_encoder_labels as labels
        import z62_extra_console as extra
        root=Path(__file__).resolve().parents[1]
        selected=candidate.load_candidate(package=root/candidate.SPEC['input'])
        with tempfile.TemporaryDirectory() as folder:
            stage=Path(folder)
            for name in ('tools/z62_console.py','tools/z62_probe.py','tools/web_console.py',
                         'web-z62/index.html','web-z62/console.js','web-z62/style.css'):
                target=stage/name
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(root/'third_party/z62-qemu'/name,target)
            reference_updates.apply_console(stage)
            transaction.apply_console(stage)
            for adapter in (shutter,capture,body,encoder,labels,extra,mode):
                adapter.apply_console(stage)
            candidate.apply_console(stage,selected)
            html=(stage/'web-z62/index.html').read_text(encoding='utf-8')
            self.assertIn('<h1>测试候选固件</h1>',html)
            self.assertIn('固件健康状态为未知',html)
            self.assertEqual(html.count('data-mode='),8)
            text=(stage/'tools/z62_console.py').read_text(encoding='utf-8')
            ast.parse(text)
            self.assertIn('return candidate_status(self, self._candidate_legacy_status, CANDIDATE_INFO)',text)


if __name__=='__main__': unittest.main()
