import { useRef } from 'react'
import {
  CheckCircleFilled,
  FlagFilled,
  FlagOutlined,
  CloseOutlined,
} from '@ant-design/icons'
import { Button, Space, Tag, Typography } from 'antd'
import type { OptionLetter, PaperQuestion } from '../../../api/adapters'

const LETTERS: OptionLetter[] = ['A', 'B', 'C', 'D']

export interface QuestionCardProps {
  question: PaperQuestion
  selected?: OptionLetter
  flagged: boolean
  readonly?: boolean
  disabled?: boolean
  onSelect?: (letter: OptionLetter) => void
  onClear?: () => void
  onToggleFlag?: () => void
}

/**
 * 单题卡：整行点选、清除、标记；只读模式无选中态、无标记/清除按钮。
 * 键盘：Tab 聚焦，方向键在选项间移动并选中，空格/回车由原生按钮提交。
 */
export default function QuestionCard({
  question,
  selected,
  flagged,
  readonly = false,
  disabled = false,
  onSelect,
  onClear,
  onToggleFlag,
}: QuestionCardProps) {
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([])
  const titleId = `question-${question.questionId}-title`

  if (readonly) {
    return (
      <div className="question-card question-card--readonly">
        <div className="question-head">
          <Typography.Text strong id={titleId}>
            第 {question.questionNo} 题
          </Typography.Text>
        </div>
        <div className="question-text">{question.questionText}</div>
        <div className="option-list">
          {question.options.map((option) => (
            <div key={option.label} className="option-item option-item--readonly">
              <span className="option-key">{option.label}</span>
              <span>{option.text || '—'}</span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  const focusLetter = (letter: OptionLetter) => {
    const index = LETTERS.indexOf(letter)
    optionRefs.current[index]?.focus()
    onSelect?.(letter)
  }

  return (
    <div className="question-card">
      <div className="question-head">
        <Space size={8} wrap>
          <Typography.Text strong id={titleId}>
            第 {question.questionNo} 题
          </Typography.Text>
          {flagged && (
            <Tag color="gold" icon={<FlagFilled />}>
              已标记
            </Tag>
          )}
        </Space>
      </div>
      <div className="question-text">{question.questionText}</div>
      <div
        className="option-list"
        role="radiogroup"
        aria-labelledby={titleId}
        onKeyDown={(event) => {
          if (disabled) {
            return
          }
          const currentIndex = LETTERS.indexOf(selected ?? 'A')
          if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
            event.preventDefault()
            focusLetter(LETTERS[(currentIndex + 1) % LETTERS.length])
          } else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
            event.preventDefault()
            focusLetter(LETTERS[(currentIndex + LETTERS.length - 1) % LETTERS.length])
          }
        }}
      >
        {question.options.map((option, index) => {
          const letter = LETTERS[index]
          const isSelected = selected === letter
          return (
            <button
              key={option.label}
              ref={(element) => {
                optionRefs.current[index] = element
              }}
              type="button"
              role="radio"
              aria-checked={isSelected}
              aria-label={`选项 ${letter}：${option.text || '（空）'}${
                isSelected ? '，已选' : ''
              }`}
              className={`option-item option-item--interactive${
                isSelected ? ' option-item--selected' : ''
              }`}
              disabled={disabled}
              onClick={() => onSelect?.(letter)}
            >
              <span className="option-key">{letter}</span>
              <span className="option-text">{option.text || '—'}</span>
              {isSelected && (
                <CheckCircleFilled className="option-check" aria-hidden="true" />
              )}
            </button>
          )
        })}
      </div>
      <Space size={8} className="question-actions">
        <Button
          size="small"
          icon={<CloseOutlined />}
          disabled={disabled || selected === undefined}
          onClick={onClear}
        >
          清除本题
        </Button>
        <Button
          size="small"
          icon={flagged ? <FlagFilled /> : <FlagOutlined />}
          disabled={disabled}
          onClick={onToggleFlag}
        >
          {flagged ? '取消标记' : '标记'}
        </Button>
      </Space>
    </div>
  )
}
