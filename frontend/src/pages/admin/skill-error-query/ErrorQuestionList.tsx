import { useState } from 'react'
import { FileTextOutlined, SoundOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Collapse,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import { ApiError } from '../../../api/api-error'
import { getQuestionDetail } from '../../../api/skill-error-query'
import type {
  ErrorOptionDetail,
  ErrorOptionSummary,
  QuestionDetailData,
  QuestionListItem,
} from '../../../api/skill-error-query'

interface ErrorQuestionListProps {
  items: QuestionListItem[]
  loading?: boolean
  scopeVersion: string
  onOpenDetail: (questionId: number) => void
  onScopeRefresh: () => void
}

function evidenceCount(option: ErrorOptionSummary): number {
  return option.candidate_causes.reduce((total, cause) => total + cause.evidence_count, 0)
}

function OptionEvidence({ option }: { option: ErrorOptionDetail }) {
  return (
    <Collapse
      size="small"
      defaultActiveKey={option.candidate_causes.map(
        (cause) => `${option.base_letter}-${cause.code}`,
      )}
      items={option.candidate_causes.map((cause) => ({
        key: `${option.base_letter}-${cause.code}`,
        label: (
          <Space wrap>
            <Tag color="orange">{cause.code}</Tag>
            <Typography.Text>{cause.name}</Typography.Text>
            <Typography.Text type="secondary">
              {cause.rationale || '未填写候选理由'}
            </Typography.Text>
            <Tag>{cause.evidence.length} 条证据</Tag>
          </Space>
        ),
        children: (
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            {cause.evidence.length === 0 ? (
              <Typography.Text type="secondary">该候选暂无证据记录</Typography.Text>
            ) : (
              cause.evidence.map((evidence) => (
                <div key={evidence.evidence_id} className="skill-query-evidence">
                  <Typography.Text type="secondary">
                    {evidence.source} · {evidence.start_ms}–{evidence.end_ms} ms
                  </Typography.Text>
                  <Typography.Paragraph style={{ marginBottom: 0 }}>
                    {evidence.text}
                  </Typography.Paragraph>
                  {evidence.support_note ? (
                    <Typography.Text type="secondary">
                      说明：{evidence.support_note}
                    </Typography.Text>
                  ) : null}
                </div>
              ))
            )}
          </Space>
        ),
      }))}
    />
  )
}

export default function ErrorQuestionList({
  items,
  loading,
  scopeVersion,
  onOpenDetail,
  onScopeRefresh,
}: ErrorQuestionListProps) {
  const [expandedKeys, setExpandedKeys] = useState<readonly (string | number)[]>([])
  const [details, setDetails] = useState<Record<number, QuestionDetailData>>({})
  const [detailLoading, setDetailLoading] = useState<Record<number, boolean>>({})
  const [detailError, setDetailError] = useState<Record<number, string>>({})
  const [retryNonce, setRetryNonce] = useState(0)

  async function loadDetail(item: QuestionListItem, force = false) {
    if (details[item.question_id] && !force) return
    setDetailLoading((current) => ({ ...current, [item.question_id]: true }))
    setDetailError((current) => ({ ...current, [item.question_id]: '' }))
    try {
      const detail = await getQuestionDetail(item.question_id, {
        expectedScopeVersion: scopeVersion,
        examPaperId: item.paper.exam_paper_id,
      })
      setDetails((current) => ({ ...current, [item.question_id]: detail }))
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        onScopeRefresh()
        return
      }
      setDetailError((current) => ({
        ...current,
        [item.question_id]:
          error instanceof Error ? error.message : '证据加载失败，请稍后重试',
      }))
    } finally {
      setDetailLoading((current) => ({ ...current, [item.question_id]: false }))
    }
  }

  const columns: TableProps<QuestionListItem>['columns'] = [
    {
      title: '题目',
      key: 'question',
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong ellipsis style={{ maxWidth: 430 }}>
            {item.question_text}
          </Typography.Text>
          <Typography.Text type="secondary" className="skill-query-code">
            {item.question_code}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '试卷 / 题号',
      key: 'paper',
      width: 190,
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{item.paper.exam_paper_code}</Typography.Text>
          <Typography.Text type="secondary">第 {item.paper.question_no} 题</Typography.Text>
        </Space>
      ),
    },
    {
      title: '错误选项 / 候选错因',
      key: 'options',
      render: (_, item) => (
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          {item.error_options.map((option) => (
            <div key={option.base_option_letter} className="skill-query-error-option">
              <Space wrap>
                <Tag color="volcano">
                  {option.display_option_letter ?? option.base_option_letter}
                  {option.display_option_letter && option.display_option_letter !== option.base_option_letter
                    ? `（基准 ${option.base_option_letter}）`
                    : ''}
                </Tag>
                <Typography.Text>{option.option_text}</Typography.Text>
                {option.candidate_causes.map((cause) => (
                  <Tag key={cause.code} color={cause.is_match ? 'orange' : 'default'}>
                    {cause.code} {cause.name}
                    {cause.evidence_count > 0 ? ` · ${cause.evidence_count} 证据` : ''}
                  </Tag>
                ))}
              </Space>
              <Typography.Text type="secondary" className="skill-query-evidence-count">
                共 {evidenceCount(option)} 条候选证据
              </Typography.Text>
            </div>
          ))}
        </Space>
      ),
    },
    {
      title: '标注',
      key: 'annotation',
      width: 125,
      render: (_, item) => <Tag color="green">{item.annotation_status_label}</Tag>,
    },
    {
      title: '音频',
      key: 'audio',
      width: 70,
      render: (_, item) =>
        item.has_audio ? <Tag icon={<SoundOutlined />} color="cyan">有</Tag> : <Tag>无</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_, item) => (
        <Button type="link" size="small" onClick={() => onOpenDetail(item.question_id)}>
          <FileTextOutlined /> 详情
        </Button>
      ),
    },
  ]

  return (
    <Table<QuestionListItem>
      rowKey="question_id"
      size="small"
      loading={loading}
      columns={columns}
      dataSource={items}
      pagination={false}
      expandable={{
        expandedRowKeys: [...expandedKeys],
        onExpand: (expanded, record) => {
          setExpandedKeys((current) =>
            expanded
              ? [...current.filter((key) => key !== record.question_id), record.question_id]
              : current.filter((key) => key !== record.question_id),
          )
          if (expanded) {
            void loadDetail(record)
          }
        },
        expandedRowRender: (record) => {
          const detail = details[record.question_id]
          const error = detailError[record.question_id]
          const isLoading = detailLoading[record.question_id]
          if (isLoading) {
            return (
              <div className="skill-query-center">
                <Spin size="small" /> 正在加载候选证据…
              </div>
            )
          }
          if (error) {
            return (
              <Alert
                type="error"
                showIcon
                message={error}
                action={
                  <Button size="small" onClick={() => { setRetryNonce((v) => v + 1); void loadDetail(record, true) }}>
                    重试
                  </Button>
                }
              />
            )
          }
          if (!detail) {
            return <Typography.Text type="secondary">展开后加载证据全文</Typography.Text>
          }
          const optionDetails = detail.error_options
          if (optionDetails.length === 0) {
            return (
              <Alert
                type="warning"
                showIcon
                message="该题当前没有可展示的错误选项候选错因"
                description={detail.warnings.map((warning) => warning.message).join('；') || undefined}
              />
            )
          }
          return (
            <Space direction="vertical" size={8} style={{ width: '100%' }} key={retryNonce}>
              {optionDetails.map((option) => (
                <div key={option.base_letter}>
                  <Typography.Text strong>
                    错误选项 {option.display_letter ?? option.base_letter}
                    {option.display_letter && option.display_letter !== option.base_letter
                      ? `（基准 ${option.base_letter}）`
                      : ''}
                    ：{option.text}
                  </Typography.Text>
                  <Typography.Text type="secondary"> 题目候选错因（非个人错因）</Typography.Text>
                  <OptionEvidence option={option} />
                </div>
              ))}
              <Typography.Text type="secondary">{detail.personal_error.message}</Typography.Text>
            </Space>
          )
        },
      }}
      locale={{ emptyText: '当前错因暂无正式题目' }}
    />
  )
}
