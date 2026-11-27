import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Descriptions, Empty, Input, Modal, Select, Space, Spin, Tag, Typography } from 'antd'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useAuth } from '../../../auth/useAuth'
import { request } from '../../../api/client'
import { binary, getCapabilities, getQuestions, getWorkflow, putMaterial, readPending, sendOperation, WORKFLOWS } from '../../../api/processing'
import { paperName, label as stateLabel, needsSourceCheck, workflowState } from '../../../api/processing-adapters'
import type { Capabilities, Evidence, Operation, QuestionView, WorkflowDetail, WorkflowMaterial } from '../../../api/processing-types'
import PendingOperationPanel from './PendingOperationPanel'
import QuestionContent from './QuestionContent'
import ReviewPanel from './ReviewPanel'
import StageApprovalPanel from './StageApprovalPanel'
import ReprocessPanel from './ReprocessPanel'
import ProcessingProgress from './ProcessingProgress'
import './processing.css'

export default function ProcessingDetailPage() {
  const {workflowId = ''} = useParams(); const {user} = useAuth(); const owner = user?.userId ?? 0
  const [search,setSearch] = useSearchParams(); const [workflow,setWorkflow] = useState<WorkflowDetail | null>(null)
  const [capabilities,setCapabilities] = useState<Capabilities | null>(null); const [questions,setQuestions] = useState<QuestionView[]>([])
  const [operations,setOperations] = useState<Operation[]>([]); const [busy,setBusy] = useState(false); const [dirty,setDirty] = useState(false)
  const [uploading,setUploading] = useState(false)
  const [error,setError] = useState(''); const [notice,setNotice] = useState(''); const [reload,setReload] = useState(0)
  const [revisionOpen,setRevisionOpen] = useState(false); const [reason,setReason] = useState('')
  const [media,setMedia] = useState<{url:string;audio:boolean;label:string}|null>(null)
  const mediaUrl = useRef<string|null>(null); const mediaController = useRef<AbortController|null>(null)
  const refresh = useCallback(()=>setReload(value=>value+1),[])
  const dirtyChanged = useCallback((value:boolean)=>setDirty(value),[])
  useEffect(()=>{const controller=new AbortController();void getCapabilities().then(setCapabilities).catch(()=>{});return()=>controller.abort()},[])
  useEffect(()=>{
    const controller=new AbortController(); let timer:ReturnType<typeof setTimeout>
    async function load() {
      try {const current=await getWorkflow(workflowId,controller.signal);if(controller.signal.aborted)return;setWorkflow(current)
        const history=await request<{items:Operation[]}>({url:`${WORKFLOWS}/${workflowId}/operations`,signal:controller.signal});setOperations(history.items)
      } catch(cause){if(!controller.signal.aborted)setError(cause instanceof Error?cause.message:'任务读取失败')}
      if(!controller.signal.aborted)timer=setTimeout(()=>void load(),5000)
    }
    void load();return()=>{controller.abort();clearTimeout(timer)}
  },[workflowId,reload])
  const contentKey=workflow ? `${workflow.revision_id}:${workflow.result_hash ?? JSON.stringify(workflow.stages)}` : ''
  useEffect(()=>{if(!workflow)return;const controller=new AbortController()
    setQuestions([])
    if(!Object.keys(workflow.stages).some(stage=>['source','sample','final'].includes(stage))){setQuestions([]);return}
    void getQuestions(workflow.workflow_id,workflow.revision_id,controller.signal).then(data=>setQuestions(data.items)).catch(cause=>{if(!controller.signal.aborted)setError(cause instanceof Error?cause.message:'题目读取失败')})
    return()=>controller.abort()
    // Stage identities are immutable; polling progress must not reload review content.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[workflowId,contentKey])
  useEffect(()=>{const before=(event:BeforeUnloadEvent)=>{if(dirty){event.preventDefault();event.returnValue=''}};window.addEventListener('beforeunload',before);return()=>window.removeEventListener('beforeunload',before)},[dirty])
  useEffect(()=>()=>{mediaController.current?.abort();if(mediaUrl.current)URL.revokeObjectURL(mediaUrl.current)},[])
  async function command(action:string,path:string,body:Record<string,unknown>,method:'POST'|'PATCH'='POST') {
    if(!workflow||busy||readPending(owner,workflowId))return null
    setBusy(true);setError('');setNotice('')
    try {const result=await sendOperation(owner,workflowId,{action,url:`${WORKFLOWS}/${workflowId}/${path}`,method,key:crypto.randomUUID(),
      body:{expected_workflow_version:workflow.row_version,expected_revision_id:workflow.revision_id,...body}})
      setNotice('操作已受理，状态以服务器记录为准');refresh();return result
    } catch(cause){setError(cause instanceof Error?cause.message:'操作失败，请查询原操作');return null} finally{setBusy(false)}
  }
  async function upload(material:WorkflowMaterial,file:File) {
    if(!workflow)return
    if(capabilities&&file.size>capabilities.max_upload_bytes){setError('文件超过上传上限');return}
    const operation=await command('reserve_upload','material-uploads',{kind:material.kind,filename:file.name,declared_size:file.size,expected_upload_version:material.upload_version})
    if(!operation)return
    setUploading(true)
    try {await putMaterial(workflowId,workflow.revision_id,material.kind,String(operation.result.upload_id),Number(operation.result.upload_version),file);setNotice('文件已上传并通过内容校验')}
    catch(cause){setError(cause instanceof Error?cause.message:'上传中断，请读取当前文件状态后重新选择文件')}
    finally{setUploading(false);refresh()}
  }
  async function openMedia(path:string,audio:boolean,label:string) {
    mediaController.current?.abort();const controller=new AbortController();mediaController.current=controller
    try {const blob=await binary(path,controller.signal);if(controller.signal.aborted)return
      if(mediaUrl.current)URL.revokeObjectURL(mediaUrl.current);mediaUrl.current=URL.createObjectURL(blob);setMedia({url:mediaUrl.current,audio,label})
    } catch(cause){if(!controller.signal.aborted)setError(cause instanceof Error?cause.message:'媒体读取失败')}
  }
  function play(evidence:Evidence) {if(workflow)void openMedia(`${WORKFLOWS}/${workflowId}/revisions/${workflow.revision_id}/evidences/${encodeURIComponent(evidence._src_id)}/audio`,true,'证据原音')}
  function retryFailed(){if(!failed||!workflow)return
    if(failed.result.stage==='publish')void command('publish','publish',{expected_result_hash:workflow.result_hash,
      review_session_id:workflow.review_session_id,expected_current_batch_id:workflow.current_batch_id,retry_of_operation_id:failed.operation_id})
    else void command('retry','retries',{reason:'管理员显式重试失败操作',retry_of_operation_id:failed.operation_id})
  }
  if(!workflow)return error?<Alert type="error" title={error} action={<Button onClick={refresh}>重试</Button>}/>:<Spin aria-label="正在读取任务"/>
  const question=questions.find(item=>String(item.question_no)===search.get('question'))??questions[0]
  const canUpload=!uploading&&workflow.allowed_actions.find(action=>action.action==='reserve_upload')?.enabled
  const waitingStage=({awaiting_alignment:'align',awaiting_source:'source',awaiting_sample:'sample'} as Record<string,string>)[workflow.processing_state]
  const failed=operations.find(operation=>['failed','conflict','stopped'].includes(operation.state)&&operation.revision_id===workflow.revision_id)
  const retryState=failed?.result.stage==='publish'?workflow.publication_state:workflow.processing_state
  const canRetry=Boolean(failed)&&['failed','conflict','stopped'].includes(retryState)
  const sourceCheck=needsSourceCheck(workflow)
  return <Space orientation="vertical" size={20} style={{width:'100%'}}>
    <Space wrap><Link to="/admin/listening-papers/processing">返回处理任务</Link><Link to="/admin/listening-papers">正式题库</Link>
      {workflow.exam_paper_id&&workflow.current_batch_id&&<Link to={`/admin/listening-papers/${workflow.exam_paper_id}`}>查看正式详情</Link>}</Space>
    <Space wrap><Typography.Title level={4} style={{margin:0}}>{paperName(workflow)}</Typography.Title><Tag color={sourceCheck?'warning':undefined}>{stateLabel(workflowState(workflow))}</Tag>
      <Button onClick={refresh}>刷新</Button></Space>
    {workflow.workflow_contract==='library.v1'&&<Space wrap><Tag>整套标注流程</Tag><Link to={`/admin/listening-papers/processing/${workflowId}/edit`}>编辑、版本与候选采纳</Link></Space>}
    <PendingOperationPanel owner={owner} target={workflowId} onChange={refresh} onRecovered={()=>refresh()} />
    {error&&<Alert type="error" showIcon title={error} closable onClose={()=>setError('')}/>}{notice&&<Alert type="success" title={notice}/>}
    <Card><ProcessingProgress workflow={workflow}/><Descriptions column={3} size="small" items={[
      {key:'content',label:'内容审核',children:stateLabel(workflow.content_review_state)},{key:'errors',label:'错因审核',children:stateLabel(workflow.error_review_state)},
      {key:'publish',label:'本次结果入库',children:stateLabel(workflow.publication_state)},{key:'visible',label:'当前正式卷学生可见',children:workflow.is_student_visible?'已开放':'未开放'},
      {key:'cost',label:'本任务费用账本',children:`已知 $${workflow.usage.known_usd} / 预留 $${workflow.usage.reserved_usd}${workflow.usage.has_unknown_charges?'（有未确认计费）':''}`},
    ]}/><Space wrap style={{marginTop:16}}>
      <Button type="primary" disabled={busy||!workflow.allowed_actions.find(action=>action.action==='start')?.enabled} onClick={()=>void command('start','start',{reason:'管理员显式开始处理'})}>开始处理</Button>
      <Button danger disabled={busy||!operations.some(operation=>['running','accepted'].includes(operation.state))} onClick={()=>void command('stop','stop',{reason:'管理员显式停止处理'})}>停止处理</Button>
      <Button disabled={busy||!canRetry} onClick={retryFailed}>{sourceCheck?'重新识别来源':'重试失败阶段'}</Button>
      <Button disabled={busy||dirty||operations.some(operation=>['running','accepted'].includes(operation.state))} onClick={()=>setRevisionOpen(true)}>创建材料子修订</Button>
      <Button disabled={busy||dirty||workflow.content_review_state!=='approved'||workflow.error_review_state!=='approved'||workflow.publication_state==='published'} onClick={()=>void command('publish','publish',{
        expected_result_hash:workflow.result_hash,review_session_id:workflow.review_session_id,expected_current_batch_id:workflow.current_batch_id})}>正式入库并激活</Button>
    </Space></Card>
    {capabilities&&!capabilities.processing_ready&&<Alert type="warning" title={capabilities.blocked_reason??'处理环境尚未就绪'}/>}
    {workflow.issues.filter(issue=>!sourceCheck||issue.code!=='PROCESSING_FAILED').map((issue,index)=><Alert key={`${issue.code}:${index}`} type={sourceCheck?'warning':'error'}
      title={sourceCheck?`来源识别待核对：${issue.message}`:`${issue.code}：${issue.message}`}
      description={sourceCheck?'保留原件和已完成步骤。可核对原页及识别结果，再重新识别来源；完整确认后才能继续标注。':undefined}/>)}
    <Card title="当前修订原件"><div className="processing-materials">{workflow.materials.map(material=><div className="processing-material" key={material.kind}>
      <Typography.Text strong>{({paper:'原卷 PDF',answer:'答案解析 PDF',audio:'原始音频'})[material.kind]}</Typography.Text><Tag>{stateLabel(material.state)}</Tag>
      <Typography.Paragraph ellipsis={{rows:2}}>{material.filename??'尚未选择文件'}</Typography.Paragraph>
      {material.failure_code&&<Typography.Paragraph type="danger">{material.failure_code}</Typography.Paragraph>}
      <Space wrap>{material.material_id&&<Button size="small" onClick={()=>void openMedia(`${WORKFLOWS}/${workflowId}/materials/${material.material_id}`,material.kind==='audio',material.filename??'原件')}>查看 / 试听</Button>}
        <label className={`processing-file ${!canUpload||busy?'processing-file-disabled':''}`}><span>{material.state==='ready'?'重新选择':'选择文件'}</span>
          <input type="file" aria-label={`上传${({paper:'原卷',answer:'答案解析',audio:'原音'})[material.kind]}`} accept={material.kind==='audio'?'.m4a,.mp3,.wav,.flac,.ogg':'.pdf'} disabled={!canUpload||busy} onChange={event=>{const file=event.target.files?.[0];event.target.value='';if(file)void upload(material,file)}}/></label>
        {material.upload_id&&['reserved','uploading','validating'].includes(material.state)&&<Button size="small" disabled={busy} onClick={()=>void command('cancel_upload',`material-uploads/${material.upload_id}/cancel`,{expected_upload_version:material.upload_version,reason:'管理员取消当前上传'})}>取消上传</Button>}
      </Space></div>)}</div><Typography.Paragraph type="secondary" style={{marginBottom:0,marginTop:16}}>处理开始后原件冻结。页面关闭不影响独立处理；上传中断后可重新选择文件。新材料需创建子修订。</Typography.Paragraph></Card>
    {media&&<Card title={media.label} extra={<Button onClick={()=>{setMedia(null);if(mediaUrl.current){URL.revokeObjectURL(mediaUrl.current);mediaUrl.current=null}}}>关闭预览</Button>}>
      {media.audio?<audio key={media.url} src={media.url} controls preload="metadata" style={{width:'100%'}}/>:<iframe title={media.label} src={media.url} style={{width:'100%',height:500,border:0}}/>}</Card>}
    {waitingStage&&workflow.stages[waitingStage]&&<StageApprovalPanel key={`${workflow.revision_id}:${waitingStage}`} workflow={workflow} stage={waitingStage} busy={busy} command={command}/>}
    {workflow.workflow_contract!=='library.v1'&&(workflow.reprocess_result_hash||workflow.result_hash||workflow.sample_result_hash)&&<ReprocessPanel key={workflow.revision_id} workflow={workflow} questions={questions} busy={busy||dirty} command={command}/>}
    {workflow.error_generation_summary&&<Typography.Text>本阶段干扰项检查 {workflow.error_generation_summary.assessed} / {workflow.error_generation_summary.expected} · 结论完整 {workflow.error_generation_summary.resolved} / {workflow.error_generation_summary.expected} · 已勾选审核 {workflow.error_generation_summary.reviewed} / {workflow.error_generation_summary.expected}</Typography.Text>}
    {question?<div className="processing-review-grid"><Card title="题目与标注（只读）" extra={<Select aria-label="跳转题目" value={question.question_no} options={questions.map(item=>({value:item.question_no,label:`第 ${item.question_no} 题`}))} onChange={value=>{const next=new URLSearchParams(search);next.set('question',String(value));setSearch(next,{replace:true})}}/>}>
      <QuestionContent question={question} play={play}/></Card>
      {workflow.review_session_id?<ReviewPanel key={`${workflow.review_session_id}:${workflow.result_hash}`} owner={owner} workflow={workflow} question={question} questions={questions} busy={busy} dirtyChanged={dirtyChanged} command={command}/>:<Card><Empty description="当前阶段尚未生成最终逐题审核会话"/></Card>}</div>:<Card><Empty description="来源处理完成后显示题目与标注"/></Card>}
    <Modal title="创建材料子修订" open={revisionOpen} okText="创建新修订" cancelText="取消" confirmLoading={busy} onCancel={()=>setRevisionOpen(false)} onOk={()=>{if(reason.trim())void command('create_revision','revisions',{reason,document_mode:workflow.document_mode,listening_pages:workflow.listening_pages}).then(result=>{if(result){setRevisionOpen(false);setReason('')}})}}>
      <Typography.Paragraph>保留已验证原件引用，后续可替换材料。新修订会清空当前阶段结论，并在新最终结果生成后整套重新审核。</Typography.Paragraph>
      <Input.TextArea aria-label="材料修订原因" placeholder="填写实际修订原因" value={reason} maxLength={2000} onChange={event=>setReason(event.target.value)}/></Modal>
  </Space>
}
