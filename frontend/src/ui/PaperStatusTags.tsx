import { Tag } from 'antd'
import { formatDateTime } from '../utils/format'

/**
 * 状态标签：严格对应后端四个独立字段，不合并成"完成/未完成"。
 * 措辞依据需求文档 §2.2——"已确认开放"是许可，不等于"当前可访问"。
 */

export function BatchTag({ hasBatch }: { hasBatch: boolean }) {
  return hasBatch ? <Tag color="blue">当前批次</Tag> : <Tag>暂无当前批次</Tag>
}

export function CheckTag({ passed, checkedAt }: { passed: boolean; checkedAt: string | null }) {
  if (!checkedAt) {
    return <Tag>尚未检查</Tag>
  }
  return passed ? <Tag color="green">检查通过</Tag> : <Tag color="red">检查未通过</Tag>
}

export function VisibilityTag({ visible }: { visible: boolean }) {
  return visible ? <Tag color="green">已确认开放</Tag> : <Tag>未确认开放</Tag>
}

export function AccessTag({ accessible }: { accessible: boolean }) {
  return accessible ? <Tag color="green">当前可访问</Tag> : <Tag>暂不可访问</Tag>
}

export function ReviewStatusTag({ status }: { status: string }) {
  if (!status) {
    return <Tag>—</Tag>
  }
  const color =
    status === '已通过' ? 'green' : status === '需修改' ? 'red' : status === '待确认' ? 'gold' : 'default'
  return <Tag color={color}>{status}</Tag>
}

export function ContentStateTag({ state }: { state: string }) {
  if (state === '可用') {
    return <Tag color="green">可用</Tag>
  }
  return <Tag color="red">{state || '待补齐'}</Tag>
}

/** 检查时间：无记录时显示"尚未检查"。 */
export function CheckedAtText({ checkedAt }: { checkedAt: string | null }) {
  return <span className="muted-text">检查时间：{checkedAt ? formatDateTime(checkedAt) : '—'}</span>
}
