import { useState } from 'react'
import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Typography } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../../auth/useAuth'
import { readPending, sendOperation, WORKFLOWS } from '../../../api/processing'
import { ApiError } from '../../../api/api-error'
import PendingOperationPanel from './PendingOperationPanel'

interface Values {exam_level: string; exam_year: number; exam_month: number; paper_set: number; document_mode: string; paper_pages?: string; answer_pages?: string}
function pages(value = '') { if (!value.trim()) return []; const values = value.split(/[,，\s]+/).map(Number); if (values.some(value => !Number.isInteger(value) || value < 1) || new Set(values).size !== values.length) throw new Error('页码须为不重复的正整数，用逗号分隔'); return values.sort((a,b) => a-b) }
export default function NewWorkflowPage() {
  const {user} = useAuth(); const owner = user?.userId ?? 0
  const navigate = useNavigate(); const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  const [existing, setExisting] = useState(''); const [, rerender] = useState(0)
  async function create(values: Values) {
    if (readPending(owner, 'new')) return
    setBusy(true); setError(''); setExisting('')
    try {
      const {paper_pages, answer_pages, ...metadata} = values
      const operation = await sendOperation(owner, 'new', {action:'create',url:WORKFLOWS,method:'POST',key:crypto.randomUUID(),
        body:{...metadata,listening_pages:{paper:pages(paper_pages),answer:pages(answer_pages)}}})
      navigate(`/admin/listening-papers/processing/${operation.workflow_id}`, {replace:true})
    } catch (cause) { setError(cause instanceof Error ? cause.message : '创建失败'); if (cause instanceof ApiError && typeof cause.context?.workflow_id === 'string') setExisting(cause.context.workflow_id) }
    finally { setBusy(false) }
  }
  return <Space orientation="vertical" size={20} style={{width:'100%',maxWidth:900}}>
    <Link to="/admin/listening-papers/processing">返回处理任务</Link>
    <Typography.Title level={4}>创建材料处理任务</Typography.Title>
    <Alert type="info" showIcon title="先确认试卷身份，再上传三份原件" description="真实内容验收范围为2025年6月CET4第1套。其他套别可创建任务，仍需独立核对来源和处理结果。" />
    <PendingOperationPanel owner={owner} target="new" onChange={() => rerender(value => value+1)} onRecovered={operation => navigate(`/admin/listening-papers/processing/${operation.workflow_id}`)} />
    {error && <Alert type="error" showIcon title={error} action={existing ? <Link to={`/admin/listening-papers/processing/${existing}`}>继续已有任务</Link> : undefined} />}
    <Card><Form<Values> layout="vertical" onFinish={values => void create(values)} initialValues={{exam_level:'CET4',exam_year:2025,exam_month:6,paper_set:1,document_mode:'text'}}>
      <Space align="start" wrap><Form.Item name="exam_level" label="级别" rules={[{required:true}]}><Select style={{width:130}} options={[{value:'CET4',label:'CET4'},{value:'CET6',label:'CET6'}]} /></Form.Item>
        <Form.Item name="exam_year" label="年份" rules={[{required:true}]}><InputNumber min={1980} max={2200} precision={0} /></Form.Item>
        <Form.Item name="exam_month" label="月份" rules={[{required:true}]}><InputNumber min={1} max={12} precision={0} /></Form.Item>
        <Form.Item name="paper_set" label="套别" rules={[{required:true}]}><InputNumber min={1} max={100} precision={0} /></Form.Item></Space>
      <Form.Item name="document_mode" label="原卷文字来源" rules={[{required:true}]}><Select options={[{value:'text',label:'文本原卷PDF'},{value:'scan',label:'扫描原卷PDF（OCR）'}]} /></Form.Item>
      <Form.Item name="paper_pages" label="原卷听力页码（可选）" extra="填写实际PDF页码，以逗号分隔；留空由来源提取检查确定。"><Input placeholder="例如：2,3,4" /></Form.Item>
      <Form.Item name="answer_pages" label="答案解析听力页码（可选）"><Input placeholder="例如：1,2,3" /></Form.Item>
      <Button type="primary" htmlType="submit" loading={busy} disabled={Boolean(readPending(owner,'new'))}>创建并上传材料</Button>
    </Form></Card>
  </Space>
}
