import { useCallback, useEffect, useState } from 'react'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { Alert, Breadcrumb, Button, Card, Typography } from 'antd'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../../api/api-error'
import { toStudentQuestion } from '../../api/adapters'
import type { StudentQuestion } from '../../api/adapters'
import { getStudentQuestions } from '../../api/papers'

const OPTION_KEYS = [
  { key: 'A', field: 'optionA' },
  { key: 'B', field: 'optionB' },
  { key: 'C', field: 'optionC' },
  { key: 'D', field: 'optionD' },
] as const

/**
 * 学生端题目页：只调接口 5（GET /papers/{id}/questions），
 * 只渲染题干与选项；不请求、不声明、不渲染答案 / 解析 / 原文。
 */
export default function StudentPaperQuestionsPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const paperId = Number(id)
  const validPaperId = Number.isInteger(paperId) && paperId > 0

  const [questions, setQuestions] = useState<StudentQuestion[]>([])
  const [loading, setLoading] = useState(validPaperId)
  const [error, setError] = useState<string | null>(null)

  const loadQuestions = useCallback(async () => {
    if (!validPaperId) {
      setError('试卷 ID 不合法')
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await getStudentQuestions(paperId)
      setQuestions(data.items.map(toStudentQuestion))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '题目加载失败')
    } finally {
      setLoading(false)
    }
  }, [paperId, validPaperId])

  useEffect(() => {
    void loadQuestions()
  }, [loadQuestions])

  return (
    <Card loading={loading}>
      <Breadcrumb
        style={{ marginBottom: 16 }}
        items={[
          { title: <Link to="/papers">试卷列表</Link> },
          { title: `题目列表（试卷 #${validPaperId ? paperId : id}）` },
        ]}
      />

      <div className="page-header">
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            听力题目
          </Typography.Title>
          <Typography.Text type="secondary">
            共 {questions.length} 道题
          </Typography.Text>
        </div>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/papers')}>
          返回列表
        </Button>
      </div>

      {error && (
        <Alert
          type="error"
          showIcon
          message={error}
          style={{ marginBottom: 16 }}
          action={
            <Button size="small" onClick={() => void loadQuestions()}>
              重试
            </Button>
          }
        />
      )}

      {!error && !loading && questions.length === 0 && (
        <Typography.Text type="secondary">该试卷暂无题目</Typography.Text>
      )}

      <div className="list-stack">
        {questions.map((question) => (
          <Card key={question.id} type="inner" title={`第 ${question.questionNo} 题`}>
            <Typography.Paragraph strong style={{ whiteSpace: 'pre-wrap' }}>
              {question.promptText ?? '—'}
            </Typography.Paragraph>

            <div className="option-list">
              {OPTION_KEYS.map((option) => (
                <div className="option-item" key={option.key}>
                  <span className="option-key">{option.key}.</span>
                  <span>{question[option.field] ?? '—'}</span>
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>
    </Card>
  )
}
