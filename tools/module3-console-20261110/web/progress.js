'use strict';
const duration = seconds => seconds < 60 ? `${seconds}秒` : `${Math.floor(seconds / 60)}分${seconds % 60}秒`;
const progressStates = {waiting:'未开始',pending:'排队中',running:'处理中',review:'待你复核',complete:'已完成',failed:'处理受阻',stopped:'已停止'};
const originalPipeline = renderPipeline;
renderPipeline = function(phase) { originalPipeline(phase); renderProgress(); };
function renderProgress() {
  const panel = $('#stage-progress'), job = state.job, data = job?.progress;
  panel.hidden = !!state.example || !data;
  $('#stop-task').hidden = !!state.example || !data?.can_stop;
  if (panel.hidden) return;
  const age = data.heartbeat_age_seconds;
  const heartbeat = age == null ? '' : age < 60 ? `后台心跳正常 · ${age}秒前` : `已${duration(age)}未收到后台心跳，请留意任务状态`;
  panel.innerHTML = `<div class="progress-overview"><span>本次已用 ${duration(data.elapsed_seconds)}</span><span>${esc(heartbeat)}</span></div><div class="stage-progress-list">${data.stages.map(s => {
    const complete = ['complete','review'].includes(s.state);
    const active = s.state === 'running';
    const required=typeof reviewableQuestions==='function'?reviewableQuestions():questions();
    const reviewed = s.state === 'review' && ['annotate_sample','annotate'].includes(s.phase) && job.phase === s.phase ? required.filter(q => reviewValid(readReview(q._src_id))).length : null;
    const review = reviewed != null ? `<div class="review-progress"><span>逐题复核 ${reviewed} / ${required.length}</span><progress aria-label="${esc(s.label)}逐题复核进度" value="${reviewed}" max="${required.length || 1}"></progress></div>` : '';
    const measured=active&&s.measured_total;
    return `<div class="stage-progress-row ${esc(s.state)}"><div class="stage-progress-title"><strong>${esc(s.label)}</strong><span>${progressStates[s.state]}${s.elapsed_seconds == null ? '' : ` · 已用 ${duration(s.elapsed_seconds)}`}</span></div><progress aria-label="${esc(s.label)}${measured?'题目':'处理'}进度" ${measured?`value="${s.measured_count}"`:active ? '' : `value="${complete ? s.total_steps : s.completed_steps}"`} max="${measured?s.measured_total:s.total_steps}"></progress><div class="stage-progress-detail"><span>${esc(s.detail)}</span>${active && s.total_steps > 1 ? `<span>已完成 ${s.completed_steps} / ${s.total_steps} 个子步骤</span>` : ''}</div>${review}</div>`;
  }).join('')}</div><p class="muted small progress-footnote">处理时间受解析页数、首次模型加载和标注服务速度影响。动态条表示正在执行；等待你复核时，不会继续运行下一步。</p>`;
  if (job.stopped) {
    $('#task-subtitle').textContent = `已停止 · ${phaseNames[job.phase] || job.phase} · 材料和已有结果保留`;
    $('#task-message').textContent = '本次处理已停止。你可以查看已有结果，或填写原因后重新处理当前阶段。';
    $('#task-issues').hidden = true;
    renderActions(false);
  } else if (job.error || job.task?.issues?.some(i=>i.severity==='error')) {
    $('#task-subtitle').textContent = `处理受阻 · ${phaseNames[job.phase] || job.phase} · 请查看下方问题`;
    $('#task-message').textContent = '当前检查未通过，不能进入下一流程。材料和已有结果已保留，请先查看具体问题。';
  }
}
const originalUpdateJob = updateJob;
updateJob = async function() { await originalUpdateJob(); renderProgress(); };
const originalReviewStage = reviewStage;
reviewStage = function() { return !state.job?.stopped && originalReviewStage(); };
const originalReviewCount = updateReviewCount;
updateReviewCount = function() { originalReviewCount(); renderProgress(); };
const originalActions = renderActions;
renderActions = function(busy) {
  if (!state.example && state.job?.stopped) {
    const panel = $('#action-panel'); panel.hidden = false;
    panel.innerHTML = `<h2>本次处理已停止</h2><p class="muted small">已有结果保留。重新处理可能再次执行识别或模型调用。</p>${state.job.task ? '<label>重新处理说明<input id="retry-reason" placeholder="填写需要重新处理的原因"></label><div class="action-buttons"><button class="secondary" data-action="retry">重新处理当前阶段</button></div>' : '<p class="muted small">材料上传尚未完成，请点击“新建处理”重新选择材料。</p>'}`;
    return;
  }
  originalActions(busy);
};
// A real stop is explicit and bound to the workflow/task version displayed.
let stopTarget = null;
$('#stop-task').addEventListener('click', () => {
  stopTarget = {id: state.job.id, task_id: state.job.task?.id ?? null};
  $('#stop-error').textContent = ''; $('#stop-dialog').showModal();
});
$('#keep-processing').addEventListener('click', () => $('#stop-dialog').close());
$('#confirm-stop').addEventListener('click', async () => {
  const button = $('#confirm-stop'); button.disabled = true;
  try {
    await post(`/console-api/workflows/${stopTarget.id}/stop`, {task_id:stopTarget.task_id});
    $('#stop-dialog').close(); state.signature = '';
    if (state.job?.id === stopTarget.id) await updateJob();
    await refreshJobs(); toast('本次处理已停止，材料和已有结果已保留');
  } catch (e) { $('#stop-error').textContent = e.message; }
  finally { button.disabled = false; }
});
const originalRefresh = refreshJobs;
refreshJobs = async function() {
  await originalRefresh();
  if (!state.token) return;
  // Status text must also reflect stopped workflows in the history list.
  document.querySelectorAll('.job-item').forEach(el => {
    if (state.job?.stopped && el.dataset.job === state.job.id) el.querySelector('span').textContent = `${phaseNames[state.job.phase]} · 已停止`;
  });
};
uploadFile = function(id,kind,file,index) {
  return new Promise((resolve,reject) => {
    const xhr = new XMLHttpRequest(); state.activeUpload = xhr;
    xhr.open('PUT',`/console-api/workflows/${id}/files/${kind}?name=${encodeURIComponent(file.name)}`);
    xhr.setRequestHeader('Authorization','Bearer '+state.token);
    xhr.upload.onprogress = e => { if(e.lengthComputable) $('#upload-bar').value=(index+e.loaded/e.total)/3*100; };
    xhr.onload = () => { state.activeUpload=null; try { const data=JSON.parse(xhr.responseText); if(xhr.status>=200&&xhr.status<300)resolve(data.data);else reject(Error(data.msg||'上传失败')); } catch { reject(Error('上传响应异常')); } };
    xhr.onerror = () => {state.activeUpload=null;reject(Error('上传中断，请检查本地服务后重试'));};
    xhr.onabort = () => {state.activeUpload=null;reject(Error('已停止本次上传'));};
    xhr.send(file);
  });
};
$('#stop-upload').addEventListener('click',async () => {
  const id=state.uploadId;if(!id)return;
  state.uploadCancelled=true;state.activeUpload?.abort();
  try {
    const job=await api('/console-api/workflows/'+id);
    await post(`/console-api/workflows/${id}/stop`,{task_id:job.task?.id??null});
    await openJob(id);toast('本次上传已停止');
  } catch(e) {toast(e.message,true);}
});
setInterval(() => { if (state.job && !state.example) renderProgress(); }, 1000);
