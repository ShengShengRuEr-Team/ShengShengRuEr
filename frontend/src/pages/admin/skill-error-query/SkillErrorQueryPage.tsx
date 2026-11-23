import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ApartmentOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Col,
  Input,
  Pagination,
  Row,
  Segmented,
  Space,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { ApiError } from '../../../api/api-error'
import {
  getDictionary,
  listQuestions,
} from '../../../api/skill-error-query'
import type {
  DictionaryData,
  DictionaryNode,
  QueryType,
  QuestionListData,
  RoleFilter,
} from '../../../api/skill-error-query'
import CategorySummary from './CategorySummary'
import DictionaryTree from './DictionaryTree'
import EntryDetailCard from './EntryDetailCard'
import ErrorQuestionList from './ErrorQuestionList'
import QuestionDetailDrawer from './QuestionDetailDrawer'
import QuestionTable from './QuestionTable'
import './skill-error-query.css'

const DEFAULT_PAGE_SIZE = 20

function firstLeaf(nodes: DictionaryNode[]): DictionaryNode | undefined {
  const leaves = nodes
    .filter((node) => node.level === 3)
    .sort((a, b) =>
      a.display_code.localeCompare(b.display_code, 'zh-CN', { numeric: true }),
    )
  return leaves.find((node) => (node.question_count ?? 0) > 0) ?? leaves[0]
}

function levelCount(nodes: DictionaryNode[], level: number): number {
  return nodes.filter((node) => node.level === level).length
}

export default function SkillErrorQueryPage() {
  const [dictionary, setDictionary] = useState<DictionaryData | null>(null)
  const [queryType, setQueryType] = useState<QueryType>('skill')
  const [selectedNode, setSelectedNode] = useState<DictionaryNode | null>(null)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('all')
  const [categoryMode, setCategoryMode] = useState<'by-leaf' | 'all'>('by-leaf')
  const [listData, setListData] = useState<QuestionListData | null>(null)
  const [cursor, setCursor] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [drawerQuestionId, setDrawerQuestionId] = useState<number | null>(null)

  const nodes = useMemo<DictionaryNode[]>(() => {
    if (!dictionary) return []
    return queryType === 'skill' ? dictionary.skills : dictionary.error_causes
  }, [dictionary, queryType])

  const scopeVersion = listData?.scope_version ?? dictionary?.scope_version ?? ''

  const loadList = useCallback(
    async (
      node: DictionaryNode,
      nextCursor: number,
      type: QueryType,
      role: RoleFilter,
      limit: number,
    ) => {
      if (!dictionary) return
      setLoading(true)
      setError('')
      try {
        const subjectType =
          node.level === 3
            ? type
            : type === 'skill'
              ? 'skill_category'
              : 'error_category'
        const data = await listQuestions({
          subject_type: subjectType,
          subject_code: node.code,
          role: type === 'skill' ? role : 'all',
          cursor: nextCursor,
          limit,
          expected_scope_version:
            nextCursor > 0 ? dictionary.scope_version : undefined,
        })
        setListData(data)
        setCursor(nextCursor)
      } catch (reason) {
        if (reason instanceof ApiError && reason.status === 409) {
          setError('查询范围已变化，正在刷新词典和列表。')
          setDictionary(null)
          return
        }
        setError(reason instanceof Error ? reason.message : '题目列表加载失败')
      } finally {
        setLoading(false)
      }
    },
    [dictionary],
  )

  const loadDictionary = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await getDictionary()
      setDictionary(data)
      const initial = firstLeaf(queryType === 'skill' ? data.skills : data.error_causes)
      setSelectedNode(initial ?? null)
      setListData(null)
      setCursor(0)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '词典加载失败')
    } finally {
      setLoading(false)
    }
  }, [queryType])

  useEffect(() => {
    void loadDictionary()
    // The dictionary is reloaded when the active tab changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryType])

  useEffect(() => {
    if (dictionary && selectedNode) {
      void loadList(selectedNode, 0, queryType, roleFilter, pageSize)
    }
    // Only a node or role change starts a new first page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNode, roleFilter, dictionary])

  const handleTypeChange = (key: string) => {
    setQueryType(key as QueryType)
    setSearch('')
    setRoleFilter('all')
    setCategoryMode('by-leaf')
    setDrawerQuestionId(null)
    setListData(null)
    setSelectedNode(null)
  }

  const handleSelectNode = (node: DictionaryNode) => {
    setSelectedNode(node)
    setListData(null)
    setCursor(0)
    setCategoryMode('by-leaf')
  }

  const handlePageChange = (page: number) => {
    if (!selectedNode) return
    void loadList(selectedNode, (page - 1) * pageSize, queryType, roleFilter, pageSize)
  }

  const handlePageSizeChange = (_page: number, size: number) => {
    setPageSize(size)
    setCursor(0)
    if (selectedNode) {
      void loadList(selectedNode, 0, queryType, roleFilter, size)
    }
  }

  const handleScopeRefresh = useCallback(() => {
    setDictionary(null)
    setListData(null)
    setSelectedNode(null)
    setDrawerQuestionId(null)
    setError('')
    void loadDictionary()
  }, [loadDictionary])

  const handleOpenDetail = (questionId: number) => {
    setDrawerQuestionId(questionId)
  }

  const closeDrawer = useCallback(() => setDrawerQuestionId(null), [])

  const selectedIsLeaf = selectedNode?.level === 3
  const isCategory = Boolean(selectedNode && !selectedIsLeaf)

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={3} style={{ marginBottom: 4 }}>
          技能与错因查询
        </Typography.Title>
        <Typography.Text type="secondary">
          只读查询当前正式题库的技能、错因标注；分类节点只汇总，不直接作为题目标注。
        </Typography.Text>
      </div>

      {error ? (
        <Alert
          type="error"
          showIcon
          message={error}
          action={
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => {
                if (!dictionary) void loadDictionary()
                else if (selectedNode)
                  void loadList(
                    selectedNode,
                    cursor,
                    queryType,
                    roleFilter,
                    pageSize,
                  )
              }}
            >
              重试
            </Button>
          }
        />
      ) : null}

      <Tabs
        activeKey={queryType}
        onChange={handleTypeChange}
        items={[
          {
            key: 'skill',
            label: (
              <Space>
                技能表
                {dictionary ? (
                  <Typography.Text type="secondary">
                    {levelCount(dictionary.skills, 1)} / {levelCount(dictionary.skills, 2)} /{' '}
                    {levelCount(dictionary.skills, 3)}
                  </Typography.Text>
                ) : null}
              </Space>
            ),
          },
          {
            key: 'error_cause',
            label: (
              <Space>
                错因表
                {dictionary ? (
                  <Typography.Text type="secondary">
                    {levelCount(dictionary.error_causes, 1)} / {levelCount(dictionary.error_causes, 2)} /{' '}
                    {levelCount(dictionary.error_causes, 3)}
                  </Typography.Text>
                ) : null}
              </Space>
            ),
          },
        ]}
      />

      <Input
        allowClear
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        prefix={<SearchOutlined />}
        placeholder="搜索名称、稳定代码或展示编码"
        style={{ maxWidth: 420 }}
      />

      <Row gutter={[16, 16]} align="top">
        <Col xs={24} lg={8} xl={7}>
          <Card
            title={
              <Space>
                <ApartmentOutlined />
                {queryType === 'skill' ? '技能树' : '错因树'}
              </Space>
            }
            extra={<Typography.Text type="secondary">{nodes.length} 项</Typography.Text>}
            className="skill-query-tree-card"
          >
            {dictionary ? (
              <DictionaryTree
                nodes={nodes}
                selectedCode={selectedNode?.code}
                search={search}
                onSelect={handleSelectNode}
                onClearSearch={() => setSearch('')}
              />
            ) : (
              <Typography.Text type="secondary">正在加载词典…</Typography.Text>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={16} xl={17}>
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            {selectedNode ? (
              <EntryDetailCard
                node={selectedNode}
                categoryStats={
                  isCategory && listData
                    ? {
                        leafCount: listData.matched_leaves.length,
                        questionCount: listData.question_count,
                        optionRelationCount: listData.option_relation_count,
                      }
                    : undefined
                }
                onOpenQuestions={() => {
                  if (!selectedNode) return
                  setCategoryMode('all')
                  void loadList(selectedNode, 0, queryType, roleFilter, pageSize)
                }}
              />
            ) : (
              <Card>
                <Typography.Text type="secondary">请从左侧选择技能或错因条目。</Typography.Text>
              </Card>
            )}

            {selectedNode ? (
              isCategory ? (
                <Space direction="vertical" size={12} style={{ width: '100%' }}>
                  {listData && listData.question_count === 0 ? (
                    <Typography.Text type="secondary">
                      该分类暂无正式题目，无需切换“按条目分组 / 全部题目”。
                    </Typography.Text>
                  ) : (
                    <Segmented
                      value={categoryMode}
                      onChange={(value) => setCategoryMode(value as 'by-leaf' | 'all')}
                      options={[
                        { label: '按条目分组', value: 'by-leaf' },
                        { label: '全部题目', value: 'all' },
                      ]}
                    />
                  )}
                  {listData ? (
                    <CategorySummary
                      data={listData}
                      mode={categoryMode}
                      onOpenLeaf={(code) => {
                        const leaf = nodes.find((node) => node.code === code)
                        if (leaf) setSelectedNode(leaf)
                      }}
                      onOpenDetail={handleOpenDetail}
                      onScopeRefresh={handleScopeRefresh}
                    />
                  ) : (
                    <Card loading />
                  )}
                </Space>
              ) : (
                <Card
                  title={
                    <Space wrap>
                      <span>相关题目</span>
                      {listData ? (
                        <>
                          <Tag color="blue">共 {listData.question_count} 题</Tag>
                          {queryType === 'skill' ? (
                            <>
                              <Tag>主要 {listData.primary_question_count ?? 0}</Tag>
                              <Tag>辅助 {listData.auxiliary_question_count ?? 0}</Tag>
                              <Segmented
                                size="small"
                                value={roleFilter}
                                onChange={(value) => setRoleFilter(value as RoleFilter)}
                                options={[
                                  { label: '全部', value: 'all' },
                                  { label: '主要', value: 'primary' },
                                  { label: '辅助', value: 'auxiliary' },
                                ]}
                              />
                            </>
                          ) : (
                            <Tag>
                              选项—错因关系 {listData.option_relation_count ?? 0}
                            </Tag>
                          )}
                        </>
                      ) : null}
                    </Space>
                  }
                  extra={
                    <Typography.Text type="secondary">
                      {listData?.subject.display_code} · 正式审核通过
                    </Typography.Text>
                  }
                >
                  {queryType === 'skill' ? (
                    <QuestionTable
                      items={listData?.items ?? []}
                      loading={loading}
                      onOpenDetail={handleOpenDetail}
                    />
                  ) : (
                    <ErrorQuestionList
                      key={selectedNode?.code ?? 'error-list'}
                      items={listData?.items ?? []}
                      loading={loading}
                      scopeVersion={scopeVersion}
                      onOpenDetail={handleOpenDetail}
                      onScopeRefresh={handleScopeRefresh}
                    />
                  )}
                  <div className="skill-query-pagination">
                    <Pagination
                      current={Math.floor(cursor / pageSize) + 1}
                      pageSize={pageSize}
                      total={listData?.question_count ?? 0}
                      showSizeChanger
                      pageSizeOptions={[20, 50, 100]}
                      onShowSizeChange={handlePageSizeChange}
                      onChange={handlePageChange}
                    />
                  </div>
                </Card>
              )
            ) : null}
          </Space>
        </Col>
      </Row>

      <QuestionDetailDrawer
        open={drawerQuestionId !== null}
        questionId={drawerQuestionId}
        scopeVersion={scopeVersion}
        onClose={closeDrawer}
        onScopeRefresh={handleScopeRefresh}
      />
    </Space>
  )
}
