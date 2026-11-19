import { useEffect, useState } from 'react'
import { Alert, Button, Empty, Select, Space, Table, Tag, Typography } from 'antd'
import { Link, useSearchParams } from 'react-router-dom'
import { listWorkflows } from '../../../api/processing'
import type { WorkflowSummary } from '../../../api/processing-types'
import { label, paperName, workflowState, needsSourceCheck } from '../../../api/processing-adapters'

export default function ProcessingListPage() {
  const [search, setSearch] = useSearchParams()
  const [items, setItems] = useState<WorkflowSummary[]>([])
  const [next, setNext] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const level = search.get('exam_level') ?? ''
  const state = search.get('processing_state') ?? ''
  const cursor = search.get('cursor') ?? ''
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    void listWorkflows({limit: 20, ...(level ? {exam_level: level} : {}),
      ...(state ? {processing_state: state} : {}), ...(cursor ? {cursor} : {})}, controller.signal)
      .then(page => { setItems(page.items); setNext(page.next_cursor) })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '任务读取失败') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [level, state, cursor, reload])
  function filter(key: string, value: string) { const params = new URLSearchParams(search); params.delete('cursor'); value ? params.set(key, value) : params.delete(key); setSearch(params) }
  return <Space orientation="vertical" size={20} style={{width: '100%'}}>
    <div className="page-header"><div><Typography.Title level={4}>处理任务与待审核</Typography.Title>
      <Typography.Text type="secondary">按阶段核对来源和标注，整套审核后发布，再单独确认学生开放。</Typography.Text></div>
      <Space><Link to="/admin/listening-papers"><Button>正式题库</Button></Link>
        <Link to="/admin/listening-papers/processing/new"><Button type="primary">上传新材料</Button></Link></Space></div>
    <Space wrap><Select aria-label="按考试级别筛选" value={level} style={{width: 140}} onChange={value => filter('exam_level', value)} options={[{value:'',label:'全部级别'},{value:'CET4',label:'CET4'},{value:'CET6',label:'CET6'}]} />
      <Select aria-label="按处理状态筛选" value={state} style={{width: 200}} onChange={value => filter('processing_state', value)} options={['', 'awaiting_materials', 'queued', 'running', 'awaiting_alignment', 'awaiting_source', 'awaiting_sample', 'awaiting_review', 'failed', 'stopped', 'completed'].map(value => ({value, label: value ? label(value) : '全部状态'}))} />
      <Button onClick={() => setReload(value => value + 1)}>刷新任务</Button></Space>
    {error && <Alert type="error" showIcon title={error} />}
    <Table<WorkflowSummary> loading={loading} rowKey="workflow_id" dataSource={items} pagination={false} locale={{emptyText: <Empty description="尚无处理任务，可先创建并上传一套材料" />}} columns={[
      {title:'试卷', key:'paper', render: (_, row) => <Link to={`/admin/listening-papers/processing/${row.workflow_id}`}>{paperName(row)}</Link>},
      {title:'处理',dataIndex:'processing_state',render: (_, row) => <Tag color={needsSourceCheck(row)?'warning':undefined}>{label(workflowState(row))}</Tag>},
      {title:'内容 / 错因审核',key:'review',render: (_, row) => `${label(row.content_review_state)} / ${label(row.error_review_state)}`},
      {title:'发布',dataIndex:'publication_state',render: value => label(String(value))},
      {title:'创建时间',dataIndex:'created_at',render: value => new Date(String(value)).toLocaleString('zh-CN')},
    ]} />
    <Space><Button disabled={!cursor} onClick={() => {const params = new URLSearchParams(search); params.delete('cursor'); setSearch(params)}}>返回首页</Button>
      <Button disabled={!next || loading} onClick={() => {if (next) {const params = new URLSearchParams(search); params.set('cursor', next); setSearch(params)}}}>下一页</Button></Space>
  </Space>
}
