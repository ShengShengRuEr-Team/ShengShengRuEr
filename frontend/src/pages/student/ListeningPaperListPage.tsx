import { useEffect, useState } from 'react'
import { ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Empty, Skeleton, Space, Table, Typography } from 'antd'
import type { TableProps } from 'antd'
import { useNavigate } from 'react-router-dom'
import type { PaperSummary } from '../../api/adapters'
import { getListeningPapers } from '../../api/listening'
import { studentListeningPaperPath } from '../../constants/routes'
import { isAbortError } from '../../utils/concurrency'
import { formatContentScope, formatDuration, formatPaperLabel } from '../../utils/format'

export default function StudentListeningPaperListPage() {
  const navigate = useNavigate()
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

  const columns: TableProps<PaperSummary>['columns'] = [
    {
      title: '试卷',
      render: (_value, paper) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>
            {formatPaperLabel(paper.year, paper.month, paper.paperSet)}
          </Typography.Text>
          <Typography.Text type="secondary" className="small-text">
            {formatContentScope(paper.contentScope)}
          </Typography.Text>
        </Space>
      ),
    },
    { title: '级别', width: 100, dataIndex: 'level' },
    {
      title: '年份 / 月份',
      width: 150,
      render: (_value, paper) => `${paper.year} 年 ${paper.month} 月`,
    },
    {
      title: '时长',
      width: 100,
      render: (_value, paper) => formatDuration(paper.durationMs),
    },
    {
      title: '操作',
      width: 130,
      render: (_value, paper) => (
        <Button
          type="primary"
          onClick={(event) => {
            event.stopPropagation()
            navigate(studentListeningPaperPath(paper.examPaperId))
          }}
        >
          查看听力
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
            当前仅支持听音频与查看题目，作答功能后续开放。
          </Typography.Text>
        </Space>
        <div className="page-actions">
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
          <Table<PaperSummary>
            rowKey="examPaperId"
            columns={columns}
            dataSource={items}
            pagination={false}
            scroll={{ x: 720 }}
            rowClassName={items.length > 0 ? 'table-row-clickable' : undefined}
            onRow={(paper) => ({
              onClick: () => navigate(studentListeningPaperPath(paper.examPaperId)),
            })}
            locale={{
              emptyText: (
                <Empty
                  description={
                    error ? '加载失败，请点击上方「重试」' : '暂无可查看的听力试卷，请联系老师开放'
                  }
                />
              ),
            }}
          />
        )}
      </Card>
    </Space>
  )
}
