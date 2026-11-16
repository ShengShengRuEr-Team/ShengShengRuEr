import { useEffect, useMemo, useState } from 'react'
import { Progress, Space, Typography } from 'antd'
import { label } from '../../../api/processing-adapters'
import type { WorkflowDetail } from '../../../api/processing-types'

function duration(milliseconds: number) {
  const seconds = Math.floor(Math.max(0, milliseconds) / 1000)
  return `${String(Math.floor(seconds / 3600)).padStart(2,'0')}:${String(Math.floor(seconds / 60) % 60).padStart(2,'0')}:${String(seconds % 60).padStart(2,'0')}`
}

export default function ProcessingProgress({workflow}: {workflow: WorkflowDetail}) {
  const progress = workflow.progress
  const active = progress.active ?? workflow.processing_state === 'running'
  const [now, setNow] = useState(() => performance.now())
  const receivedAt = useMemo(() => performance.now(), [progress])
  useEffect(() => {
    if (!active) return
    const timer = setInterval(() => setNow(performance.now()), 1000)
    return () => clearInterval(timer)
  }, [active])
  const elapsed = progress.elapsed_ms + (active ? Math.max(0, now - receivedAt) : 0)
  const total = progress.total_count
  const known = total !== null && total > 0
  const percent = known ? Math.min(100, Math.floor(progress.completed_count / total * 100)) : 0
  const waiting = workflow.processing_state.startsWith('awaiting_') && workflow.processing_state !== 'awaiting_materials'
  const failed = workflow.processing_state === 'failed'
  const done = waiting || workflow.publication_state === 'published'
  const amount = known ? `${progress.completed_count} / ${total} ${progress.unit ?? '项'}`
    : progress.completed_count > 0 ? `已完成 ${progress.completed_count} ${progress.unit ?? '项'}` : ''
  return <section className="processing-progress" aria-label="处理进度">
    <div className="processing-progress-heading">
      <Space orientation="vertical" size={4}>
        <Typography.Text strong>{progress.description ?? label(progress.stage)}</Typography.Text>
        <Typography.Text type="secondary">
          {progress.current_item ? `正在处理：${progress.current_item}` : label(workflow.processing_state)}{amount ? ` · ${amount}` : ''}
        </Typography.Text>
      </Space>
      <div className="processing-progress-clock">
        <Typography.Text type="secondary">本次任务用时{!active ? '（已暂停）' : ''}</Typography.Text>
        <Typography.Text strong className="processing-progress-duration" aria-label="本次任务用时">{duration(elapsed)}</Typography.Text>
      </div>
    </div>
    <Typography.Text type="secondary">当前步骤进度</Typography.Text>
    {known || done || !active ? <Progress percent={done && !known ? 100 : percent} status={failed ? 'exception' : active ? 'active' : 'normal'}
      format={() => workflow.publication_state === 'published' ? '已入库' : waiting ? '待确认' : known ? `${percent}%` : label(workflow.processing_state)} />
      : <div className="processing-progress-indeterminate" role="progressbar" aria-label="当前步骤进度" aria-valuetext="处理中，暂无法计算百分比"><span /></div>}
    <Space wrap size={16}>
      <Typography.Text type="secondary">进度每5秒更新，用时每秒更新</Typography.Text>
      {active && !known && <Typography.Text type="secondary">此步骤暂无法计算百分比</Typography.Text>}
      {progress.last_progress_at && <Typography.Text type="secondary">最近进展 {new Date(progress.last_progress_at).toLocaleTimeString('zh-CN',{hour12:false})}</Typography.Text>}
    </Space>
  </section>
}
