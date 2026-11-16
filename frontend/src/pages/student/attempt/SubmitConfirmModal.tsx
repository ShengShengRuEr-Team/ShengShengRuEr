import { Alert, Modal, Space, Typography } from 'antd'
import type { AttemptCounts } from '../../../attempt/state'

export interface SubmitConfirmModalProps {
  open: boolean
  counts: AttemptCounts
  submitting?: boolean
  onCancel: () => void
  onConfirm: () => void
}

/** 交卷确认：只显示计数、不列题号；全部未答强提示；仅一次。 */
export default function SubmitConfirmModal({
  open,
  counts,
  submitting = false,
  onCancel,
  onConfirm,
}: SubmitConfirmModalProps) {
  const allUnanswered = counts.answered === 0
  return (
    <Modal
      open={open}
      title="确认交卷"
      onCancel={submitting ? undefined : onCancel}
      onOk={onConfirm}
      okText={submitting ? '提交中…' : '确认交卷'}
      cancelText="取消"
      okButtonProps={{ disabled: submitting, loading: submitting }}
      cancelButtonProps={{ disabled: submitting }}
      maskClosable={!submitting}
      closable={!submitting}
      centered
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Typography.Text>
          共 {counts.total} 题 · 已答 {counts.answered} 题 · 未答{' '}
          {counts.unanswered} 题 · 标记 {counts.flagged} 题
        </Typography.Text>
        <Alert
          type={allUnanswered ? 'error' : 'warning'}
          showIcon
          message={
            allUnanswered
              ? '所有题目均未作答，提交后将无法再修改，成绩预计为 0%。'
              : '未答题目按答错计分；提交后不可修改。'
          }
        />
        <Typography.Text type="secondary" className="small-text">
          本卷仅可提交一次；离开页面不会取消已发出的提交。
        </Typography.Text>
      </Space>
    </Modal>
  )
}
