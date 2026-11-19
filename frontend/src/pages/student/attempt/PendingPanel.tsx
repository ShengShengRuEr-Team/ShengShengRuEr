import { useState } from 'react'
import { Alert, Button, Checkbox, Modal, Space, Typography } from 'antd'
import type { AttemptSubmitEnvelopeV1, EnvelopeFailureReason, RetentionDecision } from '../../../attempt/types'
import { retentionNotice } from '../../../attempt/retention'
import { formatDateTime } from '../../../utils/format'

const FAILURE_TEXT: Record<EnvelopeFailureReason, string> = {
  'bad-json': '提交记录不是合法 JSON',
  'missing-key': '提交记录缺少可用的提交编号',
  'invalid-payload': '提交记录内容不完整或字段非法',
  'unknown-version': '提交记录版本无法识别',
  'legacy-v1': '检测到旧版本数据，已按保护状态处理',
}

export interface PendingPanelProps {
  envelope: AttemptSubmitEnvelopeV1 | null
  unrecoverableReason?: EnvelopeFailureReason
  statusUnknown: boolean
  conflict: boolean
  retention: RetentionDecision
  counts?: { answered: number; total: number }
  busy?: boolean
  onRetry: () => void
  onQuery: () => void
  onClear: () => void
}

/**
 * P-06/P-14/P-17：冻结只读状态。
 * - 普通 pending/unknown：同键重试、查询、强警告清除；
 * - 信封损坏（pending-unrecoverable）：只允许查询/强警告清除，不重发、不自动删；
 * - 只显示静态「上次已答 x/y」计数，不进入答题卡/进度、不恢复选中态。
 */
export default function PendingPanel({
  envelope,
  unrecoverableReason,
  statusUnknown,
  conflict,
  retention,
  counts,
  busy = false,
  onRetry,
  onQuery,
  onClear,
}: PendingPanelProps) {
  const [retryOpen, setRetryOpen] = useState(false)
  const [clearOpen, setClearOpen] = useState(false)
  const [riskAccepted, setRiskAccepted] = useState(false)
  const unrecoverable = unrecoverableReason !== undefined

  return (
    <div className="pending-panel">
      <Alert
        type={conflict ? 'error' : 'warning'}
        showIcon
        message={
          conflict
            ? '提交状态自相矛盾，已保护性冻结'
            : unrecoverable
              ? '提交记录无法解析，已进入受保护状态'
              : statusUnknown
                ? '提交结果尚未确认，答案已冻结'
                : '上次提交结果待确认，答案已冻结'
        }
        description={
          <Space direction="vertical" size={4}>
            <span>
              {conflict
                ? '服务端返回的状态与提交计数不一致；本机草稿、信封与提交标记均保留。请重新查询状态，确认前不可修改答案。'
                : unrecoverable
                  ? `原因：${FAILURE_TEXT[unrecoverableReason]}。原始记录已保留，不会自动删除或重发。`
                  : '本页不显示所选答案与进度；请使用原提交编号重试，或先查询提交状态。'}
            </span>
            {counts && (
              <Typography.Text type="secondary" className="small-text">
                上次已答 {counts.answered}/{counts.total}（静态记录，不是实时作答进度）
              </Typography.Text>
            )}
            {envelope && (
              <Typography.Text type="secondary" className="small-text">
                提交请求时间：{formatDateTime(envelope.requestedAt)}
              </Typography.Text>
            )}
          </Space>
        }
      />

      <div className="retry-policy-notice">
        <Typography.Text type="secondary" className="small-text">
          {retentionNotice(retention)}
        </Typography.Text>
      </div>

      <Space size={8} wrap>
        {!unrecoverable && (
          <Button
            type="primary"
            disabled={busy || conflict}
            onClick={() => {
              setRiskAccepted(false)
              setRetryOpen(true)
            }}
          >
            重试提交（同键）
          </Button>
        )}
        <Button disabled={busy} onClick={onQuery}>
          查询提交状态
        </Button>
        <Button
          danger
          disabled={busy}
          onClick={() => {
            setRiskAccepted(false)
            setClearOpen(true)
          }}
        >
          强警告清除
        </Button>
      </Space>

      <Modal
        open={retryOpen}
        title="确认同键重试"
        okText="我已知悉，重试"
        cancelText="取消"
        onCancel={() => setRetryOpen(false)}
        onOk={() => {
          setRetryOpen(false)
          onRetry()
        }}
        centered
        okButtonProps={{ disabled: !riskAccepted }}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            type="warning"
            showIcon
            message="将使用原提交编号与冻结的答案重试"
            description="重试不会生成新编号；若服务端已成功提交，将按已提交处理。"
          />
          <Checkbox
            checked={riskAccepted}
            onChange={(event) => setRiskAccepted(event.target.checked)}
          >
            我已知悉风险，确认使用原提交编号重试
          </Checkbox>
        </Space>
      </Modal>

      <Modal
        open={clearOpen}
        title="强警告清除提交记录"
        okText="仍要清除"
        cancelText="取消"
        okButtonProps={{ danger: true, disabled: !riskAccepted }}
        onCancel={() => setClearOpen(false)}
        onOk={() => {
          setClearOpen(false)
          onClear()
        }}
        centered
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            type="error"
            showIcon
            message="清除后可能无法确认上次提交结果"
            description="上次提交结果可能无法确认；清除后可能重复提交；本卷仅可提交一次；请确认已通过查询状态核实结果。"
          />
          <Checkbox
            checked={riskAccepted}
            onChange={(event) => setRiskAccepted(event.target.checked)}
          >
            我已知悉风险，仍要清除本机提交记录
          </Checkbox>
        </Space>
      </Modal>
    </div>
  )
}
