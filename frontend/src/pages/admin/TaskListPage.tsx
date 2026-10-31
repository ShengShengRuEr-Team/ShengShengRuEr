import { useCallback, useEffect, useRef, useState } from 'react'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Card,
  Collapse,
  Descriptions,
  Drawer,
  Modal,
  Progress,
  Select,
  Spin,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import { ApiError } from '../../api/api-error'
import { toPaper, toTask, toTaskList } from '../../api/adapters'
import type { Paper, Task, TaskListItem } from '../../api/adapters'
import { getPapers } from '../../api/papers'
import { createTask, getTask, getTasks } from '../../api/tasks'
import { isTaskStatus } from '../../api/types'
import {
  TASK_STATUS_COLORS,
  TASK_STATUS_LABELS,
} from '../../constants/task-status'
import { formatDateTime } from '../../utils/date'

/** 轮询：只在有 pending / running 任务时进行，5 秒一次，最多 60 次（5 分钟）。 */
const POLL_INTERVAL_MS = 5000
const MAX_POLL_COUNT = 60

function TaskStatusTag({ status }: { status: string }) {
  if (!isTaskStatus(status)) {
    return <Tag>{status}</Tag>
  }
  return (
    <Tag color={TASK_STATUS_COLORS[status]}>{TASK_STATUS_LABELS[status]}</Tag>
  )
}

/**
 * 管理端任务页：接口 7 启动任务、接口 8 列表、接口 9 详情。
 * 一期后端任务状态停留在 pending，因此需要限制自动轮询次数。
 */
export default function AdminTaskListPage() {
  const { message } = App.useApp()

  const [tasks, setTasks] = useState<TaskListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [papers, setPapers] = useState<Paper[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [selectedPaperId, setSelectedPaperId] = useState<number | undefined>()
  const [creating, setCreating] = useState(false)

  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detail, setDetail] = useState<Task | null>(null)

  const [pollStopped, setPollStopped] = useState(false)
  const pollCountRef = useRef(0)

  const loadTasks = useCallback(async (silent = false) => {
    if (!silent) {
      setLoading(true)
    }
    setError(null)
    try {
      const data = await getTasks()
      setTasks(toTaskList(data).items)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '任务列表加载失败')
    } finally {
      if (!silent) {
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    void loadTasks()
  }, [loadTasks])

  const hasActiveTask = tasks.some(
    (task) => task.status === 'pending' || task.status === 'running',
  )

  // 自动轮询：组件卸载或没有活跃任务时清除定时器。
  useEffect(() => {
    if (!hasActiveTask) {
      pollCountRef.current = 0
      setPollStopped(false)
      return
    }
    if (pollStopped) {
      return
    }

    const timer = window.setInterval(() => {
      if (pollCountRef.current >= MAX_POLL_COUNT) {
        window.clearInterval(timer)
        setPollStopped(true)
        message.warning('任务状态未更新，可手动刷新')
        return
      }
      pollCountRef.current += 1
      void loadTasks(true)
    }, POLL_INTERVAL_MS)

    return () => {
      window.clearInterval(timer)
    }
  }, [hasActiveTask, pollStopped, loadTasks, message])

  const handleRefresh = () => {
    pollCountRef.current = 0
    setPollStopped(false)
    void loadTasks()
  }

  const openCreateModal = async () => {
    setCreateOpen(true)
    setSelectedPaperId(undefined)
    if (papers.length > 0) {
      return
    }
    try {
      const data = await getPapers()
      setPapers(data.items.map(toPaper))
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '试卷列表加载失败')
    }
  }

  const handleCreate = async () => {
    if (!selectedPaperId) {
      message.warning('请先选择试卷')
      return
    }
    setCreating(true)
    try {
      await createTask({ paper_id: selectedPaperId })
      message.success('任务已创建')
      setCreateOpen(false)
      pollCountRef.current = 0
      setPollStopped(false)
      await loadTasks()
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '任务创建失败')
    } finally {
      setCreating(false)
    }
  }

  const openDetail = async (taskId: number) => {
    setDetailOpen(true)
    setDetailLoading(true)
    setDetail(null)
    try {
      const data = await getTask(taskId)
      setDetail(toTask(data))
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '任务详情加载失败')
      setDetailOpen(false)
    } finally {
      setDetailLoading(false)
    }
  }

  const columns: TableProps<TaskListItem>['columns'] = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    {
      title: '试卷 ID',
      dataIndex: 'paperId',
      width: 100,
      render: (value: number | null) => value ?? '—',
    },
    { title: '类型', dataIndex: 'taskType', width: 140 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value: string) => <TaskStatusTag status={value} />,
    },
    {
      title: '进度',
      dataIndex: 'progress',
      width: 160,
      render: (value: number) => <Progress percent={value} size="small" />,
    },
    {
      title: '异常信息',
      dataIndex: 'message',
      render: (value: string | null) =>
        value ? <Typography.Text type="danger">{value}</Typography.Text> : '—',
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      width: 190,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'action',
      width: 90,
      render: (_, record) => (
        <Button type="link" onClick={() => void openDetail(record.id)}>
          详情
        </Button>
      ),
    },
  ]

  const detailItems = detail
    ? [
        { key: 'id', label: '任务 ID', children: detail.id },
        { key: 'paper', label: '试卷 ID', children: detail.paperId ?? '—' },
        { key: 'type', label: '任务类型', children: detail.taskType },
        {
          key: 'status',
          label: '状态',
          children: <TaskStatusTag status={detail.status} />,
        },
        {
          key: 'progress',
          label: '进度',
          children: <Progress percent={detail.progress} size="small" />,
        },
        { key: 'createdBy', label: '创建人 ID', children: detail.createdBy ?? '—' },
        { key: 'startedAt', label: '开始时间', children: formatDateTime(detail.startedAt) },
        { key: 'finishedAt', label: '结束时间', children: formatDateTime(detail.finishedAt) },
        { key: 'createdAt', label: '创建时间', children: formatDateTime(detail.createdAt) },
        { key: 'updatedAt', label: '更新时间', children: formatDateTime(detail.updatedAt) },
      ]
    : []

  return (
    <Card>
      <div className="page-header">
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            任务管理
          </Typography.Title>
          <Typography.Text type="secondary">
            共 {tasks.length} 个任务
            {hasActiveTask && !pollStopped && '，自动刷新中（每 5 秒）'}
            {pollStopped && '，自动刷新已停止（已达 5 分钟上限）'}
          </Typography.Text>
        </div>
        <div className="page-actions">
          <Button icon={<ReloadOutlined />} onClick={handleRefresh} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => void openCreateModal()}>
            启动任务
          </Button>
        </div>
      </div>

      {error && (
        <Alert
          type="error"
          showIcon
          message={error}
          style={{ marginBottom: 16 }}
          action={
            <Button size="small" onClick={handleRefresh}>
              重试
            </Button>
          }
        />
      )}

      <Table<TaskListItem>
        rowKey="id"
        columns={columns}
        dataSource={tasks}
        loading={loading}
        pagination={{ pageSize: 10, hideOnSinglePage: true }}
        locale={{ emptyText: '暂无任务，可点击「启动任务」创建' }}
      />

      <Modal
        title="启动处理任务"
        open={createOpen}
        onOk={() => void handleCreate()}
        confirmLoading={creating}
        onCancel={() => setCreateOpen(false)}
        okText="启动任务"
        cancelText="取消"
      >
        <Typography.Paragraph type="secondary">
          一期后端创建任务后状态停留在「等待中」，实际处理链路由模块三接入。
        </Typography.Paragraph>
        <Select
          style={{ width: '100%' }}
          placeholder="选择试卷"
          value={selectedPaperId}
          onChange={(value: number) => setSelectedPaperId(value)}
          showSearch
          optionFilterProp="label"
          options={papers.map((paper) => ({
            value: paper.id,
            label: `${paper.title}（${paper.examLevel} ${paper.examYear}-${paper.examMonth}，第 ${paper.setNo} 套）`,
          }))}
        />
      </Modal>

      <Drawer
        title={detail ? `任务 #${detail.id} 详情` : '任务详情'}
        width={560}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
      >
        {detailLoading ? (
          <div className="drawer-loading">
            <Spin />
          </div>
        ) : detail ? (
          <>
            <Descriptions column={1} size="small" bordered items={detailItems} />

            <Typography.Title level={5} style={{ marginTop: 24 }}>
              异常信息
            </Typography.Title>
            <Typography.Paragraph type={detail.message ? 'danger' : 'secondary'}>
              {detail.message ?? '无'}
            </Typography.Paragraph>

            <Typography.Title level={5}>处理结果</Typography.Title>
            {detail.result ? (
              <Collapse
                items={[
                  {
                    key: 'result',
                    label: '查看结果 JSON',
                    children: (
                      <pre className="json-block">
                        {JSON.stringify(detail.result, null, 2)}
                      </pre>
                    ),
                  },
                ]}
              />
            ) : (
              <Typography.Text type="secondary">暂无结果</Typography.Text>
            )}
          </>
        ) : (
          <Typography.Text type="secondary">暂无数据</Typography.Text>
        )}
      </Drawer>
    </Card>
  )
}
