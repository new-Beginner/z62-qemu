const renderVideoBeforeAsync = renderVideoControls;
renderVideoControls = function(state, busy = false) {
  renderVideoBeforeAsync(state, busy);
  const video = state.video || {};
  if (!video.async || !video.job_id) return;
  const active = !video.terminal;
  if (active) {
    document.getElementById('video-mode').disabled = true;
    document.getElementById('video-start').disabled = true;
    document.getElementById('video-stop').disabled = true;
    document.getElementById('software-shutter').disabled = true;
    document.getElementById('video-cancel').disabled = busy || video.phase === 'committing' || video.phase === 'cancelling';
    const labels = {queued:'后台任务已排队',starting:'正在启动后台编码',preparing:'正在校验采样帧',
      encoding_auditing:'正在编码与独立审计',validating:'正在复核文件',ready:'等待后台退出',
      awaiting_worker_exit:'等待后台退出',checking_result:'正在核对后台产物',committing:'正在提交虚拟卡',
      cancelling:'正在取消，等待后台退出',worker_reported_error:'后台报告错误，等待退出'};
    document.getElementById('video-info').textContent = `${labels[video.phase] || video.phase} · 已准备 ${video.prepared_frames || 0}/${video.frames} 帧 · 宿主等待 ${video.elapsed_wall_seconds.toFixed(1)} 秒`;
  }
  if (video.terminal && video.phase === 'error')
    document.getElementById('video-info').textContent = `视频未保存：${video.error?.message || '后台失败'}`;
  if (video.terminal && video.phase === 'cancelled')
    document.getElementById('video-info').textContent = '录像已取消，后台已退出，未提交视频。';
};
