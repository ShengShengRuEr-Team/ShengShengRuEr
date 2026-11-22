import { useEffect, useState } from 'react'
import {
  Alert, Button, Card, Drawer, Empty, Pagination, Popconfirm, Radio, Select, Space, Spin, Tag, Typography,
} from 'antd'
import { Link } from 'react-router-dom'
import { ApiError } from '../../api/api-error'
import { loadAuthenticatedAudio } from '../../api/audio'
import type { AudioSource } from '../../api/audio'
import { getListeningPapers } from '../../api/listening'
import {
  getWrongAnswer, listWrongAnswers, updateWrongAnswer, WRONG_ANSWER_PAGE_SIZE,
} from '../../api/wrong-answers'
import type {
  WrongAnswerChange, WrongAnswerDetail, WrongAnswerFilters, WrongAnswerItem, WrongAnswerLearningStatus,
} from '../../api/wrong-answers'
import { ROUTES } from '../../constants/routes'
import { formatDateTime, formatPaperLabel } from '../../utils/format'

const { Paragraph, Text, Title } = Typography

function ReviewAudio({ path }: { path: string }) {
  const [requested, setRequested] = useState(false)
  const [url, setUrl] = useState<string>()
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!requested) return

    const controller = new AbortController()
    let source: AudioSource | undefined
    loadAuthenticatedAudio(path, controller.signal)
      .then((loaded) => {
        if (controller.signal.aborted) {
          loaded.release()
          return
        }
        source = loaded
        setUrl(loaded.objectUrl)
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setError(true)
          setRequested(false)
        }
      })
    return () => {
      controller.abort()
      source?.release()
    }
  }, [path, requested])

  if (url) return <audio controls src={url} aria-label="听力音频" />

  return (
    <Space wrap>
      <Button loading={requested} onClick={() => { setError(false); setRequested(true) }}>
        {error ? '重新加载音频' : '加载音频'}
      </Button>
      {error && <Text type="danger">音频加载失败</Text>}
    </Space>
  )
}

const skillRoleLabels: Record<string, string> = { PRIMARY: '主要技能', AUXILIARY: '辅助技能' }
const learningStatusLabels: Record<WrongAnswerLearningStatus, string> = {
  pending: '待复习',
  mastered: '已掌握',
}

function RestrictedEvidence({ present }: { present: boolean }) {
  return present ? <Paragraph type="secondary">存在受限证据，暂不可查看</Paragraph> : null
}

function ReviewContent({ detail }: { detail: WrongAnswerDetail }) {
  return (
    <>
      <Space wrap>
        <Text type="secondary">{detail.paper_title}</Text>
        <Tag>{detail.snapshot_note}</Tag>
      </Space>
      <Title level={4}>{detail.question_text || `第 ${detail.question_no} 题`}</Title>
      {Object.entries(detail.options).map(([letter, text]) => (
        <Paragraph key={letter}>
          {letter}. {text}{' '}
          {letter === detail.selected_option && <Tag color="red">我的作答</Tag>}
          {letter === detail.correct_option && <Tag color="green">正确答案</Tag>}
        </Paragraph>
      ))}
      <Paragraph>我的作答：{detail.selected_option ?? '未作答'}　正确答案：{detail.correct_option}</Paragraph>
      <Title level={5}>解析</Title>
      <Paragraph>{detail.explanation_text || '暂无解析'}</Paragraph>
      <Title level={5}>听力音频</Title>
      {detail.audio_url
        ? <ReviewAudio key={detail.audio_url} path={detail.audio_url} />
        : <Paragraph>暂无音频</Paragraph>}
      <Title level={5}>关联技能</Title>
      {detail.skills.length === 0 && <Paragraph>暂无技能标注</Paragraph>}
      {detail.skills.map((skill, index) => (
        <div key={`${skill.code}-${index}`}>
          <Text strong>{skill.name}（{skill.code}）</Text>{' '}
          {skill.role && <Tag>{skillRoleLabels[skill.role] ?? skill.role}</Tag>}
          <RestrictedEvidence present={skill.has_restricted_evidence} />
        </div>
      ))}
      <Title level={5}>候选错因</Title>
      {detail.candidate_causes.length === 0 && (
        <Paragraph>{detail.selected_option ? '当次所选答案暂无可展示的候选错因' : '本题当次未作答'}</Paragraph>
      )}
      {detail.candidate_causes.map((cause, index) => (
        <div key={`${cause.code}-${index}`}>
          <Text strong>{cause.name}（{cause.code}）</Text>{' '}
          <Tag>选项 {cause.option_letter}</Tag>
          <RestrictedEvidence present={cause.has_restricted_evidence} />
        </div>
      ))}
      <Title level={5}>个人错因</Title>
      <Paragraph>未确认</Paragraph>
    </>
  )
}

type DetailState =
  | { kind: 'loading' }
  | { kind: 'ready'; detail: WrongAnswerDetail }
  | { kind: 'unavailable' }
  | { kind: 'closed' }
  | { kind: 'error'; message: string }

function EntryDrawer({ item, onClose, onUnavailable }: {
  item: WrongAnswerItem
  onClose: () => void
  onUnavailable: () => void
}) {
  const [state, setState] = useState<DetailState>({ kind: 'loading' })
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setState({ kind: 'loading' })
    getWrongAnswer(item, controller.signal)
      .then((detail) => {
        if (!controller.signal.aborted) setState({ kind: 'ready', detail })
      })
      .catch((failure: unknown) => {
        if (controller.signal.aborted) return
        if (failure instanceof ApiError && failure.status === 404) {
          setState({ kind: 'unavailable' })
        } else if (failure instanceof ApiError && failure.status === 503 && failure.message === '错题详情暂未开放') {
          setState({ kind: 'closed' })
        } else {
          setState({ kind: 'error', message: failure instanceof Error ? failure.message : '错题详情加载失败' })
        }
      })
    return () => controller.abort()
  }, [item, retry])

  return (
    <Drawer title={`第 ${item.question_no} 题 · 错题详情`} size="large" open onClose={onClose}>
      {state.kind === 'loading' && <Spin aria-label="加载错题详情" />}
      {state.kind === 'ready' && <ReviewContent detail={state.detail} />}
      {state.kind === 'closed' && <Alert showIcon type="info" title="错题详情暂未开放" />}
      {state.kind === 'unavailable' && (
        <Alert
          showIcon
          type="warning"
          title="该错题记录已不可查看"
          action={<Button onClick={onUnavailable}>返回列表</Button>}
        />
      )}
      {state.kind === 'error' && (
        <Alert showIcon type="error" title={state.message} action={<Button onClick={() => setRetry(retry + 1)}>重试</Button>} />
      )}
    </Drawer>
  )
}

function WrongAnswerCard({ item, saving, writesEnabled, onView, onUpdate }: {
  item: WrongAnswerItem
  saving: boolean
  writesEnabled: boolean
  onView: () => void
  onUpdate: (change: WrongAnswerChange) => Promise<void>
}) {
  const mastered = item.learning_status === 'mastered'

  return (
    <Card size="small">
      <Text type="secondary">
        {item.paper_title} · 第 {item.question_no} 题 · {formatDateTime(item.submitted_at)}
      </Text>
      <Paragraph style={{ marginTop: 8 }}>{item.question_text || `第 ${item.question_no} 题`}</Paragraph>
      <Space wrap>
        <Tag color={item.selected_option ? 'red' : 'default'}>
          {item.selected_option ? `选了 ${item.selected_option}` : '未作答'}
        </Tag>
        <Tag color={mastered ? 'green' : 'default'}>{learningStatusLabels[item.learning_status]}</Tag>
        {!item.is_hidden && <Button type="primary" onClick={onView}>查看详情</Button>}
        {writesEnabled && (item.is_hidden ? (
          <Button disabled={saving} onClick={() => void onUpdate({ is_hidden: false })}>恢复</Button>
        ) : (
          <>
            <Button
              disabled={saving}
              onClick={() => void onUpdate({ learning_status: mastered ? 'pending' : 'mastered' })}
            >
              {mastered ? '重新标记待复习' : '标记已掌握'}
            </Button>
            <Popconfirm
              title="隐藏这条错题记录？"
              description="可在「已隐藏」中恢复，复习状态会保留。"
              okText="确认隐藏"
              cancelText="取消"
              onConfirm={() => onUpdate({ is_hidden: true })}
              disabled={saving}
            >
              <Button disabled={saving}>隐藏</Button>
            </Popconfirm>
          </>
        ))}
      </Space>
    </Card>
  )
}

export default function WrongAnswersPage() {
  const [filters, setFilters] = useState<WrongAnswerFilters>({ visibility: 'visible' })
  const [paperOptions, setPaperOptions] = useState<{ value: number; label: string }[]>([])
  const [paperOptionsUnavailable, setPaperOptionsUnavailable] = useState(false)
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [items, setItems] = useState<WrongAnswerItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [writesEnabled, setWritesEnabled] = useState<boolean>()
  const [error, setError] = useState('')
  const [mutationError, setMutationError] = useState('')
  const [selected, setSelected] = useState<WrongAnswerItem>()
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    getListeningPapers({ signal: controller.signal })
      .then((papers) => {
        if (controller.signal.aborted) return
        setPaperOptions(papers.map((paper) => ({
          value: paper.examPaperId,
          label: `${paper.level} ${formatPaperLabel(paper.year, paper.month, paper.paperSet)}`,
        })))
      })
      .catch(() => { if (!controller.signal.aborted) setPaperOptionsUnavailable(true) })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    listWrongAnswers(filters, page, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        const lastPage = Math.max(1, Math.ceil(data.total / WRONG_ANSWER_PAGE_SIZE))
        if (page > lastPage) {
          setPage(lastPage)
          return
        }
        setItems(data.items)
        setTotal(data.total)
        setWritesEnabled(data.state_writes_enabled)
        setLoading(false)
      })
      .catch((failure: unknown) => {
        if (controller.signal.aborted) return
        setError(failure instanceof Error ? failure.message : '错题列表加载失败')
        setLoading(false)
      })
    return () => controller.abort()
  }, [filters, page, revision])

  function changeFilters(change: Partial<WrongAnswerFilters>) {
    setFilters((previous) => ({ ...previous, ...change }))
    setMutationError('')
    setPage(1)
  }

  function refresh() {
    setRevision((value) => value + 1)
  }

  async function changeItem(item: WrongAnswerItem, change: WrongAnswerChange) {
    setSaving(true)
    setMutationError('')
    try {
      await updateWrongAnswer(item, change)
      refresh()
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 404) {
        setMutationError('该错题记录已不可查看')
        refresh()
      } else if (failure instanceof ApiError && failure.status === 503 && failure.message === '错题管理暂未开放') {
        setWritesEnabled(false)
      } else {
        setMutationError(failure instanceof Error ? failure.message : '错题更新失败，请重试')
      }
    } finally {
      setSaving(false)
    }
  }

  const isFiltered = filters.exam_paper_id !== undefined || filters.answer_type || filters.learning_status
  const emptyText = isFiltered
    ? '没有符合筛选条件的错题'
    : filters.visibility === 'hidden' ? '暂无已隐藏的错题' : '暂无错题'

  return (
    <section aria-labelledby="wrong-answers-heading" style={{ maxWidth: 960, margin: '0 auto' }}>
      <div className="page-header">
        <Title id="wrong-answers-heading" level={2} style={{ margin: 0 }}>错题本</Title>
        <Link to={ROUTES.STUDENT_LISTENING_PAPERS}>返回听力练习</Link>
      </div>
      <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
        <Space wrap>
          <Radio.Group
            aria-label="错题显示范围"
            value={filters.visibility}
            options={[
              { label: '错题', value: 'visible' },
              { label: '已隐藏', value: 'hidden' },
            ]}
            onChange={(event) => changeFilters({ visibility: event.target.value })}
          />
          <Select<number>
            aria-label="按试卷筛选"
            allowClear
            disabled={paperOptionsUnavailable}
            placeholder={paperOptionsUnavailable ? '试卷筛选暂不可用' : '全部试卷'}
            value={filters.exam_paper_id}
            options={paperOptions}
            style={{ minWidth: 170 }}
            onChange={(exam_paper_id) => changeFilters({ exam_paper_id })}
          />
          <Select<WrongAnswerFilters['answer_type']>
            aria-label="按错题类型筛选"
            allowClear
            placeholder="全部错题类型"
            value={filters.answer_type}
            options={[
              { label: '答错', value: 'incorrect' },
              { label: '未作答', value: 'unanswered' },
            ]}
            style={{ minWidth: 128 }}
            onChange={(answer_type) => changeFilters({ answer_type })}
          />
          <Select<WrongAnswerLearningStatus | undefined>
            aria-label="按复习状态筛选"
            allowClear
            placeholder="全部复习状态"
            value={filters.learning_status}
            options={[
              { label: learningStatusLabels.pending, value: 'pending' },
              { label: learningStatusLabels.mastered, value: 'mastered' },
            ]}
            style={{ minWidth: 128 }}
            onChange={(learning_status) => changeFilters({ learning_status })}
          />
        </Space>
        {writesEnabled === false && <Alert showIcon type="info" title="错题管理暂未开放" />}
        {mutationError && <Alert showIcon type="warning" title={mutationError} />}
        {error ? (
          <Alert showIcon type="error" title={error} action={<Button onClick={refresh}>重试</Button>} />
        ) : loading ? <Spin aria-label="加载错题列表" /> : items.length === 0 ? (
          <Empty description={emptyText} />
        ) : (
          <>
            {items.map((item) => (
              <WrongAnswerCard
                key={`${item.attempt_code}-${item.question_no}`}
                item={item}
                saving={saving}
                writesEnabled={writesEnabled === true}
                onView={() => setSelected(item)}
                onUpdate={(change) => changeItem(item, change)}
              />
            ))}
            <Pagination
              current={page}
              pageSize={WRONG_ANSWER_PAGE_SIZE}
              total={total}
              showSizeChanger={false}
              onChange={setPage}
            />
          </>
        )}
      </Space>
      {selected && (
        <EntryDrawer
          item={selected}
          onClose={() => setSelected(undefined)}
          onUnavailable={() => {
            setSelected(undefined)
            refresh()
          }}
        />
      )}
    </section>
  )
}
