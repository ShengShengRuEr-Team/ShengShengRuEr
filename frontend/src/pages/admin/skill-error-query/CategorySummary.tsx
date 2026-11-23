import { Alert, Button, Card, Space, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import type { MatchedLeaf, QuestionListData } from '../../../api/skill-error-query'
import ErrorQuestionList from './ErrorQuestionList'
import QuestionTable from './QuestionTable'

interface CategorySummaryProps {
  data: QuestionListData
  mode: 'by-leaf' | 'all'
  onOpenLeaf: (code: string) => void
  onOpenDetail: (questionId: number) => void
  onScopeRefresh: () => void
}

export default function CategorySummary({
  data,
  mode,
  onOpenLeaf,
  onOpenDetail,
  onScopeRefresh,
}: CategorySummaryProps) {
  const isSkill = data.subject.type === 'skill_category'
  const hasQuestions = data.question_count > 0
  const leafSum = data.matched_leaves.reduce(
    (total, leaf) => total + leaf.question_count,
    0,
  )
  const relationSum = data.matched_leaves.reduce(
    (total, leaf) => total + (leaf.option_relation_count ?? 0),
    0,
  )
  const leafColumns: TableProps<MatchedLeaf>['columns'] = [
    {
      title: '展示编码',
      dataIndex: 'display_code',
      width: 100,
      render: (value: string) => <Tag color="blue">{value}</Tag>,
    },
    {
      title: '条目',
      dataIndex: 'name',
      render: (value: string, leaf) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{value}</Typography.Text>
          <Typography.Text type="secondary" className="skill-query-code">
            {leaf.code}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '关联题目',
      dataIndex: 'question_count',
      width: 110,
      render: (value: number) => (
        <Typography.Text strong={value > 0}>{value}</Typography.Text>
      ),
    },
    ...(isSkill
      ? [
          {
            title: '主要 / 辅助',
            key: 'roles',
            width: 140,
            render: (_: unknown, leaf: MatchedLeaf) => (
              <Space>
                <Tag>主要 {leaf.primary_question_count ?? 0}</Tag>
                <Tag>辅助 {leaf.auxiliary_question_count ?? 0}</Tag>
              </Space>
            ),
          },
        ]
      : [
          {
            title: '选项—错因关系',
            key: 'relations',
            width: 150,
            render: (_: unknown, leaf: MatchedLeaf) => (
              <Tag>关系 {leaf.option_relation_count ?? 0}</Tag>
            ),
          },
        ]),
    {
      title: '操作',
      key: 'action',
      width: 90,
      render: (_: unknown, leaf: MatchedLeaf) =>
        leaf.question_count > 0 ? (
          <Button type="link" size="small" onClick={() => onOpenLeaf(leaf.code)}>
            查看条目
          </Button>
        ) : (
          <Typography.Text type="secondary">暂无题目</Typography.Text>
        ),
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        title={`${data.subject.name} · ${data.subject.display_code}`}
        extra={
          <Space>
            <Tag color="blue">分类汇总</Tag>
            <Tag>{data.matched_leaves.length} 个三级条目</Tag>
            <Tag>{data.question_count} 道正式题目</Tag>
            {!isSkill ? <Tag>关系 {data.option_relation_count ?? 0}</Tag> : null}
          </Space>
        }
      >
        <Typography.Paragraph type="secondary">
          分类节点只用于汇总和导航，不直接作为题目标注；题目按叶子归组，同一题命中多个叶子时只在
          “全部题目”中计一次。
        </Typography.Paragraph>

        {!hasQuestions ? (
          <Alert
            type="info"
            showIcon
            message="该分类暂无正式题目（题库覆盖缺口）"
            description="下面仍保留该分类下的三级条目并显示 0；0 条目不提供下钻，避免把覆盖缺口显示成有内容的页面。"
            style={{ marginBottom: 12 }}
          />
        ) : null}

        <Table<MatchedLeaf>
          rowKey="code"
          size="small"
          columns={leafColumns}
          dataSource={data.matched_leaves}
          pagination={false}
          locale={{ emptyText: '该分类下没有启用的三级条目' }}
        />

        {hasQuestions && leafSum > data.question_count ? (
          <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
            叶子关联题目数之和 {leafSum} 大于分类去重总数 {data.question_count}，因为同一题可命中多个叶子；
            以“全部题目”的去重数为准。
            {!isSkill ? ` 当前分类的选项—错因关系合计 ${relationSum} 条。` : ''}
          </Typography.Paragraph>
        ) : null}
      </Card>

      {hasQuestions && mode === 'all' ? (
        <Card
          title="全部题目（按题目去重）"
          extra={<Typography.Text type="secondary">共 {data.question_count} 条</Typography.Text>}
        >
          {isSkill ? (
            <QuestionTable items={data.items} onOpenDetail={onOpenDetail} />
          ) : (
            <ErrorQuestionList
              key={data.subject.code}
              items={data.items}
              scopeVersion={data.scope_version}
              onOpenDetail={onOpenDetail}
              onScopeRefresh={onScopeRefresh}
            />
          )}
        </Card>
      ) : null}
    </Space>
  )
}
