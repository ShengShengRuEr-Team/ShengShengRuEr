import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Collapse,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd'
import { ApiError } from '../../../api/api-error'
import { getQuestionDetail } from '../../../api/skill-error-query'
import type {
  EvidenceView,
  QuestionDetailData,
} from '../../../api/skill-error-query'
import AudioPlayer from '../../../ui/AudioPlayer'

interface QuestionDetailDrawerProps {
  open: boolean
  questionId: number | null
  scopeVersion: string
  onClose: () => void
  onScopeRefresh: () => void
}

function EvidenceBlock({ evidence }: { evidence: EvidenceView[] }) {
  if (evidence.length === 0) {
    return <Typography.Text type="secondary">无证据记录</Typography.Text>
  }
  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      {evidence.map((item) => (
        <div key={item.evidence_id} className="skill-query-evidence">
          <Typography.Text type="secondary">
            {item.source} · {item.start_ms}–{item.end_ms} ms
          </Typography.Text>
          <Typography.Paragraph style={{ marginBottom: 0 }}>{item.text}</Typography.Paragraph>
          {item.support_note ? (
            <Typography.Text type="secondary">说明：{item.support_note}</Typography.Text>
          ) : null}
        </div>
      ))}
    </Space>
  )
}

export default function QuestionDetailDrawer({
  open,
  questionId,
  scopeVersion,
  onClose,
  onScopeRefresh,
}: QuestionDetailDrawerProps) {
  const [data, setData] = useState<QuestionDetailData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [paperId, setPaperId] = useState<number | undefined>()
  const [retryNonce, setRetryNonce] = useState(0)

  useEffect(() => {
    if (!open || questionId === null) {
      setData(null)
      setError('')
      setPaperId(undefined)
      return
    }
    let cancelled = false
    setLoading(true)
    setError('')
    getQuestionDetail(questionId, {
      expectedScopeVersion: scopeVersion,
      examPaperId: paperId,
    })
      .then((detail) => {
        if (cancelled) return
        setData(detail)
        setPaperId(detail.paper.exam_paper_id)
      })
      .catch((reason: unknown) => {
        if (cancelled) return
        if (reason instanceof ApiError && reason.status === 409) {
          onScopeRefresh()
          onClose()
          return
        }
        if (reason instanceof ApiError && reason.status === 404) {
          onClose()
          onScopeRefresh()
          return
        }
        setError(reason instanceof Error ? reason.message : '题目详情加载失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, questionId, scopeVersion, paperId, retryNonce, onClose, onScopeRefresh])

  const title = data
    ? `第 ${data.paper.question_no} 题 · ${data.paper.exam_paper_code}`
    : '题目详情'

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={920}
      title={
        <Space wrap>
          <Typography.Text strong>{title}</Typography.Text>
          <Tag color="green">正式数据</Tag>
          {data?.paper.paper_count && data.paper.paper_count > 1 ? (
            <Tag color="blue">共 {data.paper.paper_count} 套试卷引用</Tag>
          ) : null}
        </Space>
      }
    >
      {loading ? (
        <div className="skill-query-center">
          <Spin /> 正在加载题目详情…
        </div>
      ) : error ? (
        <Alert
          type="error"
          showIcon
          message="题目详情加载失败"
          description={error}
          action={
            <Button size="small" onClick={() => setRetryNonce((value) => value + 1)}>
              重试
            </Button>
          }
        />
      ) : !data ? (
        <Empty description="请选择题目" />
      ) : (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          {data.paper.paper_count > 1 ? (
            <Space>
              <Typography.Text>试卷上下文</Typography.Text>
              <Select
                value={paperId}
                style={{ minWidth: 220 }}
                options={data.papers.map((paper) => ({
                  value: paper.exam_paper_id,
                  label: `${paper.exam_paper_code}（第 ${paper.question_no} 题）`,
                }))}
                onChange={(value) => setPaperId(value)}
              />
              <Typography.Text type="secondary">
                切换只改变展示字母和顺序，题库基准字母与候选身份不变
              </Typography.Text>
            </Space>
          ) : null}

          {data.answer_state === 'unavailable' ? (
            <Alert type="warning" showIcon message="答案待补齐，无法确认错误选项" />
          ) : null}
          {data.warnings.map((warning) => (
            <Alert key={warning.code} type="warning" showIcon message={warning.message} />
          ))}

          {data.paper.audio_url ? (
            <div className="skill-query-audio">
              <AudioPlayer
                examPaperId={data.paper.exam_paper_id}
                expectedBatchId={data.paper.audio_batch_id ?? undefined}
                fallbackDurationMs={data.paper.duration_ms}
              />
            </div>
          ) : (
            <Alert type="info" showIcon message="音频不可用" />
          )}

          <Typography.Paragraph strong>{data.question.text}</Typography.Paragraph>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            {data.options.map((option) => {
              const correct =
                data.correct_option?.display_letter === option.display_letter &&
                data.correct_option?.base_letter === option.base_letter
              return (
                <div
                  key={option.display_letter}
                  className={`skill-query-option${correct ? ' is-correct' : ''}`}
                >
                  <Tag color={correct ? 'green' : 'default'}>{option.display_letter}</Tag>
                  <Typography.Text>{option.text}</Typography.Text>
                  {correct ? <Tag color="green">正确答案</Tag> : null}
                </div>
              )
            })}
          </Space>

          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="题目代码">{data.question.code}</Descriptions.Item>
            <Descriptions.Item label="标注状态">
              <Tag color="green">正式审核通过</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="答案状态">
              {data.answer_state === 'available' ? '可用' : '待补齐'}
            </Descriptions.Item>
            <Descriptions.Item label="选项映射">
              {data.paper.option_mapping_state}
            </Descriptions.Item>
            <Descriptions.Item label="解析来源">{data.question.explanation_source}</Descriptions.Item>
            <Descriptions.Item label="内容状态">
              {data.question.content_state} / {data.question.review_status}
            </Descriptions.Item>
          </Descriptions>

          <div>
            <Typography.Title level={5}>解析</Typography.Title>
            <Typography.Paragraph>{data.question.explanation_text || '暂无解析'}</Typography.Paragraph>
          </div>

          <div>
            <Typography.Title level={5}>原文与证据</Typography.Title>
            {data.passage ? (
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Typography.Text type="secondary">
                  {data.passage.topic} · {data.passage.passage_type}
                </Typography.Text>
                {data.passage.segments.map((segment) => (
                  <div key={segment.segment_id} className="skill-query-segment">
                    <Typography.Text type="secondary">
                      {segment.start_ms}–{segment.end_ms} ms
                      {segment.speaker_code ? ` · ${segment.speaker_code}` : ''}
                    </Typography.Text>
                    <Typography.Paragraph style={{ marginBottom: 0 }}>
                      {segment.text}
                    </Typography.Paragraph>
                  </div>
                ))}
              </Space>
            ) : (
              <Typography.Text type="secondary">原文不可用</Typography.Text>
            )}
            <Divider />
            <Typography.Title level={5}>答案证据</Typography.Title>
            <EvidenceBlock evidence={data.answer_evidence} />
          </div>

          <div>
            <Typography.Title level={5}>技能标注</Typography.Title>
            <Collapse
              items={data.skills.map((skill) => ({
                key: skill.code,
                label: (
                  <Space wrap>
                    <Tag color={skill.role === 'PRIMARY' ? 'blue' : 'default'}>
                      {skill.role === 'PRIMARY' ? '主要' : '辅助'}
                    </Tag>
                    <Typography.Text code>{skill.code}</Typography.Text>
                    <Typography.Text>{skill.name}</Typography.Text>
                    <Tag>{skill.evidence.length} 条证据</Tag>
                  </Space>
                ),
                children: (
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Typography.Paragraph>{skill.definition}</Typography.Paragraph>
                    <EvidenceBlock evidence={skill.evidence} />
                  </Space>
                ),
              }))}
            />
          </div>

          <div>
            <Typography.Title level={5}>题目候选错因</Typography.Title>
            <Typography.Paragraph type="secondary">
              以下是题目层面的错误选项候选原因，不是学生已确认的个人错因。
            </Typography.Paragraph>
            {data.error_options.length === 0 ? (
              <Typography.Text type="secondary">暂无可展示的错误选项候选错因</Typography.Text>
            ) : (
              <Collapse
                defaultActiveKey={data.error_options.map((option) => option.base_letter)}
                items={data.error_options.map((option) => ({
                  key: option.base_letter,
                  label: (
                    <Space wrap>
                      <Tag color="volcano">
                        {option.display_letter ?? option.base_letter}
                        {option.display_letter && option.display_letter !== option.base_letter
                          ? `（基准 ${option.base_letter}）`
                          : ''}
                      </Tag>
                      <Typography.Text>{option.text}</Typography.Text>
                      <Tag>{option.candidate_causes.length} 个候选</Tag>
                    </Space>
                  ),
                  children: (
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                      {option.candidate_causes.map((cause) => (
                        <div key={cause.code}>
                          <Space wrap>
                            <Tag color="orange">{cause.code}</Tag>
                            <Typography.Text strong>{cause.name}</Typography.Text>
                            <Typography.Text type="secondary">
                              {cause.rationale || '未填写候选理由'}
                            </Typography.Text>
                          </Space>
                          <EvidenceBlock evidence={cause.evidence} />
                        </div>
                      ))}
                    </Space>
                  ),
                }))}
              />
            )}
          </div>

          <Alert
            type="info"
            showIcon
            message="个人错因"
            description={data.personal_error.message}
          />
        </Space>
      )}
    </Drawer>
  )
}
