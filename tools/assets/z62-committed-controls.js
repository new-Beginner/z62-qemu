const committedFormState = {};
for (const name of ['optics', 'exposure']) {
  const form = document.getElementById('software-' + name);
  committedFormState[name] = {form, dirty:false};
  if (form) {
    const changed = () => { committedFormState[name].dirty = true; };
    form.addEventListener('input', changed);
    form.addEventListener('change', changed);
  }
}

function syncCommittedForm(name, values, summary) {
  const draft = committedFormState[name];
  if (!draft.form) return;
  const entries = Object.entries(values).map(([key, value]) =>
    [draft.form.querySelector('[name="' + key + '"]'), value]).filter(([field]) => field);
  const agrees = entries.every(([field, value]) => Number(field.value) === Number(value));
  if (agrees) draft.dirty = false;
  if (!draft.dirty) {
    for (const [field, value] of entries) {
      if (field === document.activeElement) continue;
      if (field.tagName === 'SELECT' && !Array.from(field.options).some(option => Number(option.value) === Number(value))) {
        const option = document.createElement('option');
        option.value = String(value); option.textContent = String(value) + '（当前）';
        field.appendChild(option);
      }
      field.value = String(value);
    }
  }
  const label = document.getElementById('software-' + name + '-state');
  label.textContent = (draft.dirty ? '有未应用更改；当前已应用：' : '已应用：') + summary + ' · C 软件模型';
}

const renderVideoBeforeCommittedControls = renderVideoControls;
renderVideoControls = function(state, busy = false) {
  renderVideoBeforeCommittedControls(state, busy);
  const pipeline = state.pipeline_mode || {};
  const video = state.video || {};
  const job = video.async && video.job_id && !video.terminal;
  // Unlike ||= this can release the initial disabled attribute when a real
  // committed photo frame arrives, while retaining all active-operation gates.
  document.getElementById('software-shutter').disabled = !!(busy || !state.powered || !state.card?.present ||
    !pipeline.ready || pipeline.confirmed_mode !== 'photo' || video.recording || job);
  const lens = state.lens || {};
  const exposure = state.exposure || {};
  if (Number.isFinite(lens.focus_target))
    syncCommittedForm('optics', {focal_length_mm:lens.focal_length_mm, aperture:lens.aperture, focus_target:lens.focus_target},
      `${lens.focal_length_mm} mm，f/${lens.aperture}，目标位置 ${lens.focus_target.toFixed(2)}`);
  if (Number.isFinite(exposure.iso))
    syncCommittedForm('exposure', {shutter_seconds:exposure.shutter_seconds, iso:exposure.iso},
      `${exposure.shutter_seconds} s，ISO ${exposure.iso}`);
};
