import { useEffect, useMemo, useState } from 'react'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Empty, Skeleton, Space, Tag, Typography } from 'antd'
import { Link, useParams } from 'react-router-dom'
import type { PaperDetail } from '../../api/adapters'
import { ApiError } from '../../api/api-error'
import { getListeningPaper } from '../../api/listening'
import { ROUTES } from '../../constants/routes'
import AudioPlayer from '../../ui/AudioPlayer'
import { isAbortError } from '../../utils/concurrency'
import { formatContentScope, formatDuration, formatPaperLabel } from '../../utils/format'

interface LoadError {
  message: string
  notFound: boolean
}

export default function StudentListeningPaperPage() {
  const { examPaperId } = useParams()
  const paperId = Number(examPaperId)

  const [paper, setPaper] = useState<PaperDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<LoadError | null>(null)
  const [passageIndex, setPassageIndex] = useState(0)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    if (!Number.isFinite(paperId)) {
      setError({ message: '试卷 ID 无效', notFound: true })
      setLoading(false)
      return
    }

    const controller = new AbortController()
    let cancelled = false

    setLoading(true)
    setError(null)

    getListeningPaper(paperId)
      .then((detail) => {
        if (cancelled) {
          return
        }
        setPaper(detail)
        setPassageIndex(0)
        setLoading(false)
      })
      .catch((loadError: unknown) => {
        if (cancelled || isAbortError(loadError)) {
          return
        }
        const notFound = loadError instanceof ApiError && loadError.status === 404
        setPaper(null)
        setError({
          message: notFound
            ? '试卷不存在或暂不可用'
            : loadError instanceof Error
              ? loadError.message
              : '试卷加载失败',
          notFound,
        })
        setLoading(false)
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [paperId, reloadKey])

  const passages = paper?.passages ?? []
  const total = passages.length
  const current = useMemo(() => {
    if (total === 0) {
      return null
    }
    return passages[Math.min(Math.max(passageIndex, 0), total - 1)]
  }, [passages, passageIndex, total])

  // 翻篇后回到页面顶部：否则会停在新篇章的中部，看不到题干。
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [passageIndex])

  if (loading) {
    return (
      <Card>
        <Skeleton active paragraph={{ rows: 8 }} />
      </Card>
    )
  }

  if (error || !paper) {
    return (
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Link to={ROUTES.STUDENT_LISTENING_PAPERS}>
          <ArrowLeftOutlined /> 返回听力练习
        </Link>
        <Alert
          type={error?.notFound ? 'warning' : 'error'}
          showIcon
          message={error?.message ?? '试卷加载失败'}
          description={
            error?.notFound ? '该试卷可能尚未开放，或已被老师取消开放。' : undefined
          }
          action={
            error?.notFound ? undefined : (
              <Button size="small" onClick={() => setReloadKey((key) => key + 1)}>
                重试
              </Button>
            )
          }
        />
      </Space>
    )
  }

  return (
    <Space direction="vertical" size={14} style={{ width: '100%' }}>
      <div className="breadcrumb-row">
        <Link to={ROUTES.STUDENT_LISTENING_PAPERS}>
          <ArrowLeftOutlined /> 返回听力练习
        </Link>
        <Typography.Text type="secondary">第 {current ? current.passageIndex : 0} 篇 / 共 {total} 篇</Typography.Text>
      </div>

      <div className="page-header" style={{ marginBottom: 0 }}>
        <Space direction="vertical" size={4}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            {formatPaperLabel(paper.year, paper.month, paper.paperSet)} · {paper.level}
          </Typography.Title>
          <Typography.Text type="secondary">
            {formatContentScope(paper.contentScope)} · {formatDuration(paper.durationMs)}
          </Typography.Text>
        </Space>
        <Typography.Text type="secondary" className="small-text">
          当前仅支持听音频与查看题目，作答功能后续开放
        </Typography.Text>
      </div>

      {/* 播放器在页面级常驻：翻篇只换题目内容，不重新加载音频、不回到 0 秒 */}
      <AudioPlayer examPaperId={paper.examPaperId} fallbackDurationMs={paper.durationMs} sticky />

      <Card>
        {!current ? (
          <Empty description="该试卷暂无题目数据" />
        ) : (
          <Space direction="vertical" size={14} style={{ width: '100%' }}>
            <Space size={8} wrap>
              <Tag color="blue">第 {current.passageIndex} 篇</Tag>
              <Tag>{current.passageType}</Tag>
              <Typography.Text strong>{current.topic || '—'}</Typography.Text>
            </Space>

            {current.questions.length === 0 ? (
              <Empty description="该篇章暂无题目" />
            ) : (
              current.questions.map((question) => (
                <div key={question.questionId} className="question-card">
                  <div className="question-head">
                    <Typography.Text strong>第 {question.questionNo} 题</Typography.Text>
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
              ))
            )}

            <div className="passage-pager">
              <Button
                disabled={passageIndex <= 0}
                onClick={() => setPassageIndex((index) => Math.max(0, index - 1))}
              >
                上一篇
              </Button>
              <Typography.Text type="secondary">
                第 {current.passageIndex} 篇 / 共 {total} 篇
              </Typography.Text>
              <Button
                type="primary"
                disabled={passageIndex >= total - 1}
                onClick={() => setPassageIndex((index) => Math.min(total - 1, index + 1))}
              >
                下一篇
              </Button>
            </div>
          </Space>
        )}
      </Card>
    </Space>
  )
}
