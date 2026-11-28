import { useEffect, useMemo, useState } from 'react'
import { ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Empty, Skeleton, Space, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import type { PaperSummary } from '../../api/adapters'
import { getListeningPapers } from '../../api/listening'
import {
  answeredCount,
  hasSubmittedMarker,
  readDraft,
  readEnvelope,
} from '../../attempt/storage'
import { useAuth } from '../../auth/useAuth'
import { ROUTES, studentListeningPaperPath } from '../../constants/routes'
import { isAbortError } from '../../utils/concurrency'
import { formatContentScope, formatDuration, formatPaperLabel } from '../../utils/format'

type EntryState = 'start' | 'continue' | 'pending' | 'submitted'

interface ListRow {
  paper: PaperSummary
  state: EntryState
  answered?: number
  total?: number
}

const ACTION_TEXT: Record<EntryState, string> = {
  start: '开始作答',
  continue: '继续作答',
  pending: '结果待确认',
  submitted: '已提交',
}

/** 入口四态：只读本机草稿/信封/提交标记，不逐卷查 API-3（K-15）。 */
export default function StudentListeningPaperListPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const userId = user?.userId ?? 0
  const [items, setItems] = useState<PaperSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false

    setLoading(true)
    setError(null)

    getListeningPapers({ signal: controller.signal })
      .then((list) => {
        if (cancelled) {
          return
        }
        setItems(list)
        setLoading(false)
      })
      .catch((listError: unknown) => {
        if (cancelled || isAbortError(listError)) {
          return
        }
        setError(listError instanceof Error ? listError.message : '试卷列表加载失败')
        setLoading(false)
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [reloadKey])

  const rows = useMemo<ListRow[]>(
    () =>
      items.map((paper) => {
        if (hasSubmittedMarker(userId, paper.examPaperId)) {
          return { paper, state: 'submitted' }
        }
        const envelope = readEnvelope(userId, paper.examPaperId)
        if (envelope.kind === 'valid') {
          return { paper, state: 'pending' }
        }
        const draft = readDraft(userId, paper.examPaperId)
        if (draft.kind === 'valid') {
          return {
            paper,
            state: 'continue',
            answered: answeredCount(draft.draft.answers),
            total: draft.draft.loadedQuestionIds.length,
          }
        }
        return { paper, state: 'start' }
      }),
    [items, userId],
  )

  const columns: TableProps<ListRow>['columns'] = [
    {
      title: '试卷',
      render: (_value, row) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>
            {formatPaperLabel(row.paper.year, row.paper.month, row.paper.paperSet)}
          </Typography.Text>
          <Typography.Text type="secondary" className="small-text">
            {formatContentScope(row.paper.contentScope)}
          </Typography.Text>
        </Space>
      ),
    },
    { title: '级别', width: 100, render: (_value, row) => row.paper.level },
    {
      title: '年份 / 月份',
      width: 150,
      render: (_value, row) => `${row.paper.year} 年 ${row.paper.month} 月`,
    },
    {
      title: '时长',
      width: 100,
      render: (_value, row) => formatDuration(row.paper.durationMs),
    },
    {
      title: '本机进度',
      width: 150,
      render: (_value, row) => {
        if (row.state === 'continue') {
          return (
            <Typography.Text type="secondary" className="small-text">
              已答 {row.answered}/{row.total}
            </Typography.Text>
          )
        }
        if (row.state === 'pending') {
          return <Tag color="orange">提交结果待确认</Tag>
        }
        if (row.state === 'submitted') {
          return <Tag color="green">已提交</Tag>
        }
        return <Typography.Text type="secondary" className="small-text">未开始</Typography.Text>
      },
    },
    {
      title: '操作',
      width: 140,
      render: (_value, row) => (
        <Button
          type={row.state === 'continue' ? 'primary' : 'default'}
          onClick={(event) => {
            event.stopPropagation()
            navigate(studentListeningPaperPath(row.paper.examPaperId))
          }}
        >
          {ACTION_TEXT[row.state]}
        </Button>
      ),
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div className="page-header">
        <Space direction="vertical" size={4}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            听力练习
          </Typography.Title>
          <Typography.Text type="secondary">
            列表状态只读取本机草稿/提交记录；进入试卷后由服务端校正。本卷仅可提交一次，草稿仅保存在当前浏览器。
          </Typography.Text>
        </Space>
        <div className="page-actions">
          <Link to={ROUTES.STUDENT_WRONG_ANSWERS}>错题本</Link>
          <Button icon={<ReloadOutlined />} onClick={() => setReloadKey((key) => key + 1)}>
            刷新
          </Button>
        </div>
      </div>

      {error && (
        <Alert
          type="error"
          showIcon
          message="试卷列表加载失败"
          description={error}
          action={
            <Button size="small" onClick={() => setReloadKey((key) => key + 1)}>
              重试
            </Button>
          }
        />
      )}

      <Card styles={{ body: { padding: 0 } }}>
        {loading ? (
          <div className="card-loading">
            <Skeleton active paragraph={{ rows: 5 }} />
          </div>
        ) : (
          <Table<ListRow>
            rowKey={(row) => row.paper.examPaperId}
            columns={columns}
            dataSource={rows}
            pagination={false}
            scroll={{ x: 860 }}
            rowClassName={rows.length > 0 ? 'table-row-clickable' : undefined}
            onRow={(row) => ({
              onClick: () => navigate(studentListeningPaperPath(row.paper.examPaperId)),
            })}
            locale={{
              emptyText: (
                <Empty
                  description={
                    error ? '加载失败，请点击上方「重试」' : '暂无可作答的听力试卷，请联系老师开放'
                  }
                />
              ),
            }}
          />
        )}
      </Card>

      <Typography.Text type="secondary" className="small-text">
        仅支持桌面浏览器（≥1024px）；小于 1024px 不承诺可用。
      </Typography.Text>
    </Space>
  )
}
