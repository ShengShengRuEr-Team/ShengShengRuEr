import { Alert, Button, Space, Typography } from 'antd'
import { formatDateTime } from '../../../utils/format'

export type DraftBannerKind =
  | 'restored'
  | 'saved'
  | 'stale'
  | 'unavailable'
  | 'pending'
  | 'multitab'

export interface DraftBannerProps {
  kind: DraftBannerKind
  savedAt?: string | null
  answered?: number
  total?: number
  canRestart?: boolean
  onRestart?: () => void
}

/** P-04/P-12/P-18：草稿状态与提示统一在页头 Banner，不叠加多条。 */
export default function DraftBanner({
  kind,
  savedAt,
  answered,
  total,
  canRestart = false,
  onRestart,
}: DraftBannerProps) {
  if (kind === 'pending') {
    return (
      <Alert
        type="warning"
        showIcon
        message="上次提交结果待确认，本页已冻结编辑。"
        description="请使用原提交编号重试或查询状态；在确认前不可修改答案，也不会生成新的提交编号。"
      />
    )
  }
  if (kind === 'multitab') {
    return (
      <Alert
        type="info"
        showIcon
        message="另一个标签页已提交本卷，当前页面已转为只读。"
        description="本页未保存的草稿不会复活；可查询提交状态或返回列表。"
      />
    )
  }
  if (kind === 'unavailable') {
    return (
      <Alert
        type="warning"
        showIcon
        message="本机暂存不可用"
        description="可继续在当前页面作答，但刷新或关闭后可能无法恢复；提交时仍需按提示确认。"
      />
    )
  }
  if (kind === 'stale') {
    return (
      <Alert
        type="warning"
        showIcon
        message="本机草稿与当前试卷内容不一致，已忽略旧答案。"
        description="请重新作答；旧提交信封（如有）不会被自动删除。"
      />
    )
  }

  const savedText = savedAt ? `保存于 ${formatDateTime(savedAt)}` : ''
  const countText =
    answered !== undefined && total !== undefined
      ? `已答 ${answered}/${total}`
      : ''
  return (
    <Alert
      type="info"
      showIcon
      message={
        <Space size={12} wrap>
          <span>{kind === 'restored' ? '已恢复本机草稿' : '本机草稿已自动暂存'}</span>
          {countText && <Typography.Text>{countText}</Typography.Text>}
          {savedText && (
            <Typography.Text type="secondary" className="small-text">
              {savedText}
            </Typography.Text>
          )}
          <Typography.Text type="secondary" className="small-text">
            仅当前浏览器保存，不跨设备
          </Typography.Text>
        </Space>
      }
      action={
        canRestart && onRestart ? (
          <Button size="small" onClick={onRestart}>
            重新开始
          </Button>
        ) : undefined
      }
    />
  )
}
