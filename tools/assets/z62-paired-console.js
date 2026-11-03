const renderVideoBeforePaired = renderVideoControls;
renderVideoControls = function(state, busy = false) {
  renderVideoBeforePaired(state, busy);
  const pipeline = state.pipeline_mode || {};
  const ready = pipeline.ready === true;
  const pending = !!pipeline.requested_mode;
  const names = {photo:'照片', video:'视频'};
  const phases = {'waiting-output':'等待成像输出', 'awaiting-output':'已发送模式输入，等待输出确认',
    'awaiting-current-frame':'模式已到达，等待当前设置的新帧', 'timed-out':'模式确认超时，请检查模拟器状态',
    'output-unavailable':'暂未取得输出状态', offline:'模拟器未运行', ready:'当前设置的输出已确认'};
  const info = document.getElementById('pipeline-info');
  info.textContent = `${phases[pipeline.phase] || '等待成像输出'}${pipeline.confirmed_mode ? ' · ' + names[pipeline.confirmed_mode] : ''}`;
  info.style.color = ready ? '#315c43' : '#79561b';
  const mode = document.getElementById('video-mode');
  mode.value = pipeline.requested_mode || pipeline.confirmed_mode || state.mode;
  mode.disabled ||= pending || !pipeline.confirmed_mode || state.half_pressed || state.full_pressed;
  document.getElementById('software-shutter').disabled ||= busy || !ready || pipeline.confirmed_mode !== 'photo';
  document.getElementById('video-start').disabled ||= !ready || pipeline.confirmed_mode !== 'video';
  // Cancelling and stopping remain available while an output is delayed.
  document.getElementById('software-on').hidden = true;
  document.getElementById('software-off').hidden = true;
  if (!state.video?.recording && !state.video?.job_id && !state.video?.error)
    document.getElementById('video-info').textContent = '选择视频模式，输出确认后可开始录像。';
};

function renderPairedBodyControls(state, available) {
  const pipeline = state.pipeline_mode || {};
  const photo = document.querySelector('[data-pin="25"]');
  const record = document.querySelector('[data-pin="29"]');
  if (photo) photo.disabled = !available || !pipeline.ready || pipeline.confirmed_mode !== 'photo';
  if (record) record.disabled = !available || (!videoLastState?.video?.recording &&
    (!pipeline.ready || pipeline.confirmed_mode !== 'video'));
}
