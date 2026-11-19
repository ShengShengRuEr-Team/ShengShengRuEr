import { useEffect, useState } from 'react'
import { Alert, Button, Card, Checkbox, Input, Radio, Select, Space, Typography } from 'antd'
import { request } from '../../../api/client'
import { WORKFLOWS } from '../../../api/processing'
import type { QuestionView, ReviewItem, WorkflowDetail } from '../../../api/processing-types'
import { skillName } from '../../../api/processing-adapters'

function blank(question: QuestionView): ReviewItem { return {question_src_id:question.question_src_id,content:'changes_required',primary_skills:[],answer_evidence:[],error_causes:[],distractor_assessments:[],candidate_changes:[],empty_errors_confirmed:false,note:'',issues:[]} }
const fields = ['primary_skills','answer_evidence','error_causes','distractor_assessments','candidate_changes'] as const
const suggestedNote = '已逐题核对本次结果的题干、选项、来源答案与解析、技能、答案证据及错因证据，未发现需修改项。'
type Drafts = Record<string,ReviewItem>
function complete(question:QuestionView,item?:ReviewItem) {
  return Boolean(item && item.content==='approved' && !item.issues.length && fields.every(field=>
    (item[field]??[]).length===(question.review_requirements[field]??[]).length && (question.review_requirements[field]??[]).every(ref=>
      (item[field]??[]).some(row=>row.reference===ref&&row.decision==='approved'))) &&
    (question.generation_state!=='generated_empty'||item.empty_errors_confirmed))
}
export default function ReviewPanel({owner, workflow, question, questions, busy, dirtyChanged, command}: {
  owner:number; workflow:WorkflowDetail; question:QuestionView; questions:QuestionView[]; busy:boolean; dirtyChanged:(dirty:boolean)=>void
  command:(action:string,path:string,body:Record<string,unknown>,method?:'POST'|'PATCH')=>Promise<{result:Record<string,unknown>}|null>
}) {
  const [drafts,setDrafts] = useState<Record<string,ReviewItem>>({}); const [version,setVersion] = useState(workflow.review_session_version ?? 1)
  const [unsaved,setUnsaved] = useState<Record<string,ReviewItem>>({})
  const [ready,setReady] = useState(false); const [error,setError] = useState(''); const [notice,setNotice] = useState('')
  const [audio,setAudio] = useState(false); const [reference,setReference] = useState(''); const [issueField,setIssueField] = useState('question')
  const [bulkNote,setBulkNote] = useState(suggestedNote); const [saving,setSaving] = useState(false)
  const key = `m3-review:${owner}:${workflow.workflow_id}:${workflow.revision_id}:${workflow.result_hash}`
  const root = `review-sessions/${workflow.review_session_id}`
  const disabled=busy||saving||!ready||workflow.content_review_state==='approved'
  const selectedCount=questions.filter(q=>complete(q,drafts[q.question_src_id])).length
  const allSelected=questions.length>0&&selectedCount===questions.length
  const conclusionsComplete=questions.every(q=>q.generation_state!=='generation_incomplete'&&(!q.assessment_summary||q.assessment_summary.resolved===3))
  function persist(changes:Drafts,nextVersion=version,form:Record<string,unknown>={}) {
    localStorage.setItem(key,JSON.stringify({version:nextVersion,drafts:changes,audio,reference,bulkNote,...form}))
  }
  useEffect(() => {
    const controller = new AbortController()
    void request<{row_version:number;items:ReviewItem[]}>({url:`${WORKFLOWS}/${workflow.workflow_id}/${root}`,params:{limit:100},signal:controller.signal}).then(data => {
      const saved = Object.fromEntries(data.items.map(item => [item.question_src_id,item])); setVersion(data.row_version)
      if(controller.signal.aborted)return
      try { const raw = localStorage.getItem(key); if (raw) { const local = JSON.parse(raw) as {version:number;drafts:Drafts;audio?:boolean;reference?:string;bulkNote?:string}
        if (local.version === data.row_version) {Object.assign(saved,local.drafts);setUnsaved(local.drafts);setAudio(local.audio??false);setReference(local.reference??'');setBulkNote(local.bulkNote??suggestedNote)
          setNotice(Object.keys(local.drafts).length?'已恢复同版本的本地未保存意见，请核对后显式保存':'已恢复本次审核填写内容');dirtyChanged(Object.keys(local.drafts).length>0)}
        else {localStorage.setItem(`${key}:conflict:${local.version}`,raw);setNotice('本地旧意见与当前审核版本不符，已保留本地记录，未自动应用')} }
      } catch {setNotice('本地意见记录无法读取，请以服务器已保存记录为准')}
      setDrafts(saved);setReady(true)
    }).catch(cause => {if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '审核读取失败')})
    return () => controller.abort()
  }, [key,workflow.workflow_id,root,dirtyChanged])
  const item = drafts[question.question_src_id] ?? blank(question)
  function changeItems(changes:Drafts,form:Record<string,unknown>={}) {
    const remaining={...unsaved,...changes}
    setDrafts(previous=>({...previous,...changes}));setUnsaved(remaining);dirtyChanged(Object.keys(remaining).length>0)
    persist(remaining,version,form);setError('');setNotice('')
  }
  function update(value: Partial<ReviewItem>) {
    changeItems({[question.question_src_id]:{...item,...value}})
  }
  function selectAll(checked:boolean) {
    const changes:Drafts={}
    for(const q of questions) {
      const value=drafts[q.question_src_id]??blank(q)
      changes[q.question_src_id]={...value,content:checked?'approved':'changes_required',
        ...Object.fromEntries(fields.map(field=>[field,checked?(q.review_requirements[field]??[]).map(ref=>({reference:ref,decision:'approved'})):[]])),
        empty_errors_confirmed:checked&&q.generation_state==='generated_empty'}
    }
    changeItems(changes)
  }
  function applyNote(onlyEmpty:boolean) {
    const note=bulkNote.trim();if(!note)return
    const changes:Drafts={}
    for(const q of questions) {const value=drafts[q.question_src_id]??blank(q)
      if(!onlyEmpty||!value.note.trim())changes[q.question_src_id]={...value,note}}
    const nextReference=onlyEmpty&&reference.trim()?reference:note
    setReference(nextReference);changeItems(changes,{reference:nextReference})
    setNotice(onlyEmpty?'已填入空白题目意见及整套依据，可逐题调整':'已填入全部题目意见及整套依据，可逐题调整')
  }
  async function saveItems(values:ReviewItem[],returned=false) {
    if(disabled)return
    const invalid=values.find(value=>(returned||value.content==='changes_required'||value.issues.length>0)&&!value.note.trim())
    if(invalid){const q=questions.find(q=>q.question_src_id===invalid.question_src_id);setError(`第${q?.question_no??''}题需填写具体修改原因，或先确认内容通过`);return}
    setSaving(true);setError('')
    let nextVersion=version;const remaining={...unsaved}
    try {
      for(let start=0;start<values.length;start+=25) {
        const batch=values.slice(start,start+25)
        const result=await command('review_save',`${root}/${returned?'returns':'items'}`,{
          expected_result_hash:workflow.result_hash,expected_session_version:nextVersion,items:batch},returned?'POST':'PATCH')
        if(!result)return
        nextVersion=Number(result.result.session_version);setVersion(nextVersion)
        setDrafts(previous=>({...previous,...Object.fromEntries(batch.map(value=>[value.question_src_id,value]))}))
        for(const value of batch)delete remaining[value.question_src_id]
        setUnsaved({...remaining});dirtyChanged(Object.keys(remaining).length>0);persist(remaining,nextVersion)
      }
      setNotice(values.length===1?'本题意见已保存到服务器':`全部${values.length}题意见已保存到服务器`)
    } finally {setSaving(false)}
  }
  function save(returned=false) {
    const value=returned?{...item,content:'changes_required' as const,issues:[{field:issueField,message:item.note}]}:item
    void saveItems([value],returned)
  }
  function toggle(field:typeof fields[number], ref:string, checked:boolean) {
    update({[field]:checked?[...(item[field]??[]).filter(row=>row.reference!==ref),{reference:ref,decision:'approved'}]:(item[field]??[]).filter(row=>row.reference!==ref)})
  }
  const readable:Record<string,string> = {}
  for (const skill of question.skills) {readable[skill._src_id]=`${skill.role === 'PRIMARY' ? '主要技能' : '辅助技能'} ${skill.skill_code} · ${skillName(skill)}`;for(const ev of skill.evidence) readable[ev.relation_src_id]=`技能证据：${ev.evidence_text}`}
  for(const ev of question.answer_evidence) readable[ev.relation_src_id]=`答案证据：${ev.evidence_text}`
  for(const option of question.options) for(const cause of option.error_causes) {readable[cause.relation_src_id]=`${option.display_letter} 选项错因 ${cause.code}`;for(const ev of cause.evidence) readable[ev.relation_src_id]=`错因证据：${ev.evidence_text}`}
  for(const option of question.options) if(option.assessment) readable[option.assessment._src_id]=`${option.display_letter} 干扰项比较、候选及无候选理由`
  for(const change of question.candidate_changes??[]) readable[change.reference]='候选删改及材料依据已逐项核对'
  return <Card title={`第${question.question_no}题审核意见`}>
    <Space orientation="vertical" size={16} style={{width:'100%'}}>
      {notice && <Alert type="info" title={notice} />}{error && <Alert type="error" title={error} />}
      <section aria-label="整套批量审核" className="processing-review-bulk"><Space orientation="vertical" size={10} style={{width:'100%'}}>
        <Typography.Text strong>批量处理全部{questions.length}题</Typography.Text>
        <Space wrap><Checkbox disabled={disabled} checked={allSelected} indeterminate={selectedCount>0&&!allSelected}
          onChange={event=>selectAll(event.target.checked)}>全选全部题目</Checkbox>
          <Typography.Text type="secondary">已完整勾选 {selectedCount} / {questions.length} 题</Typography.Text></Space>
        <Typography.Text type="secondary">同时勾选内容、技能、答案与错因证据，保留原意见及退回问题；可逐题调整。</Typography.Text>
        <label htmlFor="bulk-review-note">建议审核意见（可修改）</label>
        <Input.TextArea id="bulk-review-note" disabled={disabled} value={bulkNote} maxLength={2000} autoSize={{minRows:3,maxRows:6}}
          onChange={event=>{setBulkNote(event.target.value);persist(unsaved,version,{bulkNote:event.target.value})}} />
        <Space wrap><Button disabled={disabled||!bulkNote.trim()} onClick={()=>applyNote(false)}>一键填入全部题目</Button>
          <Button disabled={disabled||!bulkNote.trim()} onClick={()=>applyNote(true)}>只填空白意见</Button></Space>
        <Typography.Text type="secondary">也会填入下方整套审核依据。请核对建议内容后使用；填入全部会替换原意见。</Typography.Text>
        <Button type="primary" disabled={disabled||!Object.keys(unsaved).length} onClick={()=>void saveItems(questions.map(q=>drafts[q.question_src_id]??blank(q)))}>保存全部题目意见</Button>
      </Space></section>
      <Radio.Group disabled={disabled} aria-label="题干选项和来源答案解析审核" value={item.content} onChange={event=>update({content:event.target.value as ReviewItem['content']})}>
        <Radio value="approved">题干、选项、来源答案与解析通过</Radio><Radio value="changes_required">内容待核对 / 需修改</Radio></Radio.Group>
      {fields.map(field=><div key={field}>
        {(question.review_requirements[field]??[]).map(ref=><div key={ref}><Checkbox disabled={disabled} checked={(item[field]??[]).some(row=>row.reference===ref&&row.decision==='approved')}
          onChange={event=>toggle(field,ref,event.target.checked)}>{readable[ref]??ref}</Checkbox></div>)}
      </div>)}
      {question.assessment_summary&&<Typography.Text>干扰项已勾选审核 {(item.distractor_assessments??[]).filter(row=>row.decision==='approved').length} / 3；结论完整 {question.assessment_summary.resolved} / 3</Typography.Text>}
      {question.generation_state==='generated_empty'&&<Checkbox disabled={disabled} checked={item.empty_errors_confirmed} onChange={event=>update({empty_errors_confirmed:event.target.checked})}>确认本题无有依据的错因标注</Checkbox>}
      <label htmlFor="review-note">审核意见 / 退回原因</label><Input.TextArea disabled={disabled} id="review-note" value={item.note} rows={3} maxLength={4000} onChange={event=>update({note:event.target.value})} />
      <Space wrap><Button disabled={disabled} onClick={()=>save()}>保存本题意见</Button>
        <Select disabled={disabled} aria-label="退回问题定位" value={issueField} onChange={setIssueField} options={[{value:'question',label:'题干/选项/答案'},{value:'source',label:'来源识别'},{value:'alignment',label:'音频对齐'},{value:'annotation',label:'技能/错因/证据'}]} />
        <Button danger disabled={disabled} onClick={()=>save(true)}>保存退回问题</Button></Space>
      <Typography.Text type="secondary">保存意见不会修改内容或调用模型。任一内容修订后，新版本全部题目重新审核。</Typography.Text>
      <Typography.Title level={5}>提交整套审核</Typography.Title>
      <Checkbox disabled={disabled} checked={audio} onChange={event=>{setAudio(event.target.checked);persist(unsaved,version,{audio:event.target.checked})}}>已完成当前最终版本的原音核听确认</Checkbox>
      <Input disabled={disabled} aria-label="整套审核实际依据" value={reference} maxLength={2000} onChange={event=>{setReference(event.target.value);persist(unsaved,version,{reference:event.target.value})}} placeholder="填写本次最终审核、核听的实际依据或记录" />
      <Button type="primary" disabled={disabled||!allSelected||!conclusionsComplete||Object.keys(unsaved).length>0||!audio||!reference.trim()} onClick={()=>void command('review_submit',`${root}/submit`,{
        expected_result_hash:workflow.result_hash,expected_session_version:version,audio_confirmed:audio,approval_reference:reference})}>提交整套审核</Button>
    </Space>
  </Card>
}
