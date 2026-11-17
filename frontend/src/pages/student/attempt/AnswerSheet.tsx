import { useMemo } from 'react'
import { FlagFilled } from '@ant-design/icons'
import { Space, Typography } from 'antd'
import type { OptionLetter, PaperDetail } from '../../../api/adapters'

export interface AnswerSheetProps {
  detail: PaperDetail
  answers: Record<string, OptionLetter>
  flaggedQuestionIds: number[]
  currentQuestionId: number | null
  mode: 'answering' | 'neutral'
  onJump: (questionId: number, passageIndex: number) => void
}

/**
 * 答题卡：按篇分组全部题号；已答/未答/标记/当前用颜色+图标+文字区分。
 * neutral（已提交）只保留中性题号导航与当前题高亮，不显示进度/标记。
 */
export default function AnswerSheet({
  detail,
  answers,
  flaggedQuestionIds,
  currentQuestionId,
  mode,
  onJump,
}: AnswerSheetProps) {
  const flagged = useMemo(
    () => new Set(flaggedQuestionIds),
    [flaggedQuestionIds],
  )

  return (
    <nav className="answer-sheet" aria-label="答题卡">
      <div className="answer-sheet-title">
        <Typography.Text strong>答题卡</Typography.Text>
        {mode === 'answering' && (
          <Typography.Text type="secondary" className="small-text">
            共 {detail.passages.reduce((sum, p) => sum + p.questions.length, 0)} 题
          </Typography.Text>
        )}
      </div>

      {detail.passages.map((passage, passageIndex) => (
        <section key={passage.passageId} className="answer-sheet-group">
          <div className="answer-sheet-group-title">
            第 {passage.passageIndex} 篇
            <span className="small-text muted-text">{passage.passageType}</span>
          </div>
          <div className="answer-sheet-grid">
            {passage.questions.map((question) => {
              const answered = answers[String(question.questionId)] !== undefined
              const isFlagged = flagged.has(question.questionId)
              const isCurrent = currentQuestionId === question.questionId
              const stateLabel =
                mode === 'neutral'
                  ? isCurrent
                    ? '当前题'
                    : ''
                  : [
                      answered ? '已答' : '未答',
                      isFlagged ? '已标记' : '',
                      isCurrent ? '当前题' : '',
                    ]
                      .filter(Boolean)
                      .join('，')
              const className = [
                'answer-sheet-item',
                mode === 'neutral' ? 'answer-sheet-item--neutral' : '',
                mode === 'answering' && answered ? 'answer-sheet-item--answered' : '',
                mode === 'answering' && !answered ? 'answer-sheet-item--unanswered' : '',
                mode === 'answering' && isFlagged ? 'answer-sheet-item--flagged' : '',
                isCurrent ? 'answer-sheet-item--current' : '',
              ]
                .filter(Boolean)
                .join(' ')
              return (
                <button
                  key={question.questionId}
                  type="button"
                  className={className}
                  aria-label={`第${question.questionNo}题${
                    stateLabel ? `，${stateLabel}` : ''
                  }`}
                  aria-current={isCurrent ? 'true' : undefined}
                  onClick={() => onJump(question.questionId, passageIndex)}
                >
                  {question.questionNo}
                  {mode === 'answering' && isFlagged && (
                    <FlagFilled className="answer-sheet-flag" aria-hidden="true" />
                  )}
                </button>
              )
            })}
          </div>
        </section>
      ))}

      {mode === 'answering' && (
        <Space size={12} wrap className="answer-sheet-legend">
          <span>
            <i className="legend-dot legend-dot--answered" aria-hidden="true" /> 已答
          </span>
          <span>
            <i className="legend-dot legend-dot--unanswered" aria-hidden="true" /> 未答
          </span>
          <span>
            <FlagFilled aria-hidden="true" /> 标记
          </span>
          <span>
            <i className="legend-dot legend-dot--current" aria-hidden="true" /> 当前
          </span>
        </Space>
      )}
    </nav>
  )
}
