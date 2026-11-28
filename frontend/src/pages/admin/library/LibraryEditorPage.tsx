import { useCallback, useContext, useEffect, useRef, useState } from 'react'
import { Alert, Button, Collapse, Descriptions, Empty, Input, Modal, Select, Space, Spin, Table, Tabs, Typography } from 'antd'
import { Link, useParams, UNSAFE_NavigationContext } from 'react-router-dom'
import { request } from '../../../api/client'
import { useAuth } from '../../../auth/useAuth'
import { getCandidates, getDraft, getVersions, previewDraft, text, workflowUrl, type LibraryCandidate, type LibraryDraft, type LibraryVersion, type Preview, type Snapshot } from '../../../api/library'
import { readPending, sendOperation } from '../../../api/processing'
import PendingOperationPanel from '../processing/PendingOperationPanel'
import ManualAnnotationEditor from './ManualAnnotationEditor'
import ContentEditor from './ContentEditor'
import ModelProviderPanel from './ModelProviderPanel'
import './library.css'

const sectionNames:Record<string,string>={content_groups:'内容组',passages:'篇章',transcript_segments:'原文句子',questions:'题目',presentations:'展示映射',evidences:'证据',skill_question_relations:'技能及证据',error_question_relations:'错因及证据',other_relations:'答案证据',distractor_assessments:'三项评估',language_items:'语言项目'}
const protectionNames:Record<string,string>={latest:'最新版本',previous:'上一版本',formal_batch:'正式批次保护',review:'审核引用保护',active_operation:'活动任务保护',candidate_source:'候选来源保护',restore:'回退来源保护'}
export default function LibraryEditorPage() {
  const {navigator}=useContext(UNSAFE_NavigationContext)
  const {workflowId = ''} = useParams(), {user} = useAuth(), owner = user?.userId ?? 0
  const [draft, setDraft] = useState<LibraryDraft | null>(null), [snapshot, setSnapshot] = useState<Snapshot>({})
  const [versions, setVersions] = useState<LibraryVersion[]>([]), [candidates, setCandidates] = useState<LibraryCandidate[]>([])
  const [dirty, setDirty] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const [reason, setReason] = useState(''), [preview, setPreview] = useState<Preview | null>(null), [action, setAction] = useState<'save' | 'restore' | 'adopt' | 'source' | null>(null)
  const [selectedCandidates, setSelectedCandidates] = useState<string[]>([]), [scopes, setScopes] = useState<string[]>(['skills', 'answer_evidence', 'errors:A', 'errors:B', 'errors:C', 'errors:D'])
  const [questionId,setQuestionId] = useState(''), [restoreSections,setRestoreSections] = useState<string[]>([])
  const [generationQuestions,setGenerationQuestions]=useState<string[]>([]), [provider,setProvider]=useState('deepseek')
  const [providerReady,setProviderReady]=useState(false)
  async function prepare(stage:'source'|'final') {
    if(!draft||dirty||busy)return;setBusy(true);setError('')
    try {await sendOperation(owner,workflowId,{action:stage==='source'?'library_prepare_source':'library_prepare_review',url:`${workflowUrl(workflowId)}/prepare-${stage}-review`,method:'POST',key:crypto.randomUUID(),body:{expected_row_version:draft.row_version,expected_content_hash:draft.content_hash,reason:stage==='source'?'管理员提交当前保存内容进入来源核听审核':'管理员提交当前保存版本进入整套最终审核'}});setNotice('已提交。请进入“材料、审核与发布”继续实际审核。');await load()}
    catch(cause){setError(cause instanceof Error?cause.message:'提交审核失败')}finally{setBusy(false)}
  }
  async function generate() {
    if(!draft||dirty||busy||!providerReady||!generationQuestions.length||!reason.trim())return;setBusy(true);setError('')
    try {await sendOperation(owner,workflowId,{action:'library_generate',url:`${workflowUrl(workflowId)}/candidate-generations`,method:'POST',key:crypto.randomUUID(),body:{expected_row_version:draft.row_version,expected_content_hash:draft.content_hash,reason,provider,question_src_ids:generationQuestions}});setNotice('所选题目候选生成已排队，保留当前人工结果和审核。可在处理页查询进度。')}
    catch(cause){setError(cause instanceof Error?cause.message:'候选生成未受理')}finally{setBusy(false)}
  }
  const pendingBody = useRef<Record<string, unknown> | null>(null)
  const load = useCallback(async () => {
    const [current, history, generated] = await Promise.all([getDraft(workflowId), getVersions(workflowId), getCandidates(workflowId)])
    setDraft(current); setSnapshot(structuredClone(current.snapshot)); setVersions(history.items); setCandidates(generated.items); setDirty(false)
  }, [workflowId])
  useEffect(() => {void load().catch(cause => setError(cause instanceof Error ? cause.message : '草稿读取失败'))}, [load])
  useEffect(() => {
    const before = (event: BeforeUnloadEvent) => {if (dirty) {event.preventDefault(); event.returnValue = ''}}
    const push=navigator.push, replace=navigator.replace, go=navigator.go
    const allowed=()=>!dirty||window.confirm('有未保存的内容，确认离开并放弃这些修改？')
    navigator.push=(...args)=>{if(allowed())push.apply(navigator,args)}
    navigator.replace=(...args)=>{if(allowed())replace.apply(navigator,args)}
    navigator.go=(delta)=>{if(allowed())go.call(navigator,delta)}
    window.addEventListener('beforeunload', before)
    return () => {window.removeEventListener('beforeunload', before);navigator.push=push;navigator.replace=replace;navigator.go=go}
  }, [dirty,navigator])
  const preconditions = draft ? {expected_row_version: draft.row_version, expected_content_hash: draft.content_hash} : {}
  async function showPreview(kind: 'save' | 'restore' | 'adopt' | 'source', version?: LibraryVersion) {
    if (!draft || busy) return
    setBusy(true); setError('')
    try {
      const body: Record<string, unknown> = {...preconditions, reason: reason.trim() || '预览变更'}
      let result: Preview
      if (kind === 'save') {body.snapshot = snapshot; result = await previewDraft(workflowId, body)}
      else if (kind === 'restore') {if (!version) return; Object.assign(body, {source_version_id: version.id, sections: restoreSections, question_src_ids: []}); result = await request<Preview>({url: `${workflowUrl(workflowId)}/restore-preview`, method: 'POST', data: body})}
      else if(kind==='source') {result=await request<Preview>({url:`${workflowUrl(workflowId)}/source-adoption-preview`,method:'POST',data:body})}
      else {Object.assign(body, {candidate_ids: selectedCandidates, scopes}); result = await request<Preview>({url: `${workflowUrl(workflowId)}/candidate-adoption-preview`, method: 'POST', data: body})}
      pendingBody.current = body; setPreview(result); setAction(kind)
    } catch (cause) {setError(cause instanceof Error ? cause.message : '变更预览失败')} finally {setBusy(false)}
  }
  async function execute() {
    if (!action || !pendingBody.current || !reason.trim() || readPending(owner, workflowId)) return
    const config = {save: {action: 'library_save', path: 'edit-draft', method: 'PUT' as const}, restore: {action: 'library_restore', path: 'restores', method: 'POST' as const}, adopt: {action: 'library_adopt', path: 'candidate-adoptions', method: 'POST' as const},source:{action:'library_source_adopt',path:'source-adoptions',method:'POST' as const}}[action]
    setBusy(true); setError('')
    try {await sendOperation(owner, workflowId, {action: config.action, url: `${workflowUrl(workflowId)}/${config.path}`, method: config.method, key: crypto.randomUUID(), body: {...pendingBody.current, reason: reason.trim()}})
      setAction(null); setPreview(null); setReason(''); await load(); setNotice('保存成功。正式批次未切换，变更须重新整套审核。')
    } catch (cause) {setError(cause instanceof Error ? cause.message : '保存未确认，请查询原操作；本地内容已保留')} finally {setBusy(false)}
  }
  if (!draft) return error ? <Alert type="error" title={error} action={<Button onClick={() => void load().catch(cause => setError(String(cause)))}>重试</Button>} /> : <Spin aria-label="读取编辑草稿" />
  const question = snapshot.questions.find(q=>q._src_id===questionId)??snapshot.questions[0]
  return <Space orientation="vertical" size={20} className="library-editor">
    <div className="page-header"><div><Typography.Title level={4} style={{margin: 0}}>试卷编辑 · {draft.version_no ? `V${draft.version_no}` : '首次保存前'}</Typography.Title><Typography.Text type="secondary">{dirty ? '有未保存修改' : '当前内容已与服务器同步'} · {snapshot.questions.length} / 25 题</Typography.Text></div>
      <Space wrap><Link to="/admin/listening-papers">返回题库</Link><Link to={`/admin/listening-papers/processing/${workflowId}`}>材料、审核与发布</Link><Button disabled={!dirty || busy || draft.archived} type="primary" onClick={() => void showPreview('save')}>预览并保存</Button></Space></div>
    <PendingOperationPanel owner={owner} target={workflowId} onChange={() => setBusy(false)} onRecovered={() => {setAction(null); void load().catch(cause => setError(String(cause)))}} />
    {error && <Alert type="error" title={error} description="并发冲突时本地修改保持不变。请查看最新版本差异，再决定如何合并。" action={<Button onClick={() => void getVersions(workflowId).then(value => setVersions(value.items))}>刷新版本记录</Button>} />}
    {notice && <Alert type="success" title={notice} closable onClose={() => setNotice('')} />}
    {draft.archived && <Alert type="warning" title="试卷已归档，当前草稿只读" />}
    {draft.issues.length > 0 && <Collapse items={[{key: 'issues', label: `${draft.issues.length} 项待补齐或复核，不能送审`, children: <ul>{draft.issues.map((issue, index) => <li key={`${issue.issue_code}-${index}`}>{issue.message}{issue.src_id ? ` · ${issue.src_id}` : ''}</li>)}</ul>}]} />}
    <Space wrap><Button disabled={dirty||busy||draft.archived} onClick={()=>void showPreview('source')}>预览采用最新组装来源</Button><Button disabled={dirty||busy||!draft.save_version_id||draft.archived} onClick={()=>void prepare('source')}>提交来源与核听审核</Button><Button disabled={dirty||busy||!draft.save_version_id||Boolean(draft.issues.length)||draft.archived} onClick={()=>void prepare('final')}>送整套最终审核</Button></Space>
    <Tabs items={[
      {key:'content',label:'内容编辑',children:<ContentEditor snapshot={snapshot} materials={draft.source_materials} onChange={value=>{setSnapshot(value);setDirty(true);setPreview(null)}} disabled={busy||draft.archived}/>},
      {key:'annotations',label:'技能、错因与证据',children:<Space orientation="vertical" style={{width:'100%'}}><Select aria-label="选择标注题目" style={{width:'100%'}} value={question?._src_id} onChange={setQuestionId} options={snapshot.questions.map((q,i)=>({value:q._src_id,label:`第${String(q.question_index??i+1)}题 ${text(q,'question_text')}`}))}/>{question?<ManualAnnotationEditor key={`${question._src_id}:${draft.row_version}`} workflowId={workflowId} owner={owner} draft={draft} snapshot={snapshot} question={question} disabled={busy||dirty||draft.archived} onSaved={()=>void load().catch(cause=>setError(String(cause)))}/>:<Empty description="请先保存题目和有效正文句子"/>}{dirty&&<Alert type="info" title="请先保存内容，再编辑标注"/>}</Space>},
      {key:'versions',label:'版本记录与回退',children:<><Typography.Paragraph type="secondary">最新与上一版本长期保护。更早版本从退出保护时起至少保留七天；清理后保留摘要。</Typography.Paragraph><Select mode="multiple" aria-label="局部回退范围" placeholder="留空恢复完整版本；可选择局部范围" style={{width:'100%',marginBottom:12}} value={restoreSections} onChange={setRestoreSections} options={Object.keys(snapshot).map(value=>({value,label:sectionNames[value]??value}))}/><Table<LibraryVersion> rowKey="id" dataSource={versions} pagination={false} columns={[{title:'版本',render:(_,v)=>`V${v.version_no}`},{title:'时间',render:(_,v)=>new Date(v.saved_at).toLocaleString('zh-CN')},{title:'原因 / 来源',render:(_,v)=><span>{v.reason} · {({MANUAL:'人工',AI:'模型',MIXED:'混合'} as Record<string,string>)[v.origin_type]??v.origin_type}</span>},{title:'恢复与保护',render:(_,v)=>v.protection_reasons.length?v.protection_reasons.map(reason=>protectionNames[reason.split(':')[0]]??'业务引用保护').join('、'):v.can_restore?`保留至 ${v.eligible_after?new Date(v.eligible_after).toLocaleString('zh-CN'):'待计时'}`:'快照已清理'},{title:'操作',render:(_,v)=><Space><Button disabled={!v.can_restore||dirty||busy} onClick={()=>void showPreview('restore',v)}>预览回退</Button><Button disabled={!v.can_restore} onClick={()=>void request<Preview>({url:`${workflowUrl(workflowId)}/versions/${v.id}/diff`}).then(value=>{setPreview(value);setAction(null)}).catch(cause=>setError(String(cause)))}>差异</Button></Space>}]} /></>},
      {key:'candidates',label:`模型候选 (${candidates.length})`,children:<Space orientation="vertical" style={{width:'100%'}}><Typography.Paragraph type="secondary">生成候选保留当前人工结果。选择范围并预览后采纳，才形成保存版本。</Typography.Paragraph><ModelProviderPanel value={provider} onChange={setProvider} onReadyChange={setProviderReady} disabled={busy}/><Space wrap><Button onClick={()=>{void getCandidates(workflowId).then(data=>setCandidates(data.items)).catch(cause=>setError(String(cause)))}}>刷新候选</Button></Space><Select aria-label="生成或重试的题目范围" mode="multiple" placeholder="显式选择要生成或重试的题目" style={{width:'100%'}} value={generationQuestions} onChange={setGenerationQuestions} options={snapshot.questions.map((q,i)=>({value:q._src_id,label:`第${String(q.question_index??i+1)}题`}))}/><Input aria-label="候选生成原因" placeholder="填写生成或重试原因" value={reason} onChange={event=>setReason(event.target.value)} maxLength={2000}/><Button disabled={dirty||busy||!providerReady||draft.archived||!generationQuestions.length||!reason.trim()} onClick={()=>void generate()}>生成所选题目候选</Button><Select mode="multiple" aria-label="采纳范围" style={{width:'100%'}} value={scopes} onChange={setScopes} options={[{value:'skills',label:'技能及证据'},{value:'answer_evidence',label:'答案证据'},...'ABCD'.split('').map(letter=>({value:`errors:${letter}`,label:`基准${letter}错因、评估及证据`}))]}/><Table<LibraryCandidate> rowKey="id" dataSource={candidates} pagination={false} rowSelection={{selectedRowKeys:selectedCandidates,onChange:keys=>setSelectedCandidates(keys.map(String)),getCheckboxProps:record=>({disabled:record.evaluation_only})}} columns={[{title:'题目',dataIndex:'question_src_id'},{title:'生成模型',render:(_,v)=><span>{v.evaluation_only&&<Typography.Text type="secondary">评测候选（只读）<br/></Typography.Text>}{v.provider==='bailian'?'千问':'DeepSeek'} · {v.requested_model}<br/><Typography.Text type="secondary">响应模型：{v.response_model??'未记录'}</Typography.Text></span>},{title:'生成时间',render:(_,v)=>new Date(v.created_at).toLocaleString('zh-CN')},{title:'方法',render:(_,v)=>v.method_hash.slice(0,16)},{title:'原始候选',render:(_,v)=><details><summary>展开</summary><pre className="library-json">{JSON.stringify(v.payload,null,2)}</pre></details>}]} /><Button disabled={dirty||busy||!selectedCandidates.length||!scopes.length} onClick={()=>void showPreview('adopt')}>预览选择采纳</Button></Space>},
    ]}/>
    {preview&&<div className="library-preview"><Typography.Title level={5}>变更预览</Typography.Title><Descriptions column={3} items={[{key:'f',label:'整套审核',children:preview.impact.final_review_invalidated?'重新审核':'保持'},{key:'s',label:'来源审核',children:preview.impact.source_review_invalidated?'重新核对':'可按依赖复用'},{key:'a',label:'对齐',children:preview.impact.alignment_required?'需要重做':'未要求重做'}]}/><Table rowKey={row=>`${row.section}:${row.src_id}`} dataSource={preview.changes} pagination={{pageSize:10}} columns={[{title:'对象',render:(_,row)=>sectionNames[row.section]??row.section},{title:'源身份',dataIndex:'src_id'},{title:'修改字段',render:(_,row)=>row.fields.join('、')},{title:'差异',render:(_,row)=><details><summary>前后值</summary><pre className="library-json">{JSON.stringify({before:row.before,after:row.after},null,2)}</pre></details>}]} /></div>}
    <Modal title={action==='restore'?'回退并追加版本':action==='adopt'?'采纳所选范围':action==='source'?'采用最新组装来源':'保存变更'} open={Boolean(action)} onCancel={()=>setAction(null)} onOk={()=>void execute()} confirmLoading={busy} okButtonProps={{disabled:!reason.trim()||Boolean(readPending(owner,workflowId))}} okText="确认保存"><Typography.Paragraph>已预览 {preview?.changes.length??0} 处变更。保存后须整套重新审核，正式批次保持当前版本。{action==='source'?'采用新来源会清除当前草稿的标注与证据，历史保存版本保留。':''}</Typography.Paragraph><Input.TextArea aria-label="修改原因" maxLength={2000} value={reason} onChange={event=>setReason(event.target.value)} placeholder="填写修改原因" /></Modal>
  </Space>
}
