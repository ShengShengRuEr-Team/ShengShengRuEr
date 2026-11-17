import { PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Input,
  Modal,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  fetchJobOverview,
  fetchJobRuns,
  setJobEnabled,
  triggerJob,
} from '../../api/admin/jobs'
import type { JobOverviewDto, JobRunDto } from '../../api/admin/types'
import { ApiError } from '../../api/api-error'
import { showSuccess } from '../../ui/message'
import { RUN_STATE_LABELS } from '../../generated/adminConstants'
import { labelOf } from '../../utils/adminLabels'

export const POLL_INTERVAL_MS = 15_000
const PAGE_SIZE = 20

type ActionKind = 'enable' | 'disable' | 'trigger'

const RUN_STATE_COLORS: Record<string, string> = {
  QUEUED: 'blue',
  RUNNING: 'processing',
  SUCCEEDED: 'green',
  PARTIAL: 'orange',
  FAILED: 'red',
  INTERRUPTED: 'red',
}

function healthTag(health: string) {
  if (health === 'ok') {
    return <Tag color="green">正常</Tag>
  }
  if (health === 'stale') {
    return <Tag color="orange">心跳过期</Tag>
  }
  return <Tag>未启动</Tag>
}

export default function MonitorJobsPage() {
  const [overview, setOverview] = useState<JobOverviewDto | null>(null)
  const [runs, setRuns] = useState<JobRunDto[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [runsError, setRunsError] = useState<string | null>(null)
  const [action, setAction] = useState<ActionKind | null>(null)
  const [reason, setReason] = useState('')
  const [reasonError, setReasonError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const inFlight = useRef(false)

  const loadRuns = useCallback(async (nextPage: number) => {
    try {
      const data = await fetchJobRuns(nextPage, PAGE_SIZE)
      setRuns(data.items)
      setTotal(data.total)
      setRunsError(null)
    } catch (cause) {
      setRunsError(cause instanceof ApiError ? cause.message : '加载执行记录失败')
    }
  }, [])

  const load = useCallback(
    async (silent = false) => {
      if (inFlight.current) {
        return
      }
      inFlight.current = true
      if (!silent) {
        setLoading(true)
      }
      try {
        const data = await fetchJobOverview()
        setOverview(data)
        setError(null)
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : '加载任务配置失败')
      } finally {
        if (!silent) {
          setLoading(false)
        }
        inFlight.current = false
      }
    },
    [],
  )

  useEffect(() => {
    void load()
    void loadRuns(page)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!document.hidden) {
        void load(true)
        void loadRuns(page)
      }
    }, POLL_INTERVAL_MS)
    const onVisible = () => {
      if (!document.hidden) {
        void load(true)
        void loadRuns(page)
      }
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [load, loadRuns, page])

  const openAction = (kind: ActionKind) => {
    setAction(kind)
    setReason('')
    setReasonError(null)
  }

  const submitAction = async () => {
    if (action === null) {
      return
    }
    const trimmed = reason.trim()
    if (trimmed.length < 1 || trimmed.length > 200) {
      setReasonError('reason 需为 1—200 个字符')
      return
    }
    setSubmitting(true)
    try {
      if (action === 'trigger') {
        const result = await triggerJob(trimmed)
        showSuccess(`已排队（${result.state}），等待调度执行`)
      } else {
        const enabled = action === 'enable'
        const result = await setJobEnabled(enabled, trimmed)
        showSuccess(
          result.changed
            ? enabled
              ? '已恢复任务'
              : '已暂停任务'
            : '配置未变化',
        )
      }
      setAction(null)
      await load()
      await loadRuns(page)
    } catch (cause) {
      setReasonError(cause instanceof ApiError ? cause.message : '操作失败，结果未确认，请刷新核实')
    } finally {
      setSubmitting(false)
    }
  }

  const runColumns: ColumnsType<JobRunDto> = [
    {
      title: '触发方式',
      dataIndex: 'trigger',
      width: 100,
      render: (value: string) => (value === 'scheduled' ? '计划' : '手动'),
    },
    {
      title: 'slot',
      dataIndex: 'slot_key',
      width: 120,
      render: (value: string | null) => value ?? '—',
    },
    {
      title: '状态',
      dataIndex: 'state',
      width: 110,
      render: (value: string) => (
        <Tag color={RUN_STATE_COLORS[value] ?? 'default'}>
          {labelOf(RUN_STATE_LABELS, value)}
        </Tag>
      ),
    },
    {
      title: '尝试',
      dataIndex: 'attempt_count',
      width: 80,
      render: (value: number) => `${value}/2`,
    },
    {
      title: '计数完整',
      dataIndex: 'counts_complete',
      width: 100,
      render: (value: boolean) => (value ? '是' : '否（结果未确认）'),
    },
    {
      title: '重试',
      dataIndex: 'retry_at',
      width: 160,
      render: (value: string | null, row) =>
        row.retry_pending ? `等待重试：${value ?? '—'}` : '—',
    },
    {
      title: '错误码',
      dataIndex: 'error_code',
      width: 150,
      render: (value: string | null) => value ?? '—',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 220,
    },
  ]

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Card
        title={
          <Space>
            <span>留存任务</span>
            {overview && healthTag(overview.scheduler_health)}
          </Space>
        }
        extra={
          <Space>
            {overview && (
              <>
                <Button
                  icon={<PlayCircleOutlined />}
                  onClick={() => openAction('trigger')}
                >
                  立即执行
                </Button>
                <Button
                  icon={<ReloadOutlined />}
                  loading={loading}
                  onClick={() => {
                    void load()
                    void loadRuns(page)
                  }}
                >
                  刷新
                </Button>
              </>
            )}
          </Space>
        }
        loading={loading && !overview}
      >
        {error && (
          <Space orientation="vertical" size="small" style={{ width: '100%' }}>
            <Alert type="error" showIcon title={error} />
            <Button onClick={() => void load()}>重试</Button>
          </Space>
        )}
        {overview && (
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="任务编码">
              {overview.job.job_id}
            </Descriptions.Item>
            <Descriptions.Item label="启用">
              <Switch
                checked={overview.job.enabled}
                checkedChildren="启用"
                unCheckedChildren="暂停"
                onChange={(checked) =>
                  openAction(checked ? 'enable' : 'disable')
                }
              />
            </Descriptions.Item>
            <Descriptions.Item label="时区">
              {overview.job.timezone}
            </Descriptions.Item>
            <Descriptions.Item label="错过计划数">
              {overview.job.missed_slots}
            </Descriptions.Item>
            <Descriptions.Item label="下次计划">
              {overview.job.next_scheduled_at ?? '未排期'}
            </Descriptions.Item>
            <Descriptions.Item label="上次计划 slot">
              {overview.job.last_scheduled_slot ?? '—'}
            </Descriptions.Item>
            <Descriptions.Item label="当前执行">
              {overview.job.active_run_id ?? '无'}
            </Descriptions.Item>
            <Descriptions.Item label="上次完成">
              {overview.job.last_run_id ?? '无'}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Card>

      {overview && (
        <Card title="调度实例心跳" size="small">
          {overview.instances.length === 0 ? (
            <Typography.Text type="secondary">
              调度进程未启动（not_configured）。API 就绪不依赖调度进程，页面按心跳展示。
            </Typography.Text>
          ) : (
            <Table
              rowKey="instance_id"
              size="small"
              pagination={false}
              dataSource={overview.instances}
              columns={[
                { title: '实例', dataIndex: 'instance_id' },
                { title: '启动时间', dataIndex: 'booted_at' },
                { title: '心跳', dataIndex: 'heartbeat_at' },
                {
                  title: '状态',
                  dataIndex: 'state',
                  render: (value: string | null) => value ?? '—',
                },
                {
                  title: '最近错误',
                  dataIndex: 'last_error_code',
                  render: (value: string | null) => value ?? '—',
                },
              ]}
            />
          )}
        </Card>
      )}

      <Card title="执行记录" size="small">
        {runsError && (
          <Alert type="error" showIcon title={runsError} style={{ marginBottom: 12 }} />
        )}
        <Table<JobRunDto>
          rowKey="id"
          size="small"
          loading={loading}
          columns={runColumns}
          dataSource={runs}
          scroll={{ x: 1040 }}
          locale={{ emptyText: '暂无执行记录' }}
          pagination={{
            current: page,
            pageSize: PAGE_SIZE,
            total,
            showSizeChanger: false,
            showTotal: (value) => `共 ${value} 条`,
            onChange: (nextPage) => {
              setPage(nextPage)
              void loadRuns(nextPage)
            },
          }}
        />
      </Card>

      <Modal
        open={action !== null}
        title={
          action === 'trigger'
            ? '立即执行留存清理'
            : action === 'enable'
              ? '恢复留存任务'
              : '暂停留存任务'
        }
        okText={action === 'trigger' ? '排队' : '确认'}
        cancelText="取消"
        confirmLoading={submitting}
        onOk={() => void submitAction()}
        onCancel={() => setAction(null)}
        destroyOnHidden
      >
        <Space orientation="vertical" size="small" style={{ width: '100%' }}>
          {action === 'trigger' && (
            <Typography.Text type="secondary">
              手动执行只创建排队记录，实际删除由调度进程在获得任务锁后执行。
            </Typography.Text>
          )}
          {reasonError && <Alert type="error" showIcon title={reasonError} />}
          <Input.TextArea
            rows={3}
            maxLength={200}
            showCount
            placeholder="操作理由（1—200 字）"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            aria-label="操作理由"
          />
        </Space>
      </Modal>
    </Space>
  )
}
