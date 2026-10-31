import { useCallback, useEffect, useState } from 'react'
import { ArrowLeftOutlined } from '@ant-design/icons'
import {
  Alert,
  Breadcrumb,
  Button,
  Card,
  Divider,
  Tag,
  Typography,
} from 'antd'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../../api/api-error'
import { toAdminQuestion } from '../../api/adapters'
import type { AdminQuestion } from '../../api/adapters'
import { getAdminQuestions } from '../../api/papers'

const OPTION_KEYS = [
  { key: 'A', field: 'optionA' },
  { key: 'B', field: 'optionB' },
  { key: 'C', field: 'optionC' },
  { key: 'D', field: 'optionD' },
] as const

/**
 * 管理端题目页：接口 6（question:read_sensitive），
 * 展示题干、选项、标准答案、解析与听力原文。
 */
export default function AdminPaperQuestionsPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const paperId = Number(id)
  const validPaperId = Number.isInteger(paperId) && paperId > 0

  const [questions, setQuestions] = useState<AdminQuestion[]>([])
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
      const data = await getAdminQuestions(paperId)
      setQuestions(data.items.map(toAdminQuestion))
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
          { title: <Link to="/admin/papers">试卷管理</Link> },
          { title: `题目列表（试卷 #${validPaperId ? paperId : id}）` },
        ]}
      />

      <div className="page-header">
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            管理端题目
          </Typography.Title>
          <Typography.Text type="secondary">
            共 {questions.length} 道题，含答案 / 解析 / 听力原文
          </Typography.Text>
        </div>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/admin/papers')}>
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
          <Card
            key={question.id}
            type="inner"
            title={`第 ${question.questionNo} 题`}
            extra={<Tag color="green">答案：{question.correctOption ?? '—'}</Tag>}
          >
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

            <Divider style={{ margin: '16px 0 12px' }} />

            <Typography.Title level={5} style={{ marginTop: 0 }}>
              解析
            </Typography.Title>
            <Typography.Paragraph
              type={question.explanationText ? undefined : 'secondary'}
              style={{ whiteSpace: 'pre-wrap' }}
            >
              {question.explanationText ?? '暂无解析'}
            </Typography.Paragraph>

            <Typography.Title level={5}>听力原文</Typography.Title>
            <Typography.Paragraph
              type={question.transcriptText ? undefined : 'secondary'}
              style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}
            >
              {question.transcriptText ?? '暂无原文'}
            </Typography.Paragraph>
          </Card>
        ))}
      </div>
    </Card>
  )
}
