"""Independent interactive profile using committed C ISP frames and mode input."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile

try:
    from .z62_async_video_console import AsyncVideoSceneMixin
    from .z62_paired_camera import PipelineMode, output_record, owned_frame, committed_frame
    from .z62_software_camera import CameraError, fields
except ImportError:
    from z62_async_video_console import AsyncVideoSceneMixin
    from z62_paired_camera import PipelineMode, output_record, owned_frame, committed_frame
    from z62_software_camera import CameraError, fields

VERSION='2026.11.03-paired-console-r71'
SELECTOR_PATH='/machine/peripheral/keys'


def selector_levels(before,mode):
    if type(before) is not int or not 0<=before<=0xffffff or mode not in ('photo','video'):
        raise CameraError('invalid_pipeline_selector')
    return (before&~1)|int(mode=='photo')


def merge_globals(command,desired):
    required={}
    if len(desired)%2:
        raise ValueError('Malformed profile globals')
    for i in range(0,len(desired),2):
        if desired[i]!='-global' or '=' not in desired[i+1]:
            raise ValueError('Malformed profile global')
        key,value=desired[i+1].split('=',1)
        if key in required and required[key]!=value:
            raise ValueError('conflicting global in profile')
        required[key]=value
    result=[]; seen=set(); i=0
    while i<len(command):
        if command[i]=='-global':
            if i+1>=len(command) or '=' not in command[i+1]:
                raise ValueError('Malformed existing global')
            key,value=command[i+1].split('=',1)
            if key in required:
                if required[key]!=value:
                    raise ValueError('conflicting global: '+key)
                if key in seen:
                    i+=2; continue
                seen.add(key)
            result.extend(command[i:i+2]); i+=2
        else:
            result.append(command[i]); i+=1
    for key,value in required.items():
        if key not in seen:
            result.extend(('-global',key+'='+value))
    return result


def private_staging(source):
    source=Path(source).absolute(); work=source.parent
    if (source.name!='source' or not work.name.startswith('z62-reference-') or
            work.parent.resolve()!=Path(tempfile.gettempdir()).resolve()):
        raise ValueError('Paired profile requires a fresh private staging directory')
    for part in (source,*source.parents):
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
            raise ValueError('Linked staging directory is protected')
    if not source.is_dir():
        raise ValueError('Missing staged source')
    return source


def prepare_parameters(work,profile):
    """Replace only this new session's explicit synthetic NOR23 before VM start."""
    work=private_staging(Path(work)/'source').parent
    session=work/'session.json'; record=json.loads(session.read_text(encoding='utf-8'))
    if (record.get('profile')!='z62' or Path(record['work']).resolve()!=work.resolve() or
            record.get('qemu_sha256')!=profile['binary_sha256']):
        raise ValueError('Paired session identity differs')
    target=work/'parameters/group23.bin'
    for path in (session,target,target.parent,Path(profile['group23'])):
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            raise ValueError('Linked parameter path is protected')
    data=Path(profile['group23']).read_bytes()
    if len(data)!=0xE0000 or data[-4:]!=b'ENDM' or hashlib.sha256(data).hexdigest()!=profile['group23_sha256']:
        raise ValueError('Supplied group23 fixture changed')
    if record.get('paired_profile') is not None:
        if record['paired_profile']!=profile or target.read_bytes()!=data:
            raise ValueError('Prepared paired parameters changed')
        return
    previous=bytes(0xDFFFC)+b'ENDM'
    group=record['parameters']['groups']['group23.bin']
    if group.get('zero_body') is not True or group['sha256']!=hashlib.sha256(previous).hexdigest() or target.read_bytes()!=previous:
        raise ValueError('Only the freshly staged zero-body fixture may be replaced')
    target.write_bytes(data)
    group.update(size=len(data),sha256=profile['group23_sha256'],zero_body=False,
                 factory_calibration=False,origin='explicit r68 synthetic experiment fixture')
    record['paired_profile']=deepcopy(profile)
    session.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')


def finalize_parameters(work,profile):
    """Preserve actual fixture metadata after the ancestor launcher saves its final record."""
    work=private_staging(Path(work)/'source').parent
    session=work/'session.json'; target=work/'parameters/group23.bin'
    if not target.exists():
        return  # startup failed before this profile prepared parameters
    for path in (session,target,target.parent):
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            raise ValueError('Linked final session path is protected')
    data=target.read_bytes()
    if hashlib.sha256(data).hexdigest()!=profile['group23_sha256']:
        if data==bytes(0xDFFFC)+b'ENDM':
            return
        raise ValueError('Final group23 fixture changed')
    record=json.loads(session.read_text(encoding='utf-8'))
    if (record.get('profile')!='z62' or Path(record['work']).resolve()!=work.resolve() or
            record.get('qemu_sha256')!=profile['binary_sha256'] or
            record.get('paired_profile') not in (None,profile)):
        raise ValueError('Final paired session identity differs')
    group=record['parameters']['groups']['group23.bin']
    group.update(size=len(data),sha256=profile['group23_sha256'],zero_body=False,
                 factory_calibration=False,origin='explicit r68 synthetic experiment fixture')
    record['paired_profile']=deepcopy(profile)
    session.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')


class PairedSceneMixin(AsyncVideoSceneMixin):
    paired_profile={}

    def __init__(self,*args,**kwargs):
        self._paired_epoch=None
        self._paired_mode=PipelineMode()
        self._paired_output=None
        self._paired_polled_frame=None
        self._paired_error=None
        self._paired_selector_receipt=None
        super().__init__(*args,**kwargs)

    def _committed_frame(self,now_ns):
        if self._paired_output is None or not self._paired_mode.ready:
            raise CameraError('committed_output_unavailable')
        return committed_frame(self._scene_exchange,self._paired_output,now_ns,
                               self._scene_revision,self._software.mode)

    def _scene_publish_locked(self,camera,now_ns,force=False):
        frame_id=now_ns*30//1_000_000_000
        if not camera.powered or (not force and self._scene_published_revision==self._scene_revision and
                                  self._scene_published_frame==frame_id):
            return
        frame=camera.frame(now_ns)
        frame.metadata.update(scene_revision=self._scene_revision,pipeline_mode=camera.mode)
        if self._scene_exchange.publish(frame):
            self._scene_published_revision,self._scene_published_frame=self._scene_revision,frame_id

    def _software_locked(self):
        camera,now_ns=super()._software_locked()
        if self._paired_epoch!=camera.clock_epoch:
            self._paired_epoch=camera.clock_epoch
            self._paired_mode=PipelineMode(max_age_ns=self._scene_exchange.max_age_ns)
            self._paired_output=None; self._paired_polled_frame=None
            self._paired_error=None; self._paired_selector_receipt=None
        camera.native_frame_provider=self._committed_frame
        frame_id=now_ns*30//1_000_000_000
        if frame_id!=self._paired_polled_frame:
            self._paired_polled_frame=frame_id
            try:
                path=self._capture_input_target()
                value=self.qmp.command('qom-get',{'path':path,'property':'paired-output-lineage'})
                row=output_record(value)
                self._paired_output=row
                try:
                    metadata=owned_frame(self._scene_exchange,row).metadata
                except CameraError:
                    metadata=None
                result=self._paired_mode.observe(row,metadata,camera.mode,self._scene_revision,now_ns)
                if result['apply_mode'] is not None:
                    camera.event('mode',{'mode':result['apply_mode']},now_ns)
                    self._scene_revision+=1
                    self._paired_mode.applied(self._scene_revision,row['commits'])
                    self._scene_publish_locked(camera,now_ns,force=True)
                self._paired_error=None
            except (OSError,ValueError,RuntimeError) as exc:
                self._paired_output=None; self._paired_mode.ready=False
                self._paired_mode.phase='timed-out' if (self._paired_mode.requested_mode is not None and
                    now_ns>=self._paired_mode.deadline) else 'output-unavailable'
                self._paired_error={'type':type(exc).__name__,'message':str(exc)}
        return camera,now_ns

    def _paired_state(self):
        value=self._paired_mode.status()
        value.update(profile_version=VERSION,output=deepcopy(self._paired_output),
                     selector_receipt=deepcopy(self._paired_selector_receipt),error=deepcopy(self._paired_error))
        if self.phase!='running':
            value.update(ready=False,phase='offline',output=None)
        return value

    def software_status(self):
        with self.io:
            camera,now_ns=self._software_locked()
            return self._paired_status_locked(camera,now_ns)

    def _paired_status_locked(self,camera,now_ns):
        result=camera.status(now_ns)
        result['native_scene']=self.native_scene_status()
        result['capabilities']['qemu_sensor_scene_bridge']=result['native_scene'].get('last_consumed') is not None
        result['pipeline_mode']=self._paired_state()
        return result

    def status(self):
        result=super().status()
        result['paired_profile']=deepcopy(self.paired_profile)
        result['pipeline_mode']=self._paired_state()
        result['hardware_version']=self.paired_profile.get('hardware_version','unverified')
        return result

    def _request_pipeline_mode(self,mode):
        camera,now_ns=self._software_locked()
        if camera.job_active() or camera._recorder is not None or camera.full_held or camera.half_held:
            raise CameraError('camera_operation_busy')
        if self.key_events.get(25) or self._video_pending_action is not None:
            raise CameraError('camera_input_pending')
        if self._paired_mode.confirmed_mode is None:
            raise CameraError('pipeline_initial_output_pending')
        before=self.qmp.command('qom-get',{'path':SELECTOR_PATH,'property':'input-levels'})
        after=selector_levels(before,mode)
        count=self._paired_output['commits'] if self._paired_output else 0
        if not self._paired_mode.begin(mode,now_ns,count):
            return {'state':self._paired_status_locked(camera,camera.time_ns),'result':{'queued':True,'already_requested':True}}
        self._paired_selector_receipt={'mode':mode,'before_levels':before,'after_levels':after,
                                      'outcome':'unknown','physical_identity_verified':False}
        self._paired_polled_frame=None
        try:
            if after!=before:
                self.qmp.command('qom-set',{'path':SELECTOR_PATH,'property':'input-levels','value':after})
            actual=self.qmp.command('qom-get',{'path':SELECTOR_PATH,'property':'input-levels'})
            if actual!=after:
                raise CameraError('pipeline_selector_readback_mismatch')
        except (OSError,ValueError,RuntimeError):
            self._paired_mode.delivery_unknown()
            raise
        self._paired_selector_receipt['outcome']='readback-confirmed' if after!=before else 'already-selected'
        self._scene_revision+=1
        self._scene_publish_locked(camera,now_ns,force=True)
        return {'state':self._paired_status_locked(camera,camera.time_ns),'result':{'queued':True,'pipeline_confirmation_pending':True}}

    def software_event(self,request):
        if not isinstance(request,dict) or set(request)!={'type','payload'} or not isinstance(request['payload'],dict):
            raise CameraError('invalid_event_fields')
        kind,payload=request['type'],request['payload']
        if kind=='mode':
            with self.io:
                fields(payload,('mode',))
                return self._request_pipeline_mode(payload.get('mode'))
        if kind=='power':
            raise CameraError('use_simulator_start_stop_controls')
        return super().software_event(request)

    def set_key(self,pin,level):
        if pin==0:
            raise CameraError('pipeline_selector_is_persistent')
        return super().set_key(pin,level)

    def _set_key_locked(self,pin,level):
        self._paired_validate_key_locked(pin,level)
        return super()._set_key_locked(pin,level)

    def _paired_validate_key_locked(self,pin,level):
        # Both software actions and body keys pass this edge while holding io.
        if level==0 and pin in (25,29):
            camera,_=self._software_locked()
            stopping=pin==29 and camera._recorder is not None
            required='photo' if pin==25 else 'video'
            if not stopping and (not self._paired_mode.ready or self._paired_mode.confirmed_mode!=required):
                raise CameraError('pipeline_mode_not_confirmed')


def apply_console(source,profile):
    """Generate only the independent temporary console, never a bound ancestor."""
    from reference_updates import replace_once
    source=private_staging(source)
    target=source/'tools/z62_console.py'
    content=replace_once(target.read_text(encoding='utf-8'),
        'class Z62Machine(AsyncVideoSceneMixin, ModeInputMixin, shared.Machine):',
        'from tools.z62_paired_console import PairedSceneMixin, merge_globals, prepare_parameters\n\n\n'
        'class Z62Machine(PairedSceneMixin, ModeInputMixin, shared.Machine):\n'
        '    paired_profile = '+repr(profile))
    content=replace_once(content,'        for device in devices:',
        '        prepare_parameters(Path(__file__).resolve().parents[2], self.paired_profile)\n'
        '        command = merge_globals(command, self.paired_profile["globals"])\n'
        '        for device in devices:')
    # The concrete generated class defines these methods, taking precedence over a mixin.
    content=replace_once(content,'    def _set_key_locked(self, pin, level):\n',
        '    def _set_key_locked(self, pin, level):\n'
        '        self._paired_validate_key_locked(pin, level)\n')
    content=replace_once(content,'        state["native_scene"] = self.native_scene_status()',
        '        state["paired_profile"] = self.paired_profile.copy()\n'
        '        state["pipeline_mode"] = self._paired_state()\n'
        '        state["hardware_version"] = self.paired_profile["hardware_version"]\n'
        '        state["native_scene"] = self.native_scene_status()')
    target.write_text(content,encoding='utf-8',newline='\n')
    for name in ('z62_paired_console.py','z62_paired_camera.py'):
        (source/'tools'/name).write_bytes(Path(__file__).with_name(name).read_bytes())
    html=source/'web-z62/index.html'
    content=replace_once(html.read_text(encoding='utf-8'),'软件模式 <select id="video-mode">',
                         '成像模式 <select id="video-mode">')
    content=replace_once(content,'<p id="video-info"',
        '<p id="pipeline-info" class="body-input-note" role="status" aria-live="polite">等待成像输出</p>\n  <p id="video-info"')
    content=replace_once(content,
        '上方录像键也驱动此后端；原厂照片／视频拨杆和原厂编码尚未接入。',
        '模式选择发送到固件输入，等待实际输出确认；JPEG、NEF和MP4使用软件编码。实体拨杆身份及原厂编码尚未验证。')
    content=replace_once(content,'启动模拟器后，点击下方“开机”','控制台启动后等待成像输出；顶部可重启或关闭模拟器')
    content=replace_once(content,'<button id="software-on">','<button id="software-on" hidden>')
    content=replace_once(content,'<button id="software-off">','<button id="software-off" hidden>')
    content=replace_once(content,'<button id="software-shutter">','<button id="software-shutter" disabled>')
    content=replace_once(content,'<select id="video-mode">','<select id="video-mode" disabled>')
    html.write_text(content,encoding='utf-8',newline='\n')
    script=source/'web-z62/console.js'
    content=replace_once(script.read_text(encoding='utf-8'),
        "        if (!frame.ok) throw new Error('场景帧读取失败');\n"
        "        const next = URL.createObjectURL(await frame.blob());\n"
        "        el('frame').src = next;\n"
        "        if (imageURL) URL.revokeObjectURL(imageURL);\n"
        "        imageURL = next;",
        "        if (frame.ok) {\n"
        "          const next = URL.createObjectURL(await frame.blob());\n"
        "          el('frame').src = next;\n"
        "          if (imageURL) URL.revokeObjectURL(imageURL);\n"
        "          imageURL = next;\n"
        "        } else if (!state.pipeline_mode?.ready) {\n"
        "          el('placeholder').hidden = false;\n"
        "          el('placeholder').textContent = '等待成像输出确认';\n"
        "          el('frame').hidden = true;\n"
        "        } else { throw new Error('场景帧读取失败'); }")
    content=replace_once(content,"    $('release').disabled = !available;",
        "    $('release').disabled = !available;\n    renderPairedBodyControls(state, available);")
    content=replace_once(content," : '启动中'",
        " : state.pipeline_mode?.ready ? '成像输出已确认' : state.pipeline_mode?.requested_mode ? '模式确认中' : '等待成像输出'")
    # Both reviewed donor text and the development-layer text are accepted.
    labels=("'固件LCD输出 · 非真实取景'","'实时画面 · 1024 × 682'")
    if sum(content.count(label) for label in labels)!=1:
        raise ValueError('Unexpected original LCD label')
    content=replace_once(content,next(label for label in labels if label in content),"'原厂LCD · 软件场景'")
    script.write_text(content+'\n'+
        (Path(__file__).with_name('assets')/'z62-paired-console.js').read_text(encoding='utf-8'),
        encoding='utf-8',newline='\n')
