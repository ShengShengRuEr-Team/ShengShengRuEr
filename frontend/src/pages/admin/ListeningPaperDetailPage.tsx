import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeftOutlined, ReloadOutlined, SoundOutlined } from '@ant-design/icons'
import {
  Alert,
  App as AntdApp,
  Button,
  Card,
  Descriptions,
  Drawer,
  Empty,
  Input,
  Modal,
  Select,
  Skeleton,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { Link, useLocation, useParams } from 'react-router-dom'
import type { AdminPassage, ContentCheck, PaperCompanion } from '../../api/adapters'
import { getAdminCompanion, getContentCheck, setPaperVisibility } from '../../api/listening'
import { ApiError } from '../../api/api-error'
import type { VisibilityAction } from '../../api/types'
import { ROUTES } from '../../constants/routes'
import AudioPlayer from '../../ui/AudioPlayer'
import {
  AccessTag,
  BatchTag,
  CheckTag,
  CheckedAtText,
  ContentStateTag,
  ReviewStatusTag,
  VisibilityTag,
} from '../../ui/PaperStatusTags'
import {
  formatContentScope,
  formatDateTime,
  formatDuration,
  formatTimeRange,
} from '../../utils/format'

const { TextArea } = Input

export default function AdminListeningPaperDetailPage() {
  const { examPaperId } = useParams()
  const location = useLocation()
  const paperId = Number(examPaperId)

  // 返回列表时带回进入本页时的筛选条件（列表把筛选放在 URL 上）。
  const listSearch = (location.state as { listSearch?: string } | null)?.listSearch ?? ''
  const backToList = `${ROUTES.ADMIN_LISTENING_PAPERS}${listSearch}`
  const { message } = AntdApp.useApp()

  const [companion, setCompanion] = useState<PaperCompanion | null>(null)
  const [check, setCheck] = useState<ContentCheck | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [checkError, setCheckError] = useState<string | null>(null)
  const [currentPassageId, setCurrentPassageId] = useState<number | null>(null)
  const [checkDrawerOpen, setCheckDrawerOpen] = useState(false)
  const [playerOpen, setPlayerOpen] = useState(false)
  const [modalAction, setModalAction] = useState<VisibilityAction | null>(null)
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const leftBodyRef = useRef<HTMLDivElement | null>(null)
  const rightBodyRef = useRef<HTMLDivElement | null>(null)

  const fetchData = useCallback(async () => {
    if (!Number.isFinite(paperId)) {
      setError('试卷 ID 无效')
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)
    setCheckError(null)

    const [companionResult, checkResult] = await Promise.allSettled([
      getAdminCompanion(paperId),
      getContentCheck(paperId),
    ])

    if (companionResult.status === 'fulfilled') {
      const data = companionResult.value
      setCompanion(data)
      setCurrentPassageId((prev) => {
        if (prev !== null && data.passages.some((passage) => passage.passageId === prev)) {
          return prev
        }
        return data.passages[0]?.passageId ?? null
      })
    } else {
      const reason = companionResult.reason
      setCompanion(null)
      setError(
        reason instanceof ApiError && reason.status === 404
          ? '试卷不存在'
          : reason instanceof Error
            ? reason.message
            : '试卷详情加载失败',
      )
    }

    if (checkResult.status === 'fulfilled') {
      setCheck(checkResult.value)
    } else {
      setCheck(null)
      setCheckError(
        checkResult.reason instanceof Error ? checkResult.reason.message : '检查结果加载失败',
      )
    }

    setLoading(false)
  }, [paperId])

  useEffect(() => {
    void fetchData()
  }, [fetchData])

  // 切换篇章时两栏各自回到顶部，避免停留在上一篇的滚动位置。
  useEffect(() => {
    if (leftBodyRef.current) {
      leftBodyRef.current.scrollTop = 0
    }
    if (rightBodyRef.current) {
      rightBodyRef.current.scrollTop = 0
    }
  }, [currentPassageId])

  const currentPassage: AdminPassage | null = useMemo(() => {
    if (!companion || companion.passages.length === 0) {
      return null
    }
    return (
      companion.passages.find((passage) => passage.passageId === currentPassageId) ??
      companion.passages[0]
    )
  }, [companion, currentPassageId])

  const hasBatch = Boolean(companion?.batchCode)
  const isVisible = companion?.isVisible ?? false
  // 以最近一次检查记录为准；checks 未取到时才退回 companion 的快照，避免页头与页内结论不一致。
  const checkPassed = check ? check.isPassed : (companion?.checkPassed ?? false)
  const accessible = Boolean(companion?.isCurrent && checkPassed && isVisible)

  const confirmDisabledReason = !hasBatch
    ? '暂无当前批次，无法操作'
    : isVisible
      ? '该试卷已确认开放'
      : !checkPassed
        ? '检查未通过或尚未检查，不能确认开放'
        : ''

  const openActionModal = (action: VisibilityAction) => {
    setReason('')
    setModalAction(action)
  }

  const submitAction = async () => {
    if (!companion || !modalAction) {
      return
    }
    setSubmitting(true)
    try {
      await setPaperVisibility(companion.examPaperId, modalAction, reason.trim())
      message.success(modalAction === 'confirm' ? '已确认学生可见' : '已取消学生可见')
      setModalAction(null)
      setReason('')
      await fetchData()
    } catch (actionError) {
      message.error(actionError instanceof Error ? actionError.message : '操作失败')
      setModalAction(null)
      // 确认失败时后端会留下一条新的失败检查记录，这里必须重读，否则页面显示旧结论。
      try {
        setCheck(await getContentCheck(companion.examPaperId))
        setCheckError(null)
      } catch {
        setCheckError('检查结果刷新失败，请手动刷新页面')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <Card>
        <Skeleton active paragraph={{ rows: 8 }} />
      </Card>
    )
  }

  if (error || !companion) {
    return (
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Link to={backToList}>
          <ArrowLeftOutlined /> 返回题库管理
        </Link>
        <Alert
          type="error"
          showIcon
          message="无法加载试卷详情"
          description={error ?? '未知错误'}
          action={
            <Button size="small" onClick={() => void fetchData()}>
              重试
            </Button>
          }
        />
      </Space>
    )
  }

  const checkHint = checkError
    ? checkError
    : check?.isPassed
      ? '检查通过，可确认开放。'
      : check && check.issues.length > 0
        ? '检查未通过。请先处理下列问题；处理完成后需由导入/检查流程重新生成检查记录。'
        : '尚未检查。本页只能读取检查记录，不能重新执行检查。'

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div className="breadcrumb-row">
        <Link to={backToList}>
          <ArrowLeftOutlined /> 返回题库管理
        </Link>
        <Button icon={<ReloadOutlined />} size="small" onClick={() => void fetchData()}>
          刷新
        </Button>
      </div>

      <Card>
        <div className="page-header" style={{ marginBottom: 8 }}>
          <Space direction="vertical" size={6}>
            <Space size={8} wrap>
              <Typography.Title level={4} style={{ margin: 0 }}>
                {companion.code}
              </Typography.Title>
              <Tag>{formatContentScope(companion.contentScope)}</Tag>
              <BatchTag hasBatch={hasBatch} />
              {checkError ? (
                <Tag color="red">检查结果读取失败</Tag>
              ) : (
                <CheckTag passed={checkPassed} checkedAt={check?.checkedAt ?? null} />
              )}
              <VisibilityTag visible={isVisible} />
              <ReviewStatusTag status={companion.reviewStatus} />
            </Space>
            <Typography.Text type="secondary">
              {companion.year} 年 {companion.month} 月 · 第 {companion.paperSet} 套 · {companion.level}
              {' · '}
              音频 {formatDuration(companion.durationMs)} · {companion.passages.length} 个篇章
            </Typography.Text>
          </Space>

          <Space wrap>
            <Tooltip title={confirmDisabledReason || undefined}>
              <Button
                type="primary"
                disabled={Boolean(confirmDisabledReason)}
                onClick={() => openActionModal('confirm')}
              >
                确认开放
              </Button>
            </Tooltip>
            <Button disabled={!hasBatch || !isVisible} onClick={() => openActionModal('cancel')}>
              取消开放
            </Button>
            <Button onClick={() => setCheckDrawerOpen(true)}>查看检查结果</Button>
            <Button icon={<SoundOutlined />} onClick={() => setPlayerOpen((open) => !open)}>
              {playerOpen ? '收起试听' : '试听音频'}
            </Button>
          </Space>
        </div>

        <Descriptions
          size="small"
          column={2}
          items={[
            { key: 'batch', label: '批次', children: companion.batchCode ?? '—' },
            { key: 'mapping', label: '映射来源', children: companion.mappingSource || '—' },
            {
              key: 'pending',
              label: '待确认',
              children: companion.isPendingConfirmation ? '是' : '否',
            },
          ]}
        />

        <div className="access-line">
          <Typography.Text type="secondary">当前可访问</Typography.Text>
          <AccessTag accessible={accessible} />
          <Typography.Text type="secondary" className="small-text">
            当前批次 ∧ 检查通过 ∧ 已确认开放；仅代表服务端判定，不代表内容已人工核对
          </Typography.Text>
        </div>

        {!hasBatch && (
          <Alert
            style={{ marginTop: 12 }}
            type="warning"
            showIcon
            message="暂无当前批次"
            description="该试卷当前没有可用的当前批次，配套内容与可见性操作均不可用。"
          />
        )}

        {playerOpen && (
          <div style={{ marginTop: 12 }}>
            <AudioPlayer
              examPaperId={companion.examPaperId}
              fallbackDurationMs={companion.durationMs}
            />
          </div>
        )}
      </Card>

      <Card
        title="最低内容检查"
        extra={
          <Button size="small" onClick={() => setCheckDrawerOpen(true)}>
            查看明细
          </Button>
        }
      >
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <Space size={10} wrap>
            {checkError ? (
              <Tag color="red">检查结果读取失败</Tag>
            ) : (
              <CheckTag passed={check?.isPassed ?? false} checkedAt={check?.checkedAt ?? null} />
            )}
            {checkError ? (
              <Typography.Text type="danger" className="small-text">
                无法读取检查记录，请刷新重试
              </Typography.Text>
            ) : (
              <CheckedAtText checkedAt={check?.checkedAt ?? null} />
            )}
            {check && check.issues.length > 0 && (
              <Tag color="red">{check.issues.length} 个问题</Tag>
            )}
          </Space>
          <Typography.Text type={check?.isPassed ? 'secondary' : 'warning'}>{checkHint}</Typography.Text>
        </Space>
      </Card>

      <div className="detail-columns">
        <Card
          title="篇章原文"
          extra={
            <Select
              value={currentPassage?.passageId}
              style={{ minWidth: 190 }}
              placeholder="选择篇章"
              options={companion.passages.map((passage) => ({
                value: passage.passageId,
                label: `第 ${passage.passageIndex} 篇 · ${passage.passageType}`,
              }))}
              onChange={(value) => setCurrentPassageId(value)}
              disabled={companion.passages.length === 0}
            />
          }
          styles={{ body: { padding: 0 } }}
        >
          {currentPassage ? (
            <div className="passage-panel" ref={leftBodyRef}>
              <div className="passage-meta">
                <Space size={6} wrap>
                  <Tag color="blue">第 {currentPassage.passageIndex} 篇</Tag>
                  <Tag>{currentPassage.passageType}</Tag>
                  <Typography.Text>{currentPassage.topic || '—'}</Typography.Text>
                  <ReviewStatusTag status={currentPassage.reviewStatus} />
                </Space>
                <Typography.Text type="secondary" className="small-text">
                  场景 {currentPassage.scene || '—'} · 口音 {currentPassage.accent || '未判定'} ·{' '}
                  {formatTimeRange(currentPassage.startMs, currentPassage.endMs)}
                  {currentPassage.bodyEndMs !== null &&
                    `（正文至 ${formatDuration(currentPassage.bodyEndMs)}）`}
                </Typography.Text>
              </div>

              <div className="segment-list">
                {currentPassage.segments.length === 0 ? (
                  <Empty description="该篇章暂无原文片段" />
                ) : (
                  currentPassage.segments.map((segment) => (
                    <div
                      key={segment.segmentId}
                      className={
                        segment.segmentType === 'question' ? 'segment-row segment-row--question' : 'segment-row'
                      }
                    >
                      <span className="segment-index">{segment.segmentIndex}</span>
                      <span className="segment-text">
                        {segment.segmentType === 'question' && <Tag color="gold">录音问题</Tag>}
                        {segment.text}
                      </span>
                      <span className="segment-time">
                        {segment.speakerCode} · {formatTimeRange(segment.startMs, segment.endMs)}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          ) : (
            <div className="card-loading">
              <Empty description="暂无当前批次的篇章数据" />
            </div>
          )}
        </Card>

        <Card
          title="题目 · 答案 · 解析"
          extra={
            <Typography.Text type="secondary" className="small-text">
              共 {currentPassage?.questions.length ?? 0} 题
            </Typography.Text>
          }
          styles={{ body: { padding: 0 } }}
        >
          <div className="question-panel" ref={rightBodyRef}>
            {!currentPassage || currentPassage.questions.length === 0 ? (
              <div className="card-loading">
                <Empty description="该篇章暂无题目" />
              </div>
            ) : (
              currentPassage.questions.map((question) => {
                const reordered =
                  Boolean(question.correctOptionBase) &&
                  question.correctOption !== question.correctOptionBase
                return (
                  <div key={question.questionId} className="question-card">
                    <div className="question-head">
                      <Space size={8} wrap>
                        <Typography.Text strong>第 {question.questionNo} 题</Typography.Text>
                        {question.questionIndex !== null &&
                          question.questionIndex !== question.questionNo && (
                            <Typography.Text type="secondary" className="small-text">
                              来源卷第 {question.questionIndex} 题
                            </Typography.Text>
                          )}
                        <ContentStateTag state={question.contentState} />
                        <ReviewStatusTag status={question.reviewStatus} />
                      </Space>
                    </div>

                    <div className="question-text">{question.questionText}</div>

                    <div className="option-list">
                      {question.options.map((option) => (
                        <div key={option.label} className="option-item">
                          <span className="option-key">{option.label}</span>
                          <span>{option.text || '—'}</span>
                        </div>
                      ))}
                    </div>

                    <div className="answer-block">
                      <div className="answer-line">
                        <span className="answer-key">答案</span>
                        <span className="answer-value">{question.correctOption || '—'}</span>
                        {reordered ? (
                          <Tag color="gold">已按本套选项重排 · 题库原答案 {question.correctOptionBase}</Tag>
                        ) : (
                          question.correctOptionBase && (
                            <Typography.Text type="secondary" className="small-text">
                              答案字母一致
                            </Typography.Text>
                          )
                        )}
                      </div>
                      <div className="answer-line">
                        <span className="answer-key">解析</span>
                        <span className="answer-value">{question.explanationText || '暂无解析'}</span>
                      </div>
                      {question.explanationSource && (
                        <Typography.Text type="secondary" className="small-text">
                          来源：{question.explanationSource}
                        </Typography.Text>
                      )}
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </Card>
      </div>

      <Drawer
        title="最低内容检查明细"
        width={480}
        open={checkDrawerOpen}
        onClose={() => setCheckDrawerOpen(false)}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space size={10} wrap>
            {checkError ? (
              <Tag color="red">检查结果读取失败</Tag>
            ) : (
              <CheckTag passed={check?.isPassed ?? false} checkedAt={check?.checkedAt ?? null} />
            )}
            {checkError ? (
              <Typography.Text type="danger" className="small-text">
                无法读取检查记录，请刷新重试
              </Typography.Text>
            ) : (
              <CheckedAtText checkedAt={check?.checkedAt ?? null} />
            )}
          </Space>

          {checkError ? (
            <Alert type="error" showIcon message={checkError} />
          ) : check && check.issues.length > 0 ? (
            <div className="issue-list">
              {check.issues.map((issue, index) => (
                <div key={`${issue.kind}-${index}`} className="issue-row">
                  <Tag color="red">{issue.kind}</Tag>
                  <span>{issue.message}</span>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              description={
                check?.checkedAt ? '本次检查未发现问题' : '尚未检查：本页没有执行检查的能力'
              }
            />
          )}

          <Typography.Text type="secondary" className="small-text">
            刷新只会重新读取最近一次检查记录；重新检查需要由导入/检查流程触发。
          </Typography.Text>
        </Space>
      </Drawer>

      <Modal
        title={modalAction === 'confirm' ? '确认学生可见' : '取消学生可见'}
        open={modalAction !== null}
        onCancel={() => setModalAction(null)}
        onOk={() => void submitAction()}
        okText={modalAction === 'confirm' ? '确认开放' : '确认取消'}
        cancelText="放弃"
        confirmLoading={submitting}
        destroyOnHidden
      >
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Typography.Text>
            {modalAction === 'confirm'
              ? '确认后，满足当前批次与检查通过的条件时，学生即可在列表中看到该试卷。'
              : '取消后，学生重新打开列表将不再看到该试卷，详情与音频请求也会被拒绝。已打开的页面与已下载的音频不会被追回。'}
          </Typography.Text>
          <TextArea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="操作理由（选填，最多 255 字）"
            maxLength={255}
            showCount
            rows={3}
          />
        </Space>
      </Modal>

      <Typography.Text type="secondary" className="small-text">
        页面数据来源：配套内容与检查结果接口；状态展示以接口原值为准，最后读取 {formatDateTime(check?.checkedAt ?? null)}。
      </Typography.Text>
    </Space>
  )
}
