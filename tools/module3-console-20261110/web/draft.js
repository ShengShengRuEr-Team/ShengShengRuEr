'use strict';
const draftFieldNames={question_text:'题干',option_a:'选项A',option_b:'选项B',option_c:'选项C',option_d:'选项D',correct_option:'正确答案',explanation_text:'解析'};
function draftQuestionPending(q){
  if(!state.result?.draft_first)return false;
  return (state.result.draft_pending||[]).some(p=>p.question_src_id===q._src_id);
}
function reviewableQuestions(){return questions().filter(q=>!draftQuestionPending(q));}
const questionsBeforeDraft=renderQuestions;
renderQuestions=function(){questionsBeforeDraft();renderDraftNotice();};
function renderDraftNotice(){
  $('#draft-pending-notice')?.remove();if(!state.result?.draft_first)return;
  const relevant=new Set(questions().map(q=>q._src_id)),pending=(state.result.draft_pending||[]).filter(p=>relevant.has(p.question_src_id));
  const box=document.createElement('div');box.id='draft-pending-notice';box.className=pending.length?'draft-pending':'draft-summary';
  const buttons=list=>list.map(p=>`<button class="text-button" data-draft-q="${esc(p.question_src_id)}">第${p.question_index}题：${p.fields.length?p.fields.map(k=>draftFieldNames[k]||k).join('、')+'待补':'标注待生成'}</button>`).join('');
  box.innerHTML=`<strong>${pending.length?`草稿已生成 · ${pending.length}题待补或待标注`:'题目草稿已生成'}</strong><p class="small">${pending.length?'识别不到的内容已留空，其余题目继续生成。请在生成后集中核对，待补项未处理前不能正式入库。':'已保留题干、选项、答案和解析来源，尚未代表人工验收通过。'}</p>${buttons(pending.slice(0,5))}${pending.length>5?`<details><summary>查看其余 ${pending.length-5} 道待处理题</summary>${buttons(pending.slice(5))}</details>`:''}`;
  $('#result-view').prepend(box);
  document.querySelectorAll('[data-qid]').forEach(button=>{const p=pending.find(p=>p.question_src_id===button.dataset.qid);if(p)button.querySelector('small').textContent=p.fields.length?'待补':'待标注';});
}
const questionBeforeDraft=renderQuestion;
renderQuestion=function(){
  questionBeforeDraft();const q=questions()[state.question];if(!q||!state.result?.draft_first)return;
  if(!q.correct_option)$('#question-detail .question-meta span:last-child').textContent='答案 待补';
  document.querySelectorAll('#question-detail .option-list li').forEach((li,index)=>{if(!q['option_'+'abcd'[index]])li.insertAdjacentHTML('beforeend','<span class="muted">待补</span>');});
  if(draftQuestionPending(q)){
    $('#question-detail .review-box')?.remove();
    const info=(state.result.draft_pending||[]).find(p=>p.question_src_id===q._src_id);
    const notice=document.createElement('p');notice.className='draft-pending small';notice.textContent=info.fields.length?'本题来源字段尚待补全，已跳过标注；其余题目照常生成。':'本题标注尚未完成，已保留题目；其余题目照常生成。';$('#question-detail').prepend(notice);
  }
};
const countBeforeDraft=updateReviewCount;
updateReviewCount=function(){
  countBeforeDraft();if(!state.result?.draft_first||!reviewStage())return;
  const qs=reviewableQuestions(),count=qs.filter(q=>reviewValid(readReview(q._src_id))).length;
  if($('#review-count'))$('#review-count').textContent=`已复核 ${count} / ${qs.length} 道已生成题目；${questions().length-qs.length}题留待补全`;
  const button=$('#continue-review');if(button){button.disabled=count!==qs.length;if(!qs.length&&state.job.phase==='annotate_sample')button.textContent='跳过待补题，生成其余题目草稿';}
};
const actionsBeforeDraft=renderActions;
renderActions=function(busy){
  actionsBeforeDraft(busy);if(busy||state.example||!state.result?.draft_first||state.job?.stopped)return;
  if(state.job.phase==='assemble'&&$('#content-confirmed')){
    $('#content-confirmed').parentElement.lastChild.textContent='允许先生成可识别题目的标注草稿，缺失项稍后补全。';
    const heading=$('#action-panel h2');if(heading)heading.textContent='先生成标注草稿';
    const note=$('#action-note');if(note)note.placeholder='可选：记录本次生成说明，来源字段可在生成后核查';
    const button=$('[data-action="assembly"]');if(button)button.textContent='生成前5题标注草稿';
  }
  if(['annotate_sample','annotate'].includes(state.job.phase)){
    const panel=$('#action-panel'),pending=(state.result.draft_pending||[]);
    if(state.job.phase==='annotate'&&pending.length&&$('#continue-review')){
      $('#continue-review').disabled=true;$('#continue-review').textContent='补全待处理项后才能正式入库';
    }
    if(pending.length)panel.insertAdjacentHTML('beforeend',`<div class="draft-followup"><p class="small muted">草稿和已生成结果均保留。补充来源字段后可重新生成；修改前的标注保留在历史任务中。</p><button class="secondary" type="button" id="return-draft">返回题目草稿补全字段</button>${state.job.phase==='annotate'?'<label>重新生成说明<input id="retry-reason" placeholder="来源完整但部分标注失败时，可重新生成"></label><button class="secondary" data-action="retry">重新生成标注草稿</button>':''}</div>`);
  }
};
$('#result-view').addEventListener('click',e=>{
  const b=e.target.closest('[data-draft-q]');if(!b)return;const index=questions().findIndex(q=>q._src_id===b.dataset.draftQ);if(index<0)return;
  state.question=index;renderQuestions();$('#question-detail').scrollIntoView({block:'start'});
});
$('#action-panel').addEventListener('click',async e=>{
  if(e.target.id!=='return-draft')return;const b=e.target;b.disabled=true;
  try{await post(`/console-api/workflows/${state.job.id}/return-to-assembly`,{task_id:state.job.task.id,result_hash:state.result.result_hash});state.signature='';await updateJob();await refreshJobs();toast('已返回题目草稿，修改前结果保留在历史任务中');}catch(error){toast(error.message,true);b.disabled=false;}
});
