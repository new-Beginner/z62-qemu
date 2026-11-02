// Backend receipts are authoritative; HTTP queue acceptance is not a saved photo.
let nativeReceiptSeq = 0;
function renderNativeInputReceipt(state) {
  const message = document.getElementById('software-message');
  const events = state.shared_camera_input?.events || [];
  const event = [...events].reverse().find(row =>
    (row.pin === 25 && row.level === 0 && (row.error || row.result?.name)) ||
    (row.pin === 23 && row.level === 0 && row.software_applied && row.result?.deleted));
  if (!message || !event || event.sequence <= nativeReceiptSeq) return;
  nativeReceiptSeq = event.sequence;
  if (event.hardware_outcome === 'unknown') {
    message.textContent = '快门输入结果未知，请查看模拟器状态。';
  } else if (event.software_applied && event.result?.name) {
    message.textContent = `照片已保存：${event.result.name}`;
  } else if (event.software_applied && event.result?.deleted) {
    message.textContent = `照片已删除：${event.result.deleted}`;
  } else if ((event.error || '').includes('no_card')) {
    message.textContent = '没有可用的虚拟卡，照片未保存。';
  } else if (/scene_(settings_pending|not_consumed|stale)/.test(event.error || '')) {
    message.textContent = '场景帧尚未同步，照片未保存。';
  } else {
    message.textContent = `照片保存状态未确认：${event.error || '未知错误'}`;
  }
}

function renderNativeSoftwareInfo(state) {
  const info = document.getElementById('software-info');
  if (!info) return;
  const zoom = document.getElementById('software-zoom');
  if (zoom) {
    zoom.disabled = state.view !== 'playback';
    zoom.value = String(state.zoom || 1);
  }
  const photo = (state.card?.images || []).find(row => row.name === state.selected_image);
  if (state.view === 'playback' && photo) {
    const data = photo.metadata || {}, exposure = data.exposure || {}, lens = data.lens || {};
    const shutter = exposure.shutter_seconds;
    const speed = shutter > 0 ? (shutter < 1 ? `1/${Math.round(1/shutter)}` : `${shutter}`) : '?';
    info.textContent = `回放 ${photo.name} · 拍摄帧 ${data.frame_id ?? '?'} · ISO ${exposure.iso ?? '?'} · ${speed} s · f/${lens.aperture ?? '?'} · ${lens.focal_length_mm ?? '?'} mm`;
    return;
  }
  const tag = state.native_scene?.last_consumed;
  const sample = tag ? `源帧 ${tag.frame_id} · ${(tag.virtual_time_ns/1e9).toFixed(3)} s` : '等待原生场景帧';
  const lens = state.lens || {};
  const focus = typeof lens.focus_position === 'number' ? lens.focus_position.toFixed(3) : '?';
  const target = typeof lens.focus_target === 'number' ? lens.focus_target.toFixed(3) : '?';
  info.textContent = `取景 · ${sample} · 当前对焦 ${focus} → ${target}${lens.moving ? ' 移动中' : ''} · ${state.card?.present ? state.card.images.length+' 张照片' : '无卡'}`;
}
