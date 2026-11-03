"""The opt-in console must preserve unrelated inputs and reject flag shadowing."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))


class PairedConsoleTests(unittest.TestCase):
    def api(self):
        try:
            import z62_paired_console as api
        except ImportError as exc:
            self.fail('Independent paired console adapter is missing: '+str(exc))
        return api

    def test_selector_preserves_other_held_inputs(self):
        api=self.api(); before=0xfffff7
        video=api.selector_levels(before,'video')
        self.assertEqual(video&~1,before&~1)
        self.assertEqual(video&1,0)
        self.assertEqual(api.selector_levels(video,'photo'),before)

    def test_selector_rejects_malformed_inputs(self):
        api=self.api()
        for before,mode in ((True,'video'),(-1,'photo'),(0x1000000,'photo'),(1,'P')):
            with self.assertRaises(ValueError):
                api.selector_levels(before,mode)

    def test_profile_adds_missing_flags_without_duplicates(self):
        api=self.api(); original=['qemu','-global','x.a=on','-nographic']
        actual=api.merge_globals(original,['-global','x.a=on','-global','x.b=on'])
        self.assertEqual(actual.count('x.a=on'),1)
        self.assertIn('x.b=on',actual)
        self.assertIn('-nographic',actual)
        self.assertEqual(original,['qemu','-global','x.a=on','-nographic'])

    def test_profile_cannot_shadow_an_explicit_disabled_device(self):
        api=self.api()
        with self.assertRaisesRegex(ValueError,'conflicting global'):
            api.merge_globals(['qemu','-global','x.a=off'],['-global','x.a=on'])

    def test_parameter_fixture_is_private_and_session_is_updated(self):
        api=self.api()
        with tempfile.TemporaryDirectory(prefix='z62-reference-') as directory:
            work=Path(directory); (work/'source').mkdir(); (work/'parameters').mkdir()
            old=bytes(0xDFFFC)+b'ENDM'; target=work/'parameters/group23.bin'; target.write_bytes(old)
            fixture=work/'supplied.bin'; fixture.write_bytes(b'x'*0xDFFFC+b'ENDM')
            sha=lambda data:hashlib.sha256(data).hexdigest()
            profile={'binary_sha256':'a'*64,'group23':str(fixture),'group23_sha256':sha(fixture.read_bytes()),'version':'test'}
            record={'profile':'z62','work':str(work),'qemu_sha256':'a'*64,
                    'parameters':{'groups':{'group23.bin':{'zero_body':True,'sha256':sha(old)}}}}
            (work/'session.json').write_text(json.dumps(record),encoding='utf-8')
            api.prepare_parameters(work,profile)
            result=json.loads((work/'session.json').read_text(encoding='utf-8'))
            self.assertEqual(target.read_bytes(),fixture.read_bytes())
            self.assertFalse(result['parameters']['groups']['group23.bin']['zero_body'])
            self.assertEqual(result['paired_profile'],profile)
            api.prepare_parameters(work,profile)  # same session can restart without rewriting the fixture
            record['clean_exit']=True  # the older host writes its original in-memory record on exit
            (work/'session.json').write_text(json.dumps(record),encoding='utf-8')
            api.finalize_parameters(work,profile)
            result=json.loads((work/'session.json').read_text(encoding='utf-8'))
            self.assertTrue(result['clean_exit'])
            self.assertEqual(result['paired_profile'],profile)
            self.assertFalse(result['parameters']['groups']['group23.bin']['zero_body'])
            target.write_bytes(old)
            with self.assertRaisesRegex(ValueError,'changed'):
                api.prepare_parameters(work,profile)

    def test_generator_rejects_non_staging_source(self):
        api=self.api()
        with tempfile.TemporaryDirectory(prefix='unrelated-') as directory:
            with self.assertRaises(ValueError):
                api.apply_console(Path(directory)/'source',{})

    def test_generator_composes_with_all_previous_media_layers(self):
        import shutil
        import subprocess
        import z62_shutter_input_v2 as shutter
        import z62_capture_input as capture
        import z62_body_controls as body
        import z62_encoder_queue as encoder
        import z62_encoder_labels as labels
        import z62_extra_console as extra
        import z62_mode_console as mode
        import z62_software_console as software
        import z62_native_scene_console as native
        import z62_media_scene as media
        import z62_video_console as video
        import z62_async_video_console as asynchronous
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='z62-reference-') as directory:
            source=Path(directory)/'source'; source.mkdir()
            for name in ('tools/z62_console.py','web-z62/index.html','web-z62/console.js','web-z62/style.css'):
                target=source/name; target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(root/'third_party/z62-qemu'/name,target)
            for adapter in (shutter,capture,body,encoder,labels,extra,mode):
                adapter.apply_console(source)
            config={'card':None,'scene':None,'width':160,'height':104}
            software.apply_console(source,config); native.apply_console(source,config)
            media.apply_console(source,{'photo_format':'jpeg-nef'})
            video.apply_console(source); asynchronous.apply_console(source)
            self.api().apply_console(source,{'version':'test','globals':[]})
            content=(source/'tools/z62_console.py').read_text(encoding='utf-8')
            compile(content,'paired-generated','exec')
            self.assertIn('class Z62Machine(PairedSceneMixin,',content)
            self.assertIn('prepare_parameters(Path(__file__)',content)
            self.assertIn('self._paired_validate_key_locked(pin, level)',content)
            script=source/'web-z62/console.js'
            if shutil.which('node'):
                subprocess.run(['node','--check',str(script)],check=True,capture_output=True)
            self.assertIn('pipeline-info',(source/'web-z62/index.html').read_text(encoding='utf-8'))

    def test_status_never_reacquires_the_nonrecursive_guest_lock(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        api=self.api()
        class CheckedLock:
            held=False
            def __enter__(self):
                if self.held:
                    raise AssertionError('nonrecursive guest lock acquired twice')
                self.held=True
            def __exit__(self,*args):
                self.held=False
        instance=object.__new__(api.PairedSceneMixin)
        instance.io=CheckedLock()
        instance._software_locked=lambda:(SimpleNamespace(status=lambda ns:{'capabilities':{}}),123)
        instance.native_scene_status=lambda:{'last_consumed':None}
        instance._paired_state=lambda:{'ready':False}
        def inherited_status(self):
            with self.io:
                return {'capabilities':{}}
        with patch.object(api.AsyncVideoSceneMixin,'software_status',inherited_status):
            self.assertFalse(instance.software_status()['pipeline_mode']['ready'])


if __name__=='__main__':
    unittest.main()
