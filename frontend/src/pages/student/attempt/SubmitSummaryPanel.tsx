import { useState } from 'react'
import { CheckOutlined, CopyOutlined } from '@ant-design/icons'
import { Alert, Button, Descriptions, Space, Tag, Typography } from 'antd'
import type { AttemptSummary } from '../../../api/adapters'
import { formatDateTime } from '../../../utils/format'

export interface SubmitSummaryPanelProps {
  summary: AttemptSummary | null
  submittedAt: string | null
  /** 服务端权威结果；cacheOnly 时必须标注「本机保存，仅供参考」。 */
  authoritative: boolean
  cacheOnly?: boolean
  versionNotice?: boolean
}

/** P-07/P-16：汇总只显示总数/正确率/估分/时间/编号；无逐题、无未答数。 */
export default function SubmitSummaryPanel({
  summary,
  submittedAt,
  authoritative,
  cacheOnly = false,
  versionNotice = false,
}: SubmitSummaryPanelProps) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle')

  const copyCode = async () => {
    if (!summary) {
      return
    }
    try {
      await navigator.clipboard.writeText(summary.attemptCode)
      setCopyState('copied')
    } catch {
      setCopyState('failed')
    }
  }

  const submittedText = summary?.submittedAt ?? submittedAt
  const score = summary?.practiceScore

  return (
    <div className="submit-summary-panel">
      {!authoritative && cacheOnly && (
        <Alert
          type="warning"
          showIcon
          message="本机保存，仅供参考"
          description="当前无法从服务端确认最新状态；以下内容来自本机提交记录。"
        />
      )}
      {versionNotice && (
        <Alert
          type="info"
          showIcon
          message="当前题目内容可能已更新；汇总对应提交时的试卷版本。"
        />
      )}
      {summary ? (
        <Descriptions
          size="small"
          column={{ xs: 1, sm: 2, md: 3 }}
          items={[
            {
              key: 'correct',
              label: '正确 / 总数',
              children: `${summary.correctCount} / ${summary.questionCount}`,
            },
            {
              key: 'rate',
              label: '正确率',
              children: `${summary.correctRate}%`,
            },
            {
              key: 'score',
              label: '练习估分',
              children:
                score?.available && score.value !== null && score.max !== null ? (
                  <Space size={6}>
                    <span>
                      {score.value} / {score.max}
                    </span>
                    <Tag color="blue">{score.label}</Tag>
                  </Space>
                ) : (
                  <Space size={6}>
                    <span>暂不可用</span>
                    {score?.reason && (
                      <Typography.Text type="secondary" className="small-text">
                        （{score.reason}）
                      </Typography.Text>
                    )}
                  </Space>
                ),
            },
            ...(submittedText
              ? [
                  {
                    key: 'time',
                    label: '提交时间',
                    children: formatDateTime(submittedText),
                  },
                ]
              : []),
            {
              key: 'code',
              label: '提交编号',
              children: (
                <Space size={6}>
                  <Typography.Text code copyable={false}>
                    {summary.attemptCode}
                  </Typography.Text>
                  <Button
                    size="small"
                    icon={<CopyOutlined />}
                    onClick={() => void copyCode()}
                  >
                    复制
                  </Button>
                  {copyState === 'copied' && (
                    <Typography.Text type="success">
                      <CheckOutlined /> 已复制
                    </Typography.Text>
                  )}
                  {copyState === 'failed' && (
                    <Typography.Text type="danger">
                      复制失败，请手动选择复制
                    </Typography.Text>
                  )}
                </Space>
              ),
            },
          ]}
        />
      ) : (
        <Descriptions
          size="small"
          column={1}
          items={[
            { key: 'missing', label: '汇总', children: '暂不可用' },
            ...(submittedText
              ? [
                  {
                    key: 'time',
                    label: '提交时间',
                    children: formatDateTime(submittedText),
                  },
                ]
              : []),
          ]}
        />
      )}
    </div>
  )
}
