import { useState } from 'react'
import { Alert, Button, Collapse, Input, Select, Space, Typography } from 'antd'
import { request } from '../../../api/client'
import { WORKFLOWS } from '../../../api/processing'
import type { QuestionView, WorkflowDetail } from '../../../api/processing-types'
interface Plan {plan_hash:string;sample_valid:boolean;generation_count:number;review_count:number;affected_question_ids:string[];reusable_question_ids:string[]}
export default function ReprocessPanel({workflow,questions,busy,command}:{workflow:WorkflowDetail;questions:QuestionView[];busy:boolean;
  command:(action:string,path:string,body:Record<string,unknown>)=>Promise<unknown>}) {
  const [ids,setIds]=useState<string[]>([]);const [feedback,setFeedback]=useState('');const [plan,setPlan]=useState<Plan|null>(null);const [error,setError]=useState('')
  const body={expected_workflow_version:workflow.row_version,expected_revision_id:workflow.revision_id,
    expected_result_hash:workflow.reprocess_result_hash??workflow.result_hash??workflow.sample_result_hash,question_src_ids:ids,feedback}
  async function preview(){setError('');try{setPlan(await request<Plan>({url:`${WORKFLOWS}/${workflow.workflow_id}/reprocess-preview`,method:'POST',data:body}))}
    catch(cause){setError(cause instanceof Error?cause.message:'修复计划读取失败')}}
  return <Collapse items={[{key:'repair',label:'退回后局部重生成',children:<Space orientation="vertical" style={{width:'100%'}} size={12}>
    <Typography.Text type="secondary">先保存具体审核问题，再预览修复范围。新结果仍须整套逐题重新审核。</Typography.Text>
    {!workflow.result_hash&&!workflow.sample_result_hash&&<Alert type="warning" title="本次标注失败，尚无完整结果" description="修复将以已冻结来源创建新修订，重新生成前5题并复核；失败响应和费用继续保留。"/>}
    <Select mode="multiple" aria-label="待修复题目" placeholder="选择需要修复的题目" style={{width:'100%'}} value={ids} options={questions.map(q=>({value:q.question_src_id,label:`第${q.question_no}题`}))} onChange={value=>{setIds(value);setPlan(null)}}/>
    <Input.TextArea aria-label="重生成具体反馈" placeholder="填写要修复的具体问题和依据" value={feedback} maxLength={4000} onChange={event=>{setFeedback(event.target.value);setPlan(null)}}/>
    {error&&<Alert type="error" title={error}/>}<Button disabled={busy||!ids.length||!feedback.trim()} onClick={()=>void preview()}>预览修复范围和小样影响</Button>
    {plan&&<Alert type="info" title={`本次生成 ${plan.generation_count} 题；最终审核 ${plan.review_count} 题`} description={<Space orientation="vertical">
      <span>{plan.sample_valid?'依赖比较通过，复用有效小样审批':'小样依赖或目标发生变化，须重新试标复核'}</span>
      <span>费用与未知预留继续累计同一原音账本，下一次请求仍须满足预算上限。</span>
      <Button type="primary" disabled={busy} onClick={()=>void command('reprocess','reprocess',{...body,expected_plan_hash:plan.plan_hash})}>按此范围创建修复修订</Button>
    </Space>}/>}
  </Space>}]}/>
}
