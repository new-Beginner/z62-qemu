(() => {
  const el = id => document.getElementById(`software-${id}`);
  // Editing this pane must not send MENU/OK/mode shortcuts to the firmware.
  // Key-up still bubbles so an earlier held firmware key can be released.
  document.querySelector('.software-camera').addEventListener('keydown', event => event.stopPropagation());
  let busy = false, imageURL = null;
  async function event(type, payload = {}) {
    const response = await fetch('/software/event', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({type,payload})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '操作失败');
    return result;
  }
  async function perform(action) {
    if (busy) return;
    busy = true;
    document.querySelectorAll('.software-controls button').forEach(button => button.disabled = true);
    try { await action(); el('message').textContent = '操作已完成'; }
    catch (error) { el('message').textContent = error.message; }
    finally { busy = false; document.querySelectorAll('.software-controls button').forEach(button => button.disabled = false); }
  }
  el('on').onclick = () => perform(() => event('power', {on:true}));
  el('off').onclick = () => perform(() => event('power', {on:false}));
  el('shutter').onclick = () => perform(async () => {
    try {
      const saved = await event('shutter', {stage:'full',pressed:true});
      el('info').textContent = `已保存 ${saved.result.name}`;
    } finally { await event('shutter', {stage:'full',pressed:false}); }
  });
  for (const [id, action] of [['play','open'],['live','close'],['prev','previous'],['next','next']])
    el(id).onclick = () => perform(() => event('playback', {action}));
  el('delete').onclick = () => perform(() => event('delete'));
  el('zoom').onchange = () => perform(() => event('zoom', {factor:Number(el('zoom').value)}));
  for (const [id, type] of [['optics','lens'],['exposure','exposure']])
    el(id).onsubmit = submission => {
      submission.preventDefault();
      const payload = Object.fromEntries([...new FormData(el(id))].map(([key,value]) => [key,Number(value)]));
      perform(() => event(type, payload));
    };
  async function refresh() {
    try {
      const response = await fetch('/software/status', {cache:'no-store'});
      const state = await response.json();
      if (!response.ok) throw new Error(state.error || '等待相机时钟');
      el('placeholder').hidden = state.powered;
      el('placeholder').textContent = '软件相机已关机';
      el('frame').hidden = !state.powered;
      el('info').textContent = `${state.view === 'playback' ? '回放 '+state.selected_image : '取景'} · 帧 ${state.frame_id} · ${(state.virtual_time_ns/1e9).toFixed(3)} s · 对焦 ${state.lens.focus_position.toFixed(3)} → ${state.lens.focus_target.toFixed(3)}${state.lens.moving ? ' 移动中' : ''} · ${state.card.present ? state.card.images.length+' 张照片' : '无卡'}`;
      el('download').hidden = !state.selected_image;
      if (state.selected_image) el('download').href = '/software/file/'+encodeURIComponent(state.selected_image);
      if (state.powered && !busy) {
        const frame = await fetch('/software/frame', {cache:'no-store'});
        if (!frame.ok) throw new Error('场景帧读取失败');
        const next = URL.createObjectURL(await frame.blob());
        el('frame').src = next;
        if (imageURL) URL.revokeObjectURL(imageURL);
        imageURL = next;
      }
    } catch (error) { el('info').textContent = error.message; }
    setTimeout(refresh, 700);
  }
  refresh();
})();
