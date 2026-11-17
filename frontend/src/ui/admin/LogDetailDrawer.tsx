import { Alert, Descriptions, Drawer, Spin } from 'antd'
import { useEffect, useState } from 'react'
import { fetchLoginLog, fetchOperationLog } from '../../api/admin/logs'
import { ApiError } from '../../api/api-error'
import {
  EVENT_TYPE_LABELS,
  LOGIN_FAILURE_LABELS,
  LOG_RESULT_LABELS,
  ROLE_LABELS,
  TARGET_TYPE_LABELS,
} from '../../generated/adminConstants'
import { labelOf } from '../../utils/adminLabels'

function text(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

export default function LogDetailDrawer({
  kind,
  eventId,
  onClose,
}: {
  kind: 'login' | 'operation'
  eventId: string | null
  onClose: () => void
}) {
  const [data, setData] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!eventId) {
      setData(null)
      setError(null)
      return
    }
    let active = true
    setLoading(true)
    setError(null)
    const request = kind === 'login' ? fetchLoginLog : fetchOperationLog
    request(eventId)
      .then((detail) => {
        if (active) {
          setData(detail as unknown as Record<string, unknown>)
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setData(null)
          setError(cause instanceof ApiError ? cause.message : '加载详情失败')
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [eventId, kind])

  return (
    <Drawer
      open={Boolean(eventId)}
      onClose={onClose}
      width={520}
      title="日志详情"
      destroyOnHidden
    >
      {loading && <Spin />}
      {error && <Alert type="error" showIcon message={error} />}
      {data && (
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="事件ID">{text(data.event_id)}</Descriptions.Item>
          <Descriptions.Item label="请求ID">{text(data.request_id)}</Descriptions.Item>
          <Descriptions.Item label="时间">{text(data.occurred_at)}</Descriptions.Item>
          <Descriptions.Item label="事件类型">
            {labelOf(EVENT_TYPE_LABELS, data.event_type as string)}
          </Descriptions.Item>
          {kind === 'login' ? (
            <>
              <Descriptions.Item label="声明用户名">
                {text(data.username_attempted)}
              </Descriptions.Item>
              <Descriptions.Item label="角色">
                {data.role_snapshot
                  ? labelOf(ROLE_LABELS, data.role_snapshot as string)
                  : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="失败原因">
                {data.reason_code
                  ? labelOf(LOGIN_FAILURE_LABELS, data.reason_code as string)
                  : '—'}
              </Descriptions.Item>
            </>
          ) : (
            <>
              <Descriptions.Item label="目标类型">
                {data.target_type
                  ? labelOf(TARGET_TYPE_LABELS, data.target_type as string)
                  : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="目标ID">{text(data.target_id)}</Descriptions.Item>
              <Descriptions.Item label="摘要">{text(data.summary)}</Descriptions.Item>
              <Descriptions.Item label="run_id">{text(data.run_id)}</Descriptions.Item>
            </>
          )}
          <Descriptions.Item label="操作者">
            {text(data.actor_name)}（ID {text(data.actor_user_id)}）
          </Descriptions.Item>
          <Descriptions.Item label="结果">
            {labelOf(LOG_RESULT_LABELS, data.result as string)}
          </Descriptions.Item>
          <Descriptions.Item label="IP">{text(data.ip)}</Descriptions.Item>
          <Descriptions.Item label="UA 摘要">
            {text(data.user_agent_summary)}
          </Descriptions.Item>
          <Descriptions.Item label="耗时（毫秒）">
            {text(data.duration_ms)}
          </Descriptions.Item>
        </Descriptions>
      )}
    </Drawer>
  )
}
