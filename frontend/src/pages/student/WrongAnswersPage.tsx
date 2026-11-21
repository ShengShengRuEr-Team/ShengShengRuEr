import { useEffect, useState } from 'react'
import {
  Alert, Button, Card, Drawer, Empty, Input, Pagination, Popconfirm, Space, Spin, Tag, Typography,
} from 'antd'
import {
  dismissWrongAnswer, getWrongAnswer, listWrongAnswers,
} from '../../api/wrong-answers'
import type { WrongAnswerDetail, WrongAnswerItem } from '../../api/wrong-answers'
import { loadAuthenticatedAudio } from '../../api/audio'
import type { AudioSource } from '../../api/audio'
import { showError } from '../../ui/message'

const { Paragraph, Text, Title } = Typography
const skillRoleLabels: Record<string, string> = { PRIMARY: '主要技能', AUXILIARY: '辅助技能' }

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

function Evidence({ evidence }: { evidence: WrongAnswerDetail['skills'][number]['evidence'] }) {
  if (!evidence.length) return null
  return (
    <ul>
      {evidence.map(({ text, note }, index) => (
        <li key={index}>{text}{note && <div><Text type="secondary">{note}</Text></div>}</li>
      ))}
    </ul>
  )
}

function ReviewContent({ detail }: { detail: WrongAnswerDetail }) {
  return (
    <>
      <Text type="secondary">{detail.paper_title}</Text>
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
      <Title level={5}>听力材料</Title>
      {detail.audio_url && <ReviewAudio key={detail.audio_url} path={detail.audio_url} />}
      {detail.transcript.map((line, index) => <Paragraph key={index}>{line}</Paragraph>)}
      {!detail.audio_url && !detail.transcript.length && <Paragraph>暂无配套材料</Paragraph>}
      <Title level={5}>关联技能</Title>
      {detail.skills.length === 0 && <Paragraph>暂无技能标注</Paragraph>}
      {detail.skills.map((skill, index) => (
        <div key={`${skill.code}-${index}`}>
          <Text strong>{skill.name}（{skill.code}）</Text>{' '}
          {skill.role && <Tag>{skillRoleLabels[skill.role] ?? skill.role}</Tag>}
          {skill.reason && <Paragraph>{skill.reason}</Paragraph>}
          <Evidence evidence={skill.evidence} />
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
          {cause.reason && <Paragraph>{cause.reason}</Paragraph>}
          <Evidence evidence={cause.evidence} />
        </div>
      ))}
      <Title level={5}>个人错因</Title>
      <Paragraph>未确认</Paragraph>
    </>
  )
}

function EntryDrawer({ item, onClose }: { item: WrongAnswerItem; onClose: () => void }) {
  const [detail, setDetail] = useState<WrongAnswerDetail>()
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setError('')
    getWrongAnswer(item, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setDetail(data) })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) {
          setError(failure instanceof Error ? failure.message : '错题详情加载失败')
        }
      })
    return () => controller.abort()
  }, [item, retry])

  return (
    <Drawer title={`第 ${item.question_no} 题 · 错题详情`} size="large" open onClose={onClose}>
      {error ? (
        <Alert type="error" title={error} action={<Button onClick={() => setRetry(retry + 1)}>重试</Button>} />
      ) : detail ? <ReviewContent detail={detail} /> : <Spin />}
    </Drawer>
  )
}

export default function WrongAnswersPage() {
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [items, setItems] = useState<WrongAnswerItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<WrongAnswerItem>()
  const [removing, setRemoving] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    listWrongAnswers(keyword, page, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        const lastPage = Math.max(1, Math.ceil(data.total / 20))
        if (page > lastPage) {
          setPage(lastPage)
          return
        }
        setItems(data.items)
        setTotal(data.total)
        setLoading(false)
      })
      .catch((failure: unknown) => {
        if (controller.signal.aborted) return
        setError(failure instanceof Error ? failure.message : '错题列表加载失败')
        setLoading(false)
      })
    return () => controller.abort()
  }, [keyword, page, revision])

  async function remove(item: WrongAnswerItem) {
    setRemoving(true)
    try {
      await dismissWrongAnswer(item)
      setRevision((value) => value + 1)
    } catch (failure) {
      showError(failure instanceof Error ? failure.message : '移除失败，请重试')
    } finally {
      setRemoving(false)
    }
  }

  return (
    <section aria-labelledby="wrong-answers-heading" style={{ maxWidth: 960, margin: '0 auto' }}>
      <Title id="wrong-answers-heading" level={2}>错题本</Title>
      <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
        <Input.Search
          aria-label="搜索错题"
          placeholder="搜索题干、考试级别或试卷编号"
          allowClear
          maxLength={100}
          onSearch={(value) => { setKeyword(value.trim()); setPage(1) }}
          style={{ maxWidth: 440 }}
        />
        {error ? (
          <Alert type="error" title={error} action={<Button onClick={() => setRevision(revision + 1)}>重试</Button>} />
        ) : loading ? <Spin /> : items.length === 0 ? (
          <Empty description={keyword ? '没有匹配的错题' : '暂无错题'} />
        ) : (
          <>
            {items.map((item) => (
              <Card key={`${item.attempt_code}-${item.question_no}`} size="small">
                <Text type="secondary">
                  {item.paper_title} · 第 {item.question_no} 题 · {new Date(item.submitted_at).toLocaleString('zh-CN')}
                </Text>
                <Paragraph style={{ marginTop: 8 }}>{item.question_text || `第 ${item.question_no} 题`}</Paragraph>
                <Space wrap>
                  <Tag color={item.selected_option ? 'red' : 'default'}>
                    {item.selected_option ? `选了 ${item.selected_option}` : '未作答'}
                  </Tag>
                  <Button type="primary" onClick={() => setSelected(item)}>查看详情</Button>
                  <Popconfirm
                    title="移出这条错题记录？"
                    okText="移出"
                    cancelText="取消"
                    onConfirm={() => remove(item)}
                    disabled={removing}
                  >
                    <Button danger disabled={removing}>移出错题本</Button>
                  </Popconfirm>
                </Space>
              </Card>
            ))}
            <Pagination current={page} pageSize={20} total={total} showSizeChanger={false} onChange={setPage} />
          </>
        )}
      </Space>
      {selected && <EntryDrawer item={selected} onClose={() => setSelected(undefined)} />}
    </section>
  )
}
