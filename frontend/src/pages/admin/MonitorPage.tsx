import { Alert, Card, Descriptions, Space, Tag, Typography } from 'antd'
import type { MetricDto, MetricSnapshot } from '../../api/admin/monitoring'
import {
  fetchDatabase,
  fetchOauth,
  fetchServer,
  fetchTransport,
} from '../../api/admin/monitoring'
import { useMonitorPolling } from '../../hooks/useMonitorPolling'

export const STATUS_LABELS: Record<string, string> = {
  ok: '正常',
  error: '错误',
  unknown: '未知',
  stale: '数据过期',
  not_configured: '未启用/未配置',
  not_applicable: '不适用',
}

export function statusText(status: string): string {
  return STATUS_LABELS[status] ?? status
}

const SEVERITY_LABELS: Record<string, string> = {
  normal: '正常',
  warning: '警告',
  critical: '严重',
  none: '—',
}

function MetricCards({ metrics }: { metrics: Record<string, MetricDto> }) {
  return (
    <Space orientation="vertical" size="small" style={{ width: '100%' }}>
      {Object.entries(metrics).map(([name, metric]) => (
        <Card key={name} size="small" title={name}>
          <Space orientation="vertical" size={2}>
            <Typography.Text strong>
              {metric.value === null || metric.value === undefined
                ? '—'
                : `${String(metric.value)} ${metric.unit === 'none' ? '' : metric.unit}`}
            </Typography.Text>
            <Space size="small" wrap>
              <Tag>{statusText(metric.status)}</Tag>
              <Typography.Text type="secondary">
                严重度：{SEVERITY_LABELS[metric.severity] ?? metric.severity}
              </Typography.Text>
              {metric.reason && (
                <Typography.Text type="secondary">原因：{metric.reason}</Typography.Text>
              )}
            </Space>
            <Typography.Text type="secondary">
              来源：{metric.source} · 范围：{metric.scope} · 观测：{metric.observed_at ?? '—'}
            </Typography.Text>
          </Space>
        </Card>
      ))}
    </Space>
  )
}

export type MonitorKind = 'database' | 'server' | 'transport' | 'oauth'

export default function MonitorPage({ kind }: { kind: MonitorKind }) {
  const fetcher: (signal?: AbortSignal) => Promise<unknown> =
    kind === 'database'
      ? fetchDatabase
      : kind === 'server'
        ? fetchServer
        : kind === 'transport'
          ? fetchTransport
          : fetchOauth
  const { data, error, reload } = useMonitorPolling<unknown>(fetcher)

  if (error) {
    return (
      <Space orientation="vertical">
        <Alert type="error" showIcon title={error} />
        <button onClick={reload}>重试</button>
      </Space>
    )
  }
  if (data === null) {
    return <Typography.Text type="secondary">加载中…</Typography.Text>
  }

  if (kind === 'database' || kind === 'server') {
    const snapshot = data as MetricSnapshot
    return (
      <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
        <Card size="small">
          <Typography.Text type="secondary">
            采样方式：{snapshot.sampling} · 实例：{snapshot.instance_id} · 时间：
            {snapshot.server_time}
          </Typography.Text>
        </Card>
        <MetricCards metrics={snapshot.metrics} />
        {kind === 'server' && snapshot.module3 && (
          <Card size="small" title="模块三只读观测">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="状态">
                {statusText(snapshot.module3.status)}
              </Descriptions.Item>
              <Descriptions.Item label="原因">
                {snapshot.module3.reason ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="任务数">
                {snapshot.module3.tasks ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="Worker 存活">
                {snapshot.module3.worker_liveness === 'unknown'
                  ? '未知（不生成 Worker 心跳）'
                  : snapshot.module3.worker_liveness}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        )}
      </Space>
    )
  }

  const payload = data as unknown as Record<string, unknown>
  if (kind === 'transport') {
    return (
      <Card title="TLS 传输证据" size="small">
        <Descriptions column={1} size="small">
          <Descriptions.Item label="直连 scheme">
            {String(payload.direct_scheme ?? 'unknown')}
          </Descriptions.Item>
          <Descriptions.Item label="外部 TLS">
            {String(payload.external_tls_state ?? 'unknown')}
          </Descriptions.Item>
          <Descriptions.Item label="配置的站点 origin">
            {String(payload.configured_public_origin ?? '未配置')}
          </Descriptions.Item>
          <Descriptions.Item label="证据来源">
            {String(payload.source ?? 'unknown')}
          </Descriptions.Item>
          <Descriptions.Item label="原因">
            {String(payload.reason ?? '—')}
          </Descriptions.Item>
          <Descriptions.Item label="对端是否可信">
            {payload.peer_trusted ? '是' : '否'}
          </Descriptions.Item>
        </Descriptions>
        <Alert
          type="info"
          showIcon
          title="静态配置的 PUBLIC_ORIGIN 不代表已验证外部 TLS；直连观测以本页证据为准。"
        />
      </Card>
    )
  }

  return (
    <Card title="OAuth 能力" size="small">
      <Descriptions column={1} size="small">
        <Descriptions.Item label="状态">
          {statusText(String(payload.status ?? 'unknown'))}
        </Descriptions.Item>
        <Descriptions.Item label="原因">
          {String(payload.reason ?? '—')}
        </Descriptions.Item>
        <Descriptions.Item label="登录方式">
          {String(payload.login_mode ?? 'jwt_bearer')}
        </Descriptions.Item>
      </Descriptions>
      <Alert
        type="warning"
        showIcon
        title="当前未部署 OAuth Server；系统使用 JWT Bearer，登录事件请查看登录日志。"
      />
    </Card>
  )
}
