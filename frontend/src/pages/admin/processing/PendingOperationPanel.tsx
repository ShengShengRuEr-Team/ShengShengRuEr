import { useState } from 'react'
import { Alert, Button, Space } from 'antd'
import { findOperation, pendingKey, readPending, sendOperation } from '../../../api/processing'
import type { Operation } from '../../../api/processing-types'

export default function PendingOperationPanel({owner, target, onRecovered, onChange}: {
  owner: number; target: string; onRecovered: (operation: Operation) => void; onChange: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = readPending(owner, target)
  if (!pending) return null
  async function recover(resend: boolean) {
    if (!pending) return
    setBusy(true); setError('')
    try {
      const operation = resend ? await sendOperation(owner, target, pending) : await findOperation(pending)
      localStorage.removeItem(pendingKey(owner, target)); onChange(); onRecovered(operation)
    } catch (cause) {
      setError(`${cause instanceof Error ? cause.message : '未查到操作'}。请保留原键和原请求；未查到不代表原请求一定未受理。`)
    } finally { setBusy(false) }
  }
  return <Alert type="warning" showIcon title="有一项操作尚未核对结果" description={<Space orientation="vertical">
    <span>操作：{pending.action}。先查询结果；恢复请求会使用原操作键和原版本条件。</span>
    {error && <span role="alert">{error}</span>}
    <Space wrap><Button loading={busy} onClick={() => void recover(false)}>查询原操作</Button>
      <Button disabled={busy} onClick={() => void recover(true)}>恢复原请求</Button>
      <Button disabled={busy} onClick={() => { localStorage.removeItem(pendingKey(owner, target)); onChange() }}>移除本地提示</Button></Space>
    <span>移除提示不会取消服务器上已受理的操作。</span>
  </Space>} />
}
