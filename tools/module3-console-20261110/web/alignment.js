'use strict';
let alignmentSelection=null,alignmentVersion=null;
const sourceMergeAllowed=(a,b)=>!!a&&!!b&&a.segment_type==='body'&&b.segment_type==='body'&&a.passage_key===b.passage_key&&['M','W'].includes(a.speaker)&&a.speaker===b.speaker&&a.source_storage_key===b.source_storage_key&&a.source_sha256===b.source_sha256;
function alignmentRows(){return state.result?.alignment?.result?.segments||[];}
function alignmentCanEdit(){return !!state.result?.alignment_editor?.can_edit&&!state.example&&!state.job?.stopped;}
function badAlignmentIds(){return new Set((state.result?.alignment?.result?.issues||[]).flatMap(i=>i.segment_src_ids||[]));}
renderAlignment=function(){
  const data=state.result.alignment.result,rows=data.segments||[],issues=data.issues||[],bad=badAlignmentIds(),editable=alignmentCanEdit();
  const version=state.job?.task?.id;
  if(alignmentVersion!==version){alignmentVersion=version;alignmentSelection=rows.find(s=>bad.has(s._src_id))?._src_id||null;}
  const revision=state.result.alignment_revision;
  const history=revision?`<details class="alignment-audit"><summary>查看本次校正记录</summary><p class="small">${esc(revision.reason)}</p><p class="small muted">修改前：${esc(revision.change.before.map(s=>s.text).join(' / '))}</p><p class="small">修改后：${esc(revision.change.after.text)}</p><p class="small muted">原任务与原始产物保留。新结果仍需核听确认。</p></details>`:'';
  $('#alignment-view').innerHTML=`${issues.length?`<div class="alignment-alert"><strong>对齐有 ${bad.size||issues.length} 处异常</strong><p class="small">点击异常句，试听上下文后校正。原结果会保留。</p><div class="alignment-issue-list">${issues.map(i=>`<div><span>${esc(i.message)}</span>${(i.segment_src_ids||[]).map(id=>`<button type="button" class="text-button" data-align-select="${esc(id)}">${esc(rows.find(s=>s._src_id===id)?.text||id)}</button>`).join('')}</div>`).join('')}</div></div>`:''}${state.result.alignment_editor?.previous_result?'<p class="notice small">正在处理修订任务，下方暂时保留修改前结果，不能用于确认新版本。</p>':''}${history}<div id="alignment-editor"></div><h2>对齐片段 <span class="muted small">${rows.length}句${bad.size?` · ${bad.size}句需核查`:''}</span></h2><div class="segment-list">${rows.map(s=>{const valid=Number.isFinite(s.start_ms)&&Number.isFinite(s.end_ms),start=valid?s.start_ms:s.search_start_ms,end=valid?s.end_ms:s.search_end_ms;return `<div class="segment ${bad.has(s._src_id)?'alignment-bad':''}" data-align-row="${esc(s._src_id)}"><button type="button" data-play="${start}" data-end="${end}">${stamp(start)}<br>${valid?'播放此句':'试听候选范围'}</button><div><span>${esc(s.text)}</span><div class="alignment-row-tools">${bad.has(s._src_id)?'<span class="alignment-warning">需核查</span>':''}${editable?`<button type="button" class="text-button" data-align-select="${esc(s._src_id)}">校正此句</button>`:''}</div></div></div>`;}).join('')}</div>`;
  renderAlignmentEditor();
};
function renderAlignmentEditor(){
  const editor=$('#alignment-editor');if(!editor)return;
  const rows=alignmentRows(),index=rows.findIndex(s=>s._src_id===alignmentSelection),s=rows[index];
  if(!s||!alignmentCanEdit()){editor.innerHTML='';return;}
  const previous=sourceMergeAllowed(rows[index-1],s),next=sourceMergeAllowed(s,rows[index+1]);
  const contextStart=Math.max(0,(rows[index-1]?.start_ms??s.search_start_ms)-1000),contextEnd=Math.min(state.result.alignment.result.duration_ms,(rows[index+1]?.end_ms??s.search_end_ms)+1000);
  editor.innerHTML=`<section class="alignment-editor"><div class="alignment-editor-title"><h2>校正对齐片段</h2><button type="button" class="text-button" id="close-alignment-editor">收起</button></div><p class="alignment-selected">${esc(s.text)}</p><p class="small muted">${s.speaker==='M'?'男声':s.speaker==='W'?'女声':'说话人未标明'} · 解析第 ${(s.source_pages||[]).join('、')} 页</p><button class="secondary" type="button" data-play="${contextStart}" data-end="${contextEnd}">试听前后文 · ${stamp(contextStart)}—${stamp(contextEnd)}</button><form id="alignment-form"><label>校正方式<select id="alignment-operation"><option value="window">调整本句的音频搜索范围</option>${previous?'<option value="merge_previous">与上一句合并（同一说话人）</option>':''}${next?'<option value="merge_next">与下一句合并（同一说话人）</option>':''}</select></label><div id="alignment-preview" class="alignment-preview"></div><div class="fields two"><label>搜索开始时间（秒）<input id="alignment-start" type="number" min="0" step="0.001" required></label><label>搜索结束时间（秒）<input id="alignment-end" type="number" min="0.001" step="0.001" required></label></div><p class="muted small">搜索范围最多30秒。系统会在此范围重新计算实际起止时间；这里填写的时间不会直接作为最终边界。</p><label>核听结果与校正原因<textarea id="alignment-reason" required placeholder="例如：核听后确认 Hmm… 与后一句为同一男声的连续发言，因此合并后重新对齐。"></textarea></label><label class="check-label"><input id="alignment-listened" type="checkbox" required>我已核听这段上下文，并确认本次分句或搜索范围修改。</label><p class="small muted">只重新对齐受影响片段，不重新执行整套OCR，也不调用付费标注。成功后仍需核听确认。</p><button class="primary" type="submit" id="submit-alignment">保存修订并局部重对齐</button><p class="error-text" id="alignment-error" role="alert"></p></form></section>`;
  $('#alignment-operation').addEventListener('change',updateAlignmentPreview);updateAlignmentPreview();
}
function updateAlignmentPreview(){
  const rows=alignmentRows(),index=rows.findIndex(s=>s._src_id===alignmentSelection),operation=$('#alignment-operation').value;
  const selected=operation==='merge_previous'?rows.slice(index-1,index+1):operation==='merge_next'?rows.slice(index,index+2):[rows[index]];
  $('#alignment-preview').textContent=selected.map(s=>s.text).join(' ');
  $('#alignment-start').value=(Math.min(...selected.map(s=>s.search_start_ms))/1000).toFixed(3);
  $('#alignment-end').value=(Math.max(...selected.map(s=>s.search_end_ms))/1000).toFixed(3);
}
$('#alignment-view').addEventListener('click',e=>{
  const button=e.target.closest('[data-align-select]');
  if(button){
    if(!alignmentCanEdit())return;
    alignmentSelection=button.dataset.alignSelect;renderAlignmentEditor();
    $('#alignment-editor').scrollIntoView({block:'start',behavior:'auto'});$('#alignment-operation')?.focus({preventScroll:true});
  }
  if(e.target.id==='close-alignment-editor'){alignmentSelection=null;renderAlignmentEditor();}
});
$('#alignment-view').addEventListener('submit',async e=>{
  if(e.target.id!=='alignment-form')return;e.preventDefault();
  const button=$('#submit-alignment');button.disabled=true;$('#alignment-error').textContent='';
  try{
    const start=Number($('#alignment-start').value),end=Number($('#alignment-end').value);
    if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start||end-start>30)throw Error('搜索范围须起点小于终点，且不超过30秒');
    await post(`/console-api/workflows/${state.job.id}/alignment-revisions`,{task_id:state.job.task.id,artifact_hash:state.result.alignment.artifact_hash,segment_id:alignmentSelection,operation:$('#alignment-operation').value,search_start_ms:Math.round(start*1000),search_end_ms:Math.round(end*1000),reason:$('#alignment-reason').value.trim(),listened:$('#alignment-listened').checked});
    state.signature='';await updateJob();await refreshJobs();toast('修订任务已建立，正在局部重对齐；原结果保留');
  }catch(error){if($('#alignment-error'))$('#alignment-error').textContent=error.message;}
  finally{if(button.isConnected)button.disabled=false;}
});
const actionsBeforeAlignment=renderActions;
renderActions=function(busy){
  actionsBeforeAlignment(busy);
  if(!busy&&alignmentCanEdit()&&state.job?.task?.issues?.some(i=>i.severity==='error')){
    const panel=$('#action-panel'),retryMarkup=panel.innerHTML;
    panel.hidden=false;panel.innerHTML=`<h2>先校正异常片段</h2><p class="small muted">使用上方异常清单定位句子，核听后提交局部校正。重复整套重试通常不会改变同一处分句问题。</p><button type="button" class="secondary" id="jump-alignment-error">定位异常并校正</button><details><summary>仍需完整重试当前阶段</summary>${retryMarkup}</details>`;
  }
};
$('#action-panel').addEventListener('click',e=>{
  if(e.target.id!=='jump-alignment-error')return;
  alignmentSelection=[...badAlignmentIds()][0]||alignmentRows()[0]?._src_id;renderAlignmentEditor();
  $('#alignment-editor')?.scrollIntoView({block:'start'});$('#alignment-operation')?.focus({preventScroll:true});
});
