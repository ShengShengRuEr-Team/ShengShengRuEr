import { useEffect, useState } from 'react'
import { Alert, Button, Card, Checkbox, Input, Radio, Select, Space, Typography } from 'antd'
import { request } from '../../../api/client'
import { WORKFLOWS } from '../../../api/processing'
import type { QuestionView, ReviewItem, WorkflowDetail } from '../../../api/processing-types'
import { skillName } from '../../../api/processing-adapters'

function blank(question: QuestionView): ReviewItem { return {question_src_id:question.question_src_id,content:'changes_required',primary_skills:[],answer_evidence:[],error_causes:[],empty_errors_confirmed:false,note:'',issues:[]} }
export default function ReviewPanel({owner, workflow, question, busy, dirtyChanged, command}: {
  owner:number; workflow:WorkflowDetail; question:QuestionView; busy:boolean; dirtyChanged:(dirty:boolean)=>void
  command:(action:string,path:string,body:Record<string,unknown>,method?:'POST'|'PATCH')=>Promise<{result:Record<string,unknown>}|null>
}) {
  const [drafts,setDrafts] = useState<Record<string,ReviewItem>>({}); const [version,setVersion] = useState(workflow.review_session_version ?? 1)
  const [unsaved,setUnsaved] = useState<Record<string,ReviewItem>>({})
  const [ready,setReady] = useState(false); const [error,setError] = useState(''); const [notice,setNotice] = useState('')
  const [audio,setAudio] = useState(false); const [reference,setReference] = useState(''); const [issueField,setIssueField] = useState('question')
  const key = `m3-review:${owner}:${workflow.workflow_id}:${workflow.revision_id}:${workflow.result_hash}`
  const root = `review-sessions/${workflow.review_session_id}`
  useEffect(() => {
    const controller = new AbortController()
    void request<{row_version:number;items:ReviewItem[]}>({url:`${WORKFLOWS}/${workflow.workflow_id}/${root}`,params:{limit:100},signal:controller.signal}).then(data => {
      const saved = Object.fromEntries(data.items.map(item => [item.question_src_id,item])); setVersion(data.row_version)
      try { const raw = localStorage.getItem(key); if (raw) { const local = JSON.parse(raw) as {version:number;drafts:Record<string,ReviewItem>}
        if (local.version === data.row_version) {Object.assign(saved,local.drafts);setUnsaved(local.drafts);setNotice('已恢复同版本的本地未保存意见，请核对后显式保存');dirtyChanged(true)}
        else setNotice('本地旧意见与当前审核版本不符，已保留本地记录，未自动应用') }
      } catch {setNotice('本地意见记录无法读取，请以服务器已保存记录为准')}
      setDrafts(saved);setReady(true)
    }).catch(cause => {if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '审核读取失败')})
    return () => controller.abort()
  }, [key,workflow.workflow_id,root,dirtyChanged])
  const item = drafts[question.question_src_id] ?? blank(question)
  function update(value: Partial<ReviewItem>) {
    const next = {...drafts,[question.question_src_id]:{...item,...value}};setDrafts(next);dirtyChanged(true)
    const changes={...unsaved,[question.question_src_id]:next[question.question_src_id]};setUnsaved(changes)
    localStorage.setItem(key,JSON.stringify({version,drafts:changes}))
  }
  async function save(returned=false) {
    if (returned && !item.note.trim()) {setError('退回必须填写具体原因');return}
    const value = returned ? {...item,content:'changes_required',issues:[{field:issueField,message:item.note}]} : item
    const result = await command('review_save',`${root}/${returned ? 'returns' : 'items'}`,{
      expected_result_hash:workflow.result_hash,expected_session_version:version,items:[value]},returned?'POST':'PATCH')
    if (result) {const nextVersion=Number(result.result.session_version);setVersion(nextVersion);setDrafts(previous=>({...previous,[question.question_src_id]:value as ReviewItem}))
      const remaining={...unsaved};delete remaining[question.question_src_id];setUnsaved(remaining);dirtyChanged(Object.keys(remaining).length>0)
      if(Object.keys(remaining).length)localStorage.setItem(key,JSON.stringify({version:nextVersion,drafts:remaining}));else localStorage.removeItem(key)
      setNotice('本题意见已保存到服务器')}
  }
  function toggle(field:keyof Pick<ReviewItem,'primary_skills'|'answer_evidence'|'error_causes'>, ref:string, checked:boolean) {
    update({[field]:checked?[...item[field].filter(row=>row.reference!==ref),{reference:ref,decision:'approved'}]:item[field].filter(row=>row.reference!==ref)})
  }
  const readable:Record<string,string> = {}
  for (const skill of question.skills) {readable[skill._src_id]=`${skill.role === 'PRIMARY' ? '主要技能' : '辅助技能'} ${skill.skill_code} · ${skillName(skill)}`;for(const ev of skill.evidence) readable[ev.relation_src_id]=`技能证据：${ev.evidence_text}`}
  for(const ev of question.answer_evidence) readable[ev.relation_src_id]=`答案证据：${ev.evidence_text}`
  for(const option of question.options) for(const cause of option.error_causes) {readable[cause.relation_src_id]=`${option.display_letter} 选项错因 ${cause.code}`;for(const ev of cause.evidence) readable[ev.relation_src_id]=`错因证据：${ev.evidence_text}`}
  return <Card title={`第${question.question_no}题审核意见`}>
    <Space orientation="vertical" size={12} style={{width:'100%'}}>
      {notice && <Alert type="info" title={notice} />}{error && <Alert type="error" title={error} />}
      <Radio.Group disabled={workflow.content_review_state==='approved'} aria-label="题干选项和来源答案解析审核" value={item.content} onChange={event=>update({content:event.target.value as ReviewItem['content']})}>
        <Radio value="approved">题干、选项、来源答案与解析通过</Radio><Radio value="changes_required">内容待核对 / 需修改</Radio></Radio.Group>
      {(['primary_skills','answer_evidence','error_causes'] as const).map(field=><div key={field}>
        {question.review_requirements[field].map(ref=><div key={ref}><Checkbox disabled={workflow.content_review_state==='approved'} checked={item[field].some(row=>row.reference===ref&&row.decision==='approved')}
          onChange={event=>toggle(field,ref,event.target.checked)}>{readable[ref]??ref}</Checkbox></div>)}
      </div>)}
      {question.generation_state==='generated_empty'&&<Checkbox disabled={workflow.content_review_state==='approved'} checked={item.empty_errors_confirmed} onChange={event=>update({empty_errors_confirmed:event.target.checked})}>确认本题无有依据的错因标注</Checkbox>}
      <label htmlFor="review-note">审核意见 / 退回原因</label><Input.TextArea disabled={workflow.content_review_state==='approved'} id="review-note" value={item.note} rows={3} maxLength={4000} onChange={event=>update({note:event.target.value})} />
      <Space wrap><Button disabled={busy||!ready||workflow.content_review_state==='approved'} onClick={()=>void save()}>保存本题意见</Button>
        <Select aria-label="退回问题定位" value={issueField} onChange={setIssueField} options={[{value:'question',label:'题干/选项/答案'},{value:'source',label:'来源识别'},{value:'alignment',label:'音频对齐'},{value:'annotation',label:'技能/错因/证据'}]} />
        <Button danger disabled={busy||!ready||workflow.content_review_state==='approved'} onClick={()=>void save(true)}>保存退回问题</Button></Space>
      <Typography.Text type="secondary">保存意见不会修改内容或调用模型。任一内容修订后，新版本全部题目重新审核。</Typography.Text>
      <Typography.Title level={5}>提交整套审核</Typography.Title>
      <Checkbox checked={audio} onChange={event=>setAudio(event.target.checked)}>已完成当前最终版本的原音核听确认</Checkbox>
      <Input aria-label="整套审核实际依据" value={reference} onChange={event=>setReference(event.target.value)} placeholder="填写本次最终审核、核听的实际依据或记录" />
      <Button type="primary" disabled={busy||!ready||Object.keys(unsaved).length>0||!audio||!reference.trim()||workflow.content_review_state==='approved'} onClick={()=>void command('review_submit',`${root}/submit`,{
        expected_result_hash:workflow.result_hash,expected_session_version:version,audio_confirmed:audio,approval_reference:reference})}>提交整套审核</Button>
    </Space>
  </Card>
}
