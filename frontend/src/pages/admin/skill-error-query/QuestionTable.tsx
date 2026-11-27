import { FileTextOutlined, SoundOutlined } from '@ant-design/icons'
import { Button, Space, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import type { QuestionListItem } from '../../../api/skill-error-query'

interface QuestionTableProps {
  items: QuestionListItem[]
  loading?: boolean
  onOpenDetail: (questionId: number) => void
}

export default function QuestionTable({
  items,
  loading,
  onOpenDetail,
}: QuestionTableProps) {
  const columns: TableProps<QuestionListItem>['columns'] = [
    {
      title: '题目',
      dataIndex: 'question_text',
      key: 'question',
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong ellipsis style={{ maxWidth: 420 }}>
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
          <Typography.Text type="secondary">
            第 {item.paper.question_no} 题
            {item.paper.paper_count > 1 ? ` · 共 ${item.paper.paper_count} 卷` : ''}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '技能角色',
      key: 'skills',
      width: 210,
      render: (_, item) => (
        <Space size={[4, 4]} wrap>
          {item.skills.filter((skill) => skill.role === 'PRIMARY').length > 1 ? (
            <Tag color="gold" title="该题有多个主要技能，需结合技能证据判断共同主要">
              共同主要
            </Tag>
          ) : null}
          {item.skills.length === 0 ? (
            <Tag color="red">标注缺失</Tag>
          ) : (
            item.skills.map((skill) => (
              <Tag
                key={`${skill.code}-${skill.role}`}
                color={skill.role === 'PRIMARY' ? 'blue' : 'default'}
              >
                {skill.code} · {skill.role === 'PRIMARY' ? '主要' : '辅助'}
              </Tag>
            ))
          )}
        </Space>
      ),
    },
    {
      title: '标注',
      key: 'annotation',
      width: 130,
      render: (_, item) => <Tag color="green">{item.annotation_status_label}</Tag>,
    },
    {
      title: '音频',
      key: 'audio',
      width: 80,
      render: (_, item) =>
        item.has_audio ? (
          <Tag icon={<SoundOutlined />} color="cyan">
            有
          </Tag>
        ) : (
          <Tag>无</Tag>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
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
      locale={{ emptyText: '当前条目暂无正式题目' }}
    />
  )
}
