import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Empty, Select, Skeleton, Space, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import type { ContentCheck, PaperCompanion, PaperSummary } from '../../api/adapters'
import { getAdminCompanion, getContentCheck, getListeningPapers } from '../../api/listening'
import { adminListeningPaperPath } from '../../constants/routes'
import { isAbortError, mapWithConcurrency } from '../../utils/concurrency'
import { formatContentScope, formatDuration, formatPaperLabel } from '../../utils/format'
import {
  BatchTag,
  CheckTag,
  ReviewStatusTag,
  VisibilityTag,
} from '../../ui/PaperStatusTags'

/** 状态补调的规模与并发边界，见需求文档 §5.7。 */
const STATUS_FETCH_LIMIT = 20
const STATUS_CONCURRENCY = 3
const STATUS_TIMEOUT_MS = 8000

interface RowStatus {
  loading: boolean
  companion?: PaperCompanion
  check?: ContentCheck
  error?: string
}

type Row = PaperSummary

export default function AdminListeningPaperListPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const [items, setItems] = useState<Row[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusMap, setStatusMap] = useState<Record<number, RowStatus>>({})
  const [reloadKey, setReloadKey] = useState(0)
  const retryControllersRef = useRef<Set<AbortController>>(new Set())

  useEffect(() => {
    const controllers = retryControllersRef.current
    return () => {
      controllers.forEach((controller) => controller.abort())
      controllers.clear()
    }
  }, [])

  // 筛选条件放在 URL 上：从详情返回、浏览器前进后退都能保留。
  const level = searchParams.get('level') ?? 'all'
  const year = searchParams.get('year') ?? 'all'

  const updateFilter = (key: 'level' | 'year', value: string) => {
    const next = new URLSearchParams(searchParams)
    if (value === 'all') {
      next.delete(key)
    } else {
      next.set(key, value)
    }
    setSearchParams(next, { replace: true })
  }

  const openDetail = (paperId: number) => {
    navigate(adminListeningPaperPath(paperId), {
      state: { listSearch: location.search },
    })
  }

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false

    setLoading(true)
    setError(null)
    setStatusMap({})

    getListeningPapers({ signal: controller.signal })
      .then((list) => {
        if (cancelled) {
          return
        }
        setItems(list)
        setLoading(false)

        if (list.length === 0 || list.length > STATUS_FETCH_LIMIT) {
          return
        }

        setStatusMap(
          Object.fromEntries(list.map((paper) => [paper.examPaperId, { loading: true }])) as Record<
            number,
            RowStatus
          >,
        )

        void mapWithConcurrency(list, STATUS_CONCURRENCY, async (paper) => {
          // 用 allSettled 而不是 all：Promise.all 在 checks 先失败时会立刻返回，
          // 但同组的 companion 仍在飞，worker 会提前取下一套，导致并发上限失效。
          const [companionResult, checkResult] = await Promise.allSettled([
            getAdminCompanion(paper.examPaperId, {
              signal: controller.signal,
              timeout: STATUS_TIMEOUT_MS,
            }),
            getContentCheck(paper.examPaperId, {
              signal: controller.signal,
              timeout: STATUS_TIMEOUT_MS,
            }),
          ])
          if (cancelled) {
            return
          }
          if (companionResult.status === 'fulfilled' && checkResult.status === 'fulfilled') {
            setStatusMap((prev) => ({
              ...prev,
              [paper.examPaperId]: {
                loading: false,
                companion: companionResult.value,
                check: checkResult.value,
              },
            }))
            return
          }
          const reason =
            companionResult.status === 'rejected'
              ? companionResult.reason
              : (checkResult as PromiseRejectedResult).reason
          if (isAbortError(reason)) {
            return
          }
          setStatusMap((prev) => ({
            ...prev,
            [paper.examPaperId]: {
              loading: false,
              error: reason instanceof Error ? reason.message : '状态获取失败',
            },
          }))
        })
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

  const reloadRow = useCallback(async (paper: Row) => {
    // 行级重试也要受页面生命周期约束：离开列表时取消，避免请求在后台空跑。
    const retryController = new AbortController()
    retryControllersRef.current.add(retryController)
    setStatusMap((prev) => ({ ...prev, [paper.examPaperId]: { loading: true } }))
    try {
      const [companion, check] = await Promise.all([
        getAdminCompanion(paper.examPaperId, {
          signal: retryController.signal,
          timeout: STATUS_TIMEOUT_MS,
        }),
        getContentCheck(paper.examPaperId, {
          signal: retryController.signal,
          timeout: STATUS_TIMEOUT_MS,
        }),
      ])
      if (retryController.signal.aborted) {
        return
      }
      setStatusMap((prev) => ({
        ...prev,
        [paper.examPaperId]: { loading: false, companion, check },
      }))
    } catch (rowError) {
      if (retryController.signal.aborted || isAbortError(rowError)) {
        return
      }
      // Promise.all 首个失败时，其余请求可能仍未结束。先取消同组请求，
      // 再释放控制器，避免卸载时失去对未完成请求的控制。
      retryController.abort()
      setStatusMap((prev) => ({
        ...prev,
        [paper.examPaperId]: {
          loading: false,
          error: rowError instanceof Error ? rowError.message : '状态获取失败',
        },
      }))
    } finally {
      retryControllersRef.current.delete(retryController)
    }
  }, [])

  const levelOptions = useMemo(() => {
    const values = Array.from(new Set(items.map((item) => item.level)))
    return [
      { value: 'all', label: '全部级别' },
      ...values.map((value) => ({ value, label: value })),
    ]
  }, [items])

  const yearOptions = useMemo(() => {
    const values = Array.from(new Set(items.map((item) => item.year))).sort((a, b) => b - a)
    return [
      { value: 'all', label: '全部年份' },
      ...values.map((value) => ({ value: String(value), label: `${value} 年` })),
    ]
  }, [items])

  const filtered = useMemo(
    () =>
      items.filter(
        (item) =>
          (level === 'all' || item.level === level) && (year === 'all' || String(item.year) === year),
      ),
    [items, level, year],
  )

  const renderStatusCell = (paper: Row, kind: 'batch' | 'check' | 'visible' | 'review') => {
    const status = statusMap[paper.examPaperId]
    if (!status) {
      return <Tag>—</Tag>
    }
    if (status.loading) {
      return <Tag>获取中</Tag>
    }
    if (status.error || !status.companion) {
      return (
        <Space size={4}>
          <Typography.Text type="danger">获取失败</Typography.Text>
          <Button
            type="link"
            size="small"
            onClick={(event) => {
              // 阻止冒泡：否则会同时触发行点击跳转到详情页
              event.stopPropagation()
              void reloadRow(paper)
            }}
          >
            重试
          </Button>
        </Space>
      )
    }

    switch (kind) {
      case 'batch':
        return <BatchTag hasBatch={Boolean(status.companion.batchCode)} />
      case 'check':
        return (
          <CheckTag
            passed={status.companion.checkPassed}
            checkedAt={status.check?.checkedAt ?? null}
          />
        )
      case 'visible':
        return <VisibilityTag visible={status.companion.isVisible} />
      default:
        return <ReviewStatusTag status={status.companion.reviewStatus} />
    }
  }

  const columns: TableProps<Row>['columns'] = [
    {
      title: '试卷',
      dataIndex: 'code',
      render: (_value, paper) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{paper.code}</Typography.Text>
          <Typography.Text type="secondary" className="small-text">
            {formatContentScope(paper.contentScope)}
          </Typography.Text>
        </Space>
      ),
    },
    { title: '级别', dataIndex: 'level', width: 80 },
    {
      title: '年月 / 套别',
      width: 160,
      render: (_value, paper) => formatPaperLabel(paper.year, paper.month, paper.paperSet),
    },
    {
      title: '时长',
      width: 90,
      render: (_value, paper) => formatDuration(paper.durationMs),
    },
    {
      title: '当前批次',
      width: 120,
      render: (_value, paper) => renderStatusCell(paper, 'batch'),
    },
    {
      title: '检查结果',
      width: 120,
      render: (_value, paper) => renderStatusCell(paper, 'check'),
    },
    {
      title: '开放状态',
      width: 120,
      render: (_value, paper) => renderStatusCell(paper, 'visible'),
    },
    {
      title: '审核状态',
      width: 110,
      render: (_value, paper) => renderStatusCell(paper, 'review'),
    },
    {
      title: '操作',
      width: 110,
      render: (_value, paper) => (
        <Button
          type="link"
          onClick={(event) => {
            event.stopPropagation()
            openDetail(paper.examPaperId)
          }}
        >
          查看详情
        </Button>
      ),
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div className="page-header">
        <Space direction="vertical" size={4}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            题库管理 · 听力试卷
          </Typography.Title>
          <Typography.Text type="secondary">
            学生能否访问某套卷，取决于「当前批次 + 检查通过 + 已确认开放」三项同时成立。
          </Typography.Text>
        </Space>
        <div className="page-actions">
          <Select
            value={level}
            options={levelOptions}
            onChange={(value) => updateFilter('level', value)}
            style={{ width: 130 }}
            aria-label="按级别筛选"
          />
          <Select
            value={year}
            options={yearOptions}
            onChange={(value) => updateFilter('year', value)}
            style={{ width: 120 }}
            aria-label="按年份筛选"
          />
          <Button icon={<ReloadOutlined />} onClick={() => setReloadKey((key) => key + 1)}>
            刷新
          </Button>
        </div>
      </div>

      {items.length > STATUS_FETCH_LIMIT && (
        <Alert
          type="info"
          showIcon
          message={`当前共 ${items.length} 套试卷，列表只显示基本信息；开放状态请在试卷详情中查看。`}
        />
      )}

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
            <Skeleton active paragraph={{ rows: 6 }} />
          </div>
        ) : (
          <Table<Row>
            rowKey="examPaperId"
            columns={columns}
            dataSource={filtered}
            pagination={false}
            scroll={{ x: 1080 }}
            rowClassName="table-row-clickable"
            onRow={(paper) => ({
              onClick: () => openDetail(paper.examPaperId),
            })}
            locale={{
              emptyText: (
                <Empty
                  description={
                    error
                      ? '加载失败，请点击上方「重试」'
                      : items.length === 0
                        ? '暂无试卷，请先导入题库数据'
                        : '没有符合筛选条件的试卷'
                  }
                />
              ),
            }}
          />
        )}
      </Card>

      <Typography.Text type="secondary" className="small-text">
        列表本阶段不分页；开放状态由逐卷调用配套内容与检查结果接口汇总，单卷失败不影响其他行。
      </Typography.Text>
    </Space>
  )
}
