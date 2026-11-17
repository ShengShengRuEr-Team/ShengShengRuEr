import { ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Col, Row, Space, Statistic, Tag, Typography } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchDashboard } from '../../api/admin/dashboard'
import type { DashboardDto } from '../../api/admin/types'
import { ApiError } from '../../api/api-error'
import { ROUTES } from '../../constants/routes'

interface CardSpec {
  key: keyof DashboardDto['cards']
  title: string
  hint?: string
  clickable?: boolean
}

const CARDS: CardSpec[] = [
  { key: 'paper_count', title: '试卷总数', hint: '同卷多批次不重复计卷' },
  {
    key: 'awaiting_visibility_count',
    title: '检查通过待确认',
    hint: '最新检查通过、尚未确认可见',
    clickable: true,
  },
  { key: 'failed_check_count', title: '检查未通过', hint: '最新检查明确失败' },
  { key: 'active_student_count', title: '在读学生', hint: '不含管理员角色' },
  { key: 'disabled_student_count', title: '停用学生', hint: '不含管理员角色' },
  { key: 'successful_attempts_7d', title: '近 7 天成功提交', hint: '按北京时间窗口' },
]

function cacheLabel(status: DashboardDto['cache']['status']): {
  text: string
  color: string
} {
  if (status === 'hit') {
    return { text: '缓存命中', color: 'green' }
  }
  if (status === 'miss') {
    return { text: '缓存未命中', color: 'blue' }
  }
  return { text: '缓存未启用', color: 'default' }
}

export default function HomePage() {
  const navigate = useNavigate()
  const [data, setData] = useState<DashboardDto | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [stale, setStale] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const next = await fetchDashboard()
      setData(next)
      setError(null)
      setStale(false)
    } catch (cause) {
      const message =
        cause instanceof ApiError ? cause.message : '加载首页汇总失败'
      // 失败不显示 0：有旧数据时保留并标“可能已过期”，否则展示错误。
      if (data) {
        setStale(true)
        setError(null)
      } else {
        setError(message)
      }
    } finally {
      setLoading(false)
    }
  }, [data])

  useEffect(() => {
    void load()
    // 只做首屏加载；不做自动循环重试。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const badge = data ? cacheLabel(data.cache.status) : null

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Card
        title="业务首页"
        extra={
          <Space>
            <Button
              icon={<ReloadOutlined />}
              loading={loading}
              onClick={() => void load()}
            >
              刷新
            </Button>
            <Button type="primary" onClick={() => navigate(ROUTES.ADMIN_LISTENING_PAPERS)}>
              题库管理
            </Button>
          </Space>
        }
      >
        {error && (
          <Space orientation="vertical" size="small" style={{ width: '100%' }}>
            <Alert type="error" showIcon title={error} />
            <Button onClick={() => void load()}>重试</Button>
          </Space>
        )}
        {stale && data && (
          <Alert
            type="warning"
            showIcon
            title={`数据可能已过期（as_of: ${data.as_of}）`}
            description="保留上次成功采集的数据，未显示为最新；请手动刷新核实。"
            style={{ marginBottom: 12 }}
          />
        )}
        {data && (
          <Space orientation="vertical" size="small" style={{ width: '100%' }}>
            <Space wrap size="large">
              <Typography.Text type="secondary">
                采集时间（as_of）：{data.as_of}
              </Typography.Text>
              <Typography.Text type="secondary">
                统计窗口：{data.window_start} — {data.window_end}
              </Typography.Text>
              <Typography.Text type="secondary">
                时区：{data.timezone}
              </Typography.Text>
              {badge && <Tag color={badge.color}>{badge.text}</Tag>}
              <Typography.Text type="secondary">
                缓存 TTL：{data.cache.ttl_seconds} 秒
              </Typography.Text>
              {data.cache.age_seconds !== null && (
                <Typography.Text type="secondary">
                  缓存年龄：{data.cache.age_seconds} 秒
                </Typography.Text>
              )}
            </Space>
            {data.cards.awaiting_visibility_count === 0 &&
              data.cards.failed_check_count === 0 && (
                <Typography.Text type="secondary">
                  当前没有待确认或检查未通过的试卷。
                </Typography.Text>
              )}
          </Space>
        )}
      </Card>

      {data && (
        <Row gutter={[16, 16]}>
          {CARDS.map((card) => (
            <Col key={card.key} xs={24} sm={12} lg={8} xl={8}>
              <Card hoverable={card.clickable} loading={loading}>
                <Statistic title={card.title} value={data.cards[card.key]} />
                {card.hint && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {card.hint}
                  </Typography.Text>
                )}
                {card.clickable && (
                  <div style={{ marginTop: 8 }}>
                    <Button
                      size="small"
                      type="link"
                      style={{ padding: 0 }}
                      onClick={() => navigate(ROUTES.ADMIN_LISTENING_PAPERS)}
                    >
                      进入题库列表
                    </Button>
                  </div>
                )}
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </Space>
  )
}
