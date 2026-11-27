import { useEffect, useRef, useState } from 'react'
import { Button, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Typography, Alert, Drawer, Descriptions } from 'antd'
import { ReloadOutlined, PlusOutlined, InboxOutlined } from '@ant-design/icons'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { request } from '../../../api/client'
import { ApiError } from '../../../api/api-error'
import { LIBRARY, libraryWrite, listLibrary, type LibraryPaper } from '../../../api/library'
import { label } from '../../../api/processing-adapters'

interface CreateValues {exam_level: string; exam_year: number; exam_month: number; paper_set: number; expected_question_count_source: string}
export default function LibraryPaperListPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [items, setItems] = useState<LibraryPaper[]>([]), [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true), [error, setError] = useState(''), [reload, setReload] = useState(0)
  const [creating, setCreating] = useState(false), [busy, setBusy] = useState(false)
  const [archive, setArchive] = useState<LibraryPaper | null>(null), [impact, setImpact] = useState<Record<string, unknown> | null>(null), [reason, setReason] = useState('')
  const createKey = useRef(crypto.randomUUID()), actionKey = useRef(crypto.randomUUID())
  const page = Math.max(1, Number(params.get('page')) || 1), recycled = params.get('archived') === 'true'
  const filterKey = params.toString()
  const [form] = Form.useForm<CreateValues>()
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('')
    const query = Object.fromEntries(new URLSearchParams(filterKey))
    void listLibrary({...query, page, page_size: 20}, controller.signal).then(data => {
      if (!controller.signal.aborted) {setItems(data.items); setTotal(data.total)}
    }).catch(cause => {if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '列表读取失败')})
      .finally(() => {if (!controller.signal.aborted) setLoading(false)})
    return () => controller.abort()
  }, [filterKey, page, reload])
  function filter(name: string, value?: string) {
    const next = new URLSearchParams(params); next.delete('page'); value ? next.set(name, value) : next.delete(name); setParams(next)
  }
  async function create(values: CreateValues) {
    setBusy(true); setError('')
    try {const result = await libraryWrite(LIBRARY, {...values, mode: 'manual'}, createKey.current)
      createKey.current = crypto.randomUUID(); setCreating(false)
      navigate(`/admin/listening-papers/processing/${result.workflow_id}/edit`)
    } catch (cause) {setError(cause instanceof Error ? cause.message : '登记失败')
      if (cause instanceof ApiError && cause.status > 0) createKey.current = crypto.randomUUID()
    } finally {setBusy(false)}
  }
  async function openEditor(paper: LibraryPaper) {
    setBusy(true); setError('')
    try {const operation = await libraryWrite(`${LIBRARY}/${paper.exam_paper_id}/edit-draft`, {expected_row_version: paper.row_version, reason: '从题库打开唯一编辑草稿'}, crypto.randomUUID())
      navigate(`/admin/listening-papers/processing/${operation.workflow_id}/edit`)
    } catch (cause) {setError(cause instanceof Error ? cause.message : '草稿打开失败')} finally {setBusy(false)}
  }
  async function previewArchive(paper: LibraryPaper) {
    setError(''); setReason(''); setImpact(null); setArchive(paper); actionKey.current = crypto.randomUUID()
    try {setImpact(await request<Record<string, unknown>>({url: `${LIBRARY}/${paper.exam_paper_id}/archive-preview`, method: 'POST'}))}
    catch (cause) {setError(cause instanceof Error ? cause.message : '影响预览失败')}
  }
  async function submitArchive() {
    if (!archive || !impact || !reason.trim()) return
    setBusy(true); setError('')
    try {await libraryWrite(`${LIBRARY}/${archive.exam_paper_id}/${recycled ? 'restore' : 'archive'}`, {expected_row_version: impact.row_version, expected_content_hash:impact.content_hash, reason: reason.trim()}, actionKey.current)
      setArchive(null); setReload(value => value + 1)
    } catch (cause) {setError(cause instanceof Error ? cause.message : '操作失败')} finally {setBusy(false)}
  }
  return <Space orientation="vertical" size={20} style={{width: '100%'}}>
    <div className="page-header"><div><Typography.Title level={4} style={{margin: 0}}>题库管理{recycled ? ' · 回收站' : ' · 听力试卷'}</Typography.Title>
      <Typography.Text type="secondary">保存版本、正式批次与学生开放分别管理。恢复试卷后需重新确认开放。</Typography.Text></div>
      <Space wrap><Button icon={<InboxOutlined />} onClick={() => filter('archived', recycled ? undefined : 'true')}>{recycled ? '返回题库' : '回收站'}</Button>
        {!recycled && <><Button onClick={() => navigate('/admin/listening-papers/processing')}>处理任务</Button><Button onClick={() => navigate('/admin/listening-papers/processing/new')}>上传材料</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>新增试卷</Button></>}
      </Space></div>
    <Space wrap><Input.Search aria-label="搜索试卷" placeholder="搜索试卷编码" key={filterKey} defaultValue={params.get('keyword') ?? ''} allowClear onSearch={value => filter('keyword', value)} style={{width: 240}} />
      <Select aria-label="按级别筛选" value={params.get('exam_level') ?? ''} onChange={value => filter('exam_level', value)} style={{width: 130}} options={[{value: '', label: '全部级别'}, {value: 'CET4', label: 'CET4'}, {value: 'CET6', label: 'CET6'}]} />
      <InputNumber aria-label="按年份筛选" placeholder="年份" value={params.get('exam_year') ? Number(params.get('exam_year')) : null} min={1980} max={2200} onChange={value => filter('exam_year', value ? String(value) : undefined)} />
      <Select aria-label="按月份筛选" value={params.get('exam_month') ?? ''} onChange={value => filter('exam_month', value)} options={[{value: '', label: '全部月份'}, {value: '6', label: '6月'}, {value: '12', label: '12月'}]} style={{width: 120}} />
      <Select aria-label="按开放状态筛选" value={params.get('visible') ?? ''} onChange={value => filter('visible', value)} options={[{value: '', label: '全部开放状态'}, {value: 'true', label: '已开放'}, {value: 'false', label: '未开放'}]} style={{width: 150}} />
      <Select aria-label="按处理状态筛选" value={params.get('processing_state') ?? ''} onChange={value => filter('processing_state', value)} options={[{value: '', label: '全部处理状态'}, ...['awaiting_materials', 'editing', 'awaiting_source', 'candidate_ready', 'awaiting_review', 'failed'].map(value => ({value, label: label(value)}))]} style={{width: 160}} />
      <Button icon={<ReloadOutlined />} onClick={() => setReload(value => value + 1)}>刷新</Button></Space>
    {error && <Alert type="error" showIcon title={error} />}
    <Table<LibraryPaper> rowKey="exam_paper_id" loading={loading} dataSource={items} scroll={{x: 1100}} pagination={{current: page, total, pageSize: 20, showSizeChanger: false, onChange: value => {const next = new URLSearchParams(params); next.set('page', String(value)); setParams(next)}}}
      columns={[
        {title: '试卷', render: (_, paper) => <Space orientation="vertical" size={0}><Typography.Text strong>{paper.code}</Typography.Text><Typography.Text type="secondary">{paper.exam_year}年{paper.exam_month}月 · 第{paper.paper_set}套</Typography.Text></Space>},
        {title: '题量', render: (_, paper) => `${paper.question_count} / ${paper.expected_question_count ?? '待核'}`},
        {title: '编辑版本', render: (_, paper) => paper.version_no ? `V${paper.version_no}` : '尚未保存'},
        {title: '正式批次', render: (_, paper) => paper.current_batch_code ?? '未入库'},
        {title: '处理 / 审核', render: (_, paper) => <Space orientation="vertical" size={0}><span>{label(paper.processing_state)}</span><span>{label(paper.review_state)}</span></Space>},
        {title: '学生开放', render: (_, paper) => <Tag color={paper.is_visible ? 'green' : 'default'}>{paper.is_visible ? '已开放' : '未开放'}</Tag>},
        {title: '操作', width: 260, render: (_, paper) => <Space wrap>
          {!recycled && <><Button type="link" disabled={busy} onClick={() => void openEditor(paper)}>编辑 / 版本</Button>{paper.current_batch_id && <Link to={`/admin/listening-papers/${paper.exam_paper_id}`}>正式详情</Link>}{paper.workflow_id && <Link to={`/admin/listening-papers/processing/${paper.workflow_id}`}>处理</Link>}</>}
          <Button type="link" danger={!recycled} onClick={() => void previewArchive(paper)}>{recycled ? '恢复' : '归档'}</Button></Space>},
      ]} locale={{emptyText: recycled ? '回收站为空' : '没有符合条件的试卷'}} />
    <Drawer title="新增标准完整真题" open={creating} onClose={() => setCreating(false)} width={480} destroyOnHidden>
      <Typography.Paragraph type="secondary">支持四级、六级标准完整25题真题。材料与内容可稍后补齐，缺项草稿不能送审或发布。</Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={{exam_level: 'CET4', exam_year: 2025, exam_month: 6, paper_set: 1}} onFinish={values => void create(values)}>
        <Form.Item name="exam_level" label="级别" rules={[{required: true}]}><Select options={[{value: 'CET4'}, {value: 'CET6'}]} /></Form.Item>
        <Form.Item name="exam_year" label="年份" rules={[{required: true}]}><InputNumber min={1980} max={2200} precision={0} /></Form.Item>
        <Form.Item name="exam_month" label="月份" rules={[{required: true}]}><Select options={[{value: 6, label: '6月'}, {value: 12, label: '12月'}]} /></Form.Item>
        <Form.Item name="paper_set" label="套别" rules={[{required: true}]}><Select options={[1, 2, 3].map(value => ({value, label: `第${value}套`}))} /></Form.Item>
        <Form.Item name="expected_question_count_source" label="完整题量的原件依据" rules={[{required: true, whitespace: true}]}><Input.TextArea rows={3} maxLength={2000} placeholder="填写原卷名称、页码和25题范围依据" /></Form.Item>
        <Button type="primary" htmlType="submit" loading={busy}>登记并编辑</Button>
      </Form></Drawer>
    <Modal title={recycled ? '恢复试卷' : '归档影响确认'} open={Boolean(archive)} onCancel={() => setArchive(null)} onOk={() => void submitArchive()} confirmLoading={busy} okText={recycled ? '恢复，保持未开放' : '确认归档'} okButtonProps={{danger: !recycled, disabled: !impact || !reason.trim()}}>
      {impact && <><Typography.Paragraph>{String(impact.impact)}</Typography.Paragraph><Descriptions size="small" column={1} items={[{key: 'b', label: '批次', children: String(impact.batch_count)}, {key: 'v', label: '保存版本', children: String(impact.version_count)}, {key: 'a', label: '历史作答', children: String(impact.attempt_count)}]} /></>}
      <Input.TextArea aria-label="归档或恢复原因" value={reason} onChange={event => setReason(event.target.value)} placeholder="填写操作原因" maxLength={2000} />
    </Modal>
  </Space>
}
