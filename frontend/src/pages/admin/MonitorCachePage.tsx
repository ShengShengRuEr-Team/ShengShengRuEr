import { Alert, Button, Card, Descriptions, Input, Modal, Space, Table, Typography } from 'antd'
import { useState } from 'react'
import {
  clearCache,
  fetchCache,
  fetchCacheEntries,
} from '../../api/admin/monitoring'
import type { CacheOverview } from '../../api/admin/monitoring'
import { ApiError } from '../../api/api-error'
import { useMonitorPolling } from '../../hooks/useMonitorPolling'
import { showSuccess } from '../../ui/message'

type Entry = Record<string, unknown>

export default function MonitorCachePage() {
  const { data, error, reload } = useMonitorPolling(fetchCache)
  const [entries, setEntries] = useState<Entry[]>([])
  const [entriesError, setEntriesError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const loadEntries = async () => {
    try {
      const page = await fetchCacheEntries()
      setEntries(page.items)
      setEntriesError(null)
    } catch (cause) {
      setEntriesError(cause instanceof ApiError ? cause.message : '加载缓存条目失败')
    }
  }

  const onOpen = () => {
    setOpen(true)
    setReason('')
    setActionError(null)
    void loadEntries()
  }

  const submit = async (overview: CacheOverview) => {
    if (reason.trim().length < 1 || reason.trim().length > 200) {
      setActionError('reason 需为 1—200 个字符')
      return
    }
    setBusy(true)
    try {
      const result = await clearCache({
        domain: overview.domain,
        expected_instance_id: overview.instance_id,
        reason: reason.trim(),
      })
      showSuccess(
        result.deleted_count === 0
          ? '无缓存条目，清理完成'
          : `已清理 ${result.deleted_count} 条缓存`,
      )
      setOpen(false)
      await loadEntries()
      reload()
    } catch (cause) {
      setActionError(cause instanceof ApiError ? cause.message : '清理失败，结果未确认，请刷新核实')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Card
        title="缓存监控"
        size="small"
        extra={<Button onClick={onOpen}>清理缓存</Button>}
      >
        {error && <Alert type="error" showIcon title={error} />}
        {data && (
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="域">{data.domain}</Descriptions.Item>
            <Descriptions.Item label="实例">{data.instance_id}</Descriptions.Item>
            <Descriptions.Item label="启用">{data.enabled ? '是' : '否'}</Descriptions.Item>
            <Descriptions.Item label="未过期条目">{data.entries}</Descriptions.Item>
            <Descriptions.Item label="TTL">{data.ttl_seconds} 秒</Descriptions.Item>
            <Descriptions.Item label="命中/未命中">
              {data.hits} / {data.misses}
            </Descriptions.Item>
            <Descriptions.Item label="Redis">
              {data.redis.status === 'not_configured' ? '未配置（不伪造数据）' : data.redis.status}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Card>

      <Card title="缓存条目（仅元数据）" size="small" extra={<Button onClick={() => void loadEntries()}>加载条目</Button>}>
        {entriesError && <Alert type="error" showIcon title={entriesError} />}
        <Table<Entry>
          rowKey={(row) => String(row.key)}
          size="small"
          dataSource={entries}
          pagination={false}
          locale={{ emptyText: '暂无条目' }}
          columns={[
            { title: '键', dataIndex: 'key' },
            { title: '创建时间', dataIndex: 'cached_at' },
            { title: '到期时间', dataIndex: 'expires_at' },
            { title: '剩余秒', dataIndex: 'remaining_seconds' },
          ]}
        />
        <Typography.Text type="secondary">列表不返回缓存值，只展示键与时间元数据。</Typography.Text>
      </Card>

      <Modal
        open={open}
        title="清理当前实例缓存"
        okText="确认清理"
        cancelText="取消"
        confirmLoading={busy}
        onOk={() => data && void submit(data)}
        onCancel={() => setOpen(false)}
        destroyOnHidden
      >
        {actionError && <Alert type="error" showIcon title={actionError} />}
        <Input.TextArea
          rows={3}
          maxLength={200}
          showCount
          aria-label="清理理由"
          placeholder="清理理由（1—200 字）"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
        <Typography.Text type="secondary">
          只清理当前实例（{data?.instance_id ?? '—'}）；结果为未确认时请刷新核实。
        </Typography.Text>
      </Modal>
    </Space>
  )
}
