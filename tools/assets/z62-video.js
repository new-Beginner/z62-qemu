let videoLastState = null;
function renderVideoControls(state, busy = false) {
  videoLastState = state;
  const video = state.video || {};
  const recording = !!video.recording;
  const available = !!state.capabilities?.video;
  const mode = document.getElementById('video-mode');
  mode.value = state.mode;
  mode.disabled = recording || busy;
  document.getElementById('video-start').disabled = busy || !available || recording || state.mode !== 'video' || !state.card.present || state.view === 'playback';
  document.getElementById('video-stop').disabled = busy || !recording;
  document.getElementById('video-cancel').disabled = busy || !recording;
  const info = document.getElementById('video-info');
  if (!available) info.textContent = '录像后端不可用，请按项目说明准备视频运行环境。';
  else if (video.error) info.textContent = `录像未保存：${video.error.message}`;
  else if (recording) info.textContent = `正在录制 · ${video.frames || 0} 帧 · ${((state.virtual_time_ns-video.start_request_ns)/1e9).toFixed(2)} 秒（相机内时间）`;
  else if (video.phase === 'saved') info.textContent = `视频已保存：${video.last_saved} · ${video.frames} 帧`;
  else if (video.phase === 'cancelled') info.textContent = '录像已取消，未创建视频文件。';
  else info.textContent = '切换软件模式为视频，再开始录像。';
  const item = (state.card.images || []).find(row => row.name === state.selected_image);
  if (state.card.present && state.view !== 'playback') {
    const summary = document.getElementById('software-info');
    summary.textContent = summary.textContent.replace(/ · \d+ 张照片$/, ` · ${state.card.photos} 张照片／${state.card.videos} 段视频`);
  }
  const player = document.getElementById('video-playback');
  const playing = item?.kind === 'video';
  player.hidden = !playing;
  if (playing) {
    document.getElementById('software-download').textContent = '下载当前视频';
    if (player.dataset.file !== item.name) {
      player.src = '/software/file/' + encodeURIComponent(item.name);
      player.dataset.file = item.name;
    }
    document.getElementById('software-frame').hidden = true;
    document.getElementById('software-zoom').disabled = true;
    const data = item.metadata;
    document.getElementById('software-info').textContent = `视频回放 ${item.name} · ${data.samples.length} 帧 · ${(data.duration_us/1e6).toFixed(3)} 秒 · 无音频`;
    if (data.codec === 'libx264rgb-lossless')
      info.textContent = '此段为旧实验RGB编码，内置播放器可能偏色；请导出独立解码，或重新录制为兼容格式。';
  } else if (player.dataset.file) {
    player.pause(); player.removeAttribute('src'); delete player.dataset.file; player.load();
    document.getElementById('software-download').textContent = '下载当前照片';
  }
}
