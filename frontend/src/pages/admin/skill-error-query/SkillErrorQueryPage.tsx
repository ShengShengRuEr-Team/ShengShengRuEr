import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
  Select,
  Space,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { ApiError } from '../../../api/api-error'
import { getDictionary, listQuestions } from '../../../api/skill-error-query'
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

function nodesInCategory(
  nodes: DictionaryNode[],
  category: DictionaryNode | null,
): DictionaryNode[] {
  if (!category) return nodes
  const allowed = new Set<string>(category.path.map((part) => part.code))
  allowed.add(category.code)
  for (const node of nodes) {
    if (node.path.some((part) => part.code === category.code)) {
      allowed.add(node.code)
    }
  }
  return nodes.filter((node) => allowed.has(node.code))
}

function uniqueKeys(keys: string[]): string[] {
  return [...new Set(keys)]
}

export default function SkillErrorQueryPage() {
  const [dictionary, setDictionary] = useState<DictionaryData | null>(null)
  const [queryType, setQueryType] = useState<QueryType>('skill')
  const [selectedNode, setSelectedNode] = useState<DictionaryNode | null>(null)
  const [categoryFilter, setCategoryFilter] = useState<DictionaryNode | null>(null)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('all')
  const [categoryMode, setCategoryMode] = useState<'by-leaf' | 'all'>('by-leaf')
  const [listData, setListData] = useState<QuestionListData | null>(null)
  const [cursor, setCursor] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [drawerQuestionId, setDrawerQuestionId] = useState<number | null>(null)
  const [scopeReloadKey, setScopeReloadKey] = useState(0)
  const listRequestSeq = useRef(0)
  const dictionaryRequestSeq = useRef(0)

  const nodes = useMemo<DictionaryNode[]>(() => {
    if (!dictionary) return []
    return queryType === 'skill' ? dictionary.skills : dictionary.error_causes
  }, [dictionary, queryType])

  const visibleNodes = useMemo(
    () => (search.trim() ? nodesInCategory(nodes, categoryFilter) : nodes),
    [nodes, categoryFilter, search],
  )

  const selectedIsLeaf = selectedNode?.level === 3
  const isCategory = Boolean(selectedNode && !selectedIsLeaf)
  const scopeVersion = listData?.scope_version ?? dictionary?.scope_version ?? ''
  const searchExpandedKeys = useMemo(
    () => (search.trim() ? visibleNodes.map((node) => node.code) : expandedKeys),
    [expandedKeys, search, visibleNodes],
  )

  const loadDictionary = useCallback(
    async (preferredCode?: string, reloadList = false) => {
      const seq = ++dictionaryRequestSeq.current
      // A dictionary refresh supersedes every list request from the old scope.
      listRequestSeq.current += 1
      setListData(null)
      setDrawerQuestionId(null)
      setCursor(0)
      setLoading(true)
      setError('')
      try {
        const data = await getDictionary()
        if (seq !== dictionaryRequestSeq.current) return
        setDictionary(data)
        const all = queryType === 'skill' ? data.skills : data.error_causes
        const preferred = preferredCode
          ? all.find((node) => node.code === preferredCode)
          : undefined
        const initial = preferred ?? firstLeaf(all)
        setSelectedNode(initial ?? null)
        setExpandedKeys(initial ? initial.path.map((part) => part.code) : [])
        setListData(null)
        setCursor(0)
        if (reloadList) setScopeReloadKey((value) => value + 1)
      } catch (reason) {
        if (seq !== dictionaryRequestSeq.current) return
        setError(reason instanceof Error ? reason.message : '词典加载失败')
      } finally {
        if (seq === dictionaryRequestSeq.current) setLoading(false)
      }
    },
    [queryType],
  )

  useEffect(() => {
    setCategoryFilter(null)
    setSearch('')
    setRoleFilter('all')
    setPageSize(DEFAULT_PAGE_SIZE)
    setCategoryMode('by-leaf')
    setExpandedKeys([])
    setListData(null)
    setSelectedNode(null)
    setDrawerQuestionId(null)
    void loadDictionary()
  }, [queryType, loadDictionary])

  const loadList = useCallback(
    async (
      node: DictionaryNode,
      nextCursor: number,
      type: QueryType,
      role: RoleFilter,
      limit: number,
    ) => {
      if (!dictionary) return
      const seq = ++listRequestSeq.current
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
          role: type === 'skill' && node.level === 3 ? role : 'all',
          cursor: nextCursor,
          limit,
          expected_scope_version: dictionary.scope_version,
        })
        if (seq !== listRequestSeq.current) return
        if (data.scope_version !== dictionary.scope_version) {
          throw new ApiError('查询范围已变化，请整体刷新', 409, 409, 'SCOPE_CHANGED')
        }
        setListData(data)
        setCursor(nextCursor)
        setPageSize(limit)
      } catch (reason) {
        if (seq !== listRequestSeq.current) return
        if (reason instanceof ApiError && reason.status === 409) {
          setListData(null)
          setDrawerQuestionId(null)
          setError('查询范围已变化，正在重新加载词典和第一页。')
          void loadDictionary(node.code, true)
          return
        }
        setError(reason instanceof Error ? reason.message : '题目列表加载失败')
      } finally {
        if (seq === listRequestSeq.current) setLoading(false)
      }
    },
    [dictionary, loadDictionary],
  )

  useEffect(() => {
    if (dictionary && selectedNode) {
      void loadList(selectedNode, 0, queryType, roleFilter, pageSize)
    }
    // selectedNode/role change starts a new first page; pageSize changes use changePage.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNode, roleFilter, dictionary, scopeReloadKey])

  const changePage = (page: number, size = pageSize) => {
    if (!selectedNode) return
    void loadList(selectedNode, (page - 1) * size, queryType, roleFilter, size)
  }

  const handleSelectNode = (node: DictionaryNode) => {
    setSelectedNode(node)
    setListData(null)
    setCursor(0)
    setExpandedKeys((current) =>
      uniqueKeys([...current, ...node.path.map((part) => part.code)]),
    )
    if (node.level < 3) {
      setRoleFilter('all')
      setCategoryFilter(node)
      setCategoryMode('by-leaf')
    }
  }

  const clearSearch = () => setSearch('')
  const clearCategoryFilter = () => setCategoryFilter(null)
  const closeDrawer = useCallback(() => setDrawerQuestionId(null), [])

  const handleScopeRefresh = useCallback(() => {
    setListData(null)
    setDrawerQuestionId(null)
    setError('')
    void loadDictionary(selectedNode?.code, true)
  }, [loadDictionary, selectedNode?.code])

  const handleOpenDetail = (questionId: number) => setDrawerQuestionId(questionId)

  const expandAll = () => {
    setExpandedKeys(
      visibleNodes
        .filter((node) => node.level < 3)
        .map((node) => node.code),
    )
  }
  const collapseAll = () => {
    setExpandedKeys(selectedNode ? selectedNode.path.map((part) => part.code) : [])
  }

  const activeCounts = useMemo(
    () => ({
      level1: levelCount(nodes, 1),
      level2: levelCount(nodes, 2),
      level3: levelCount(nodes, 3),
    }),
    [nodes],
  )
  const skillLeafCount = dictionary ? levelCount(dictionary.skills, 3) : 0
  const errorLeafCount = dictionary ? levelCount(dictionary.error_causes, 3) : 0
  const categoryStats =
    isCategory && listData
      ? {
          leafCount: listData.matched_leaves.length,
          questionCount: listData.question_count,
          optionRelationCount: listData.option_relation_count,
        }
      : undefined

  const relatedCard = selectedNode ? (
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
                    onChange={(value) => {
                      setRoleFilter(value as RoleFilter)
                    }}
                    options={[
                      { label: '全部', value: 'all' },
                      { label: '主要', value: 'primary' },
                      { label: '辅助', value: 'auxiliary' },
                    ]}
                  />
                </>
              ) : (
                <Tag>选项—错因关系 {listData.option_relation_count ?? 0}</Tag>
              )}
            </>
          ) : (
            <Tag>加载中</Tag>
          )}
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
          key={selectedNode.code}
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
          showSizeChanger={false}
          onChange={(page) => changePage(page)}
        />
        <Select
          size="small"
          value={pageSize}
          style={{ width: 100 }}
          options={[20, 50, 100].map((value) => ({ value, label: `${value} 条/页` }))}
          onChange={(size) => changePage(1, size)}
        />
      </div>
    </Card>
  ) : null

  return (
    <Space direction="vertical" size={18} style={{ width: '100%' }}>
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
              onClick={() => void loadDictionary(selectedNode?.code, true)}
            >
              重试
            </Button>
          }
        />
      ) : null}

      <div className="skill-query-tabs-row">
        <Tabs
          activeKey={queryType}
          onChange={(key) => setQueryType(key as QueryType)}
          items={[
            { key: 'skill', label: `技能表 ${skillLeafCount} 条` },
            { key: 'error_cause', label: `错因表 ${errorLeafCount} 条` },
          ]}
        />
        <Typography.Text type="secondary">
          {activeCounts.level1} 个一级分类 · {activeCounts.level2} 个二级分组 ·{' '}
          {activeCounts.level3} 个{queryType === 'skill' ? '技能' : '错因'}条目
        </Typography.Text>
      </div>

      <Row gutter={[16, 16]} align="top">
        <Col xs={24} lg={9} xl={8}>
          <Card
            title={
              <Space>
                <ApartmentOutlined />
                {queryType === 'skill' ? '技能目录' : '错因目录'}
              </Space>
            }
            extra={
              <Space size={0}>
                <Button type="link" size="small" onClick={expandAll}>
                  展开全部
                </Button>
                <Button type="link" size="small" onClick={collapseAll}>
                  收起
                </Button>
              </Space>
            }
            className="skill-query-tree-card"
          >
            <Input
              allowClear
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              prefix={<SearchOutlined />}
              placeholder="搜索名称或代码"
            />
            <Typography.Paragraph type="secondary" className="skill-query-tree-help">
              一级分类 → 二级分组 → 三级条目（用于题目标注的具体技能）
            </Typography.Paragraph>
            {categoryFilter && search.trim() ? (
              <div className="skill-query-filter-row">
                <Typography.Text type="secondary">搜索范围：</Typography.Text>
                <Tag closable color="blue" onClose={clearCategoryFilter}>
                  {categoryFilter.name}
                </Tag>
              </div>
            ) : null}
            {dictionary ? (
              <DictionaryTree
                nodes={visibleNodes}
                selectedCode={selectedNode?.code}
                search={search}
                expandedKeys={searchExpandedKeys}
                onExpand={setExpandedKeys}
                onSelect={handleSelectNode}
                onClearSearch={clearSearch}
              />
            ) : (
              <Typography.Text type="secondary">正在加载词典…</Typography.Text>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={15} xl={16}>
          {selectedNode ? (
            <EntryDetailCard
              node={selectedNode}
              allNodes={nodes}
              categoryStats={categoryStats}
              onOpenQuestions={() => {
                if (!selectedNode) return
                if (selectedNode.level < 3) setCategoryMode('all')
                void loadList(selectedNode, 0, queryType, roleFilter, pageSize)
              }}
            />
          ) : (
            <Card>
              <Typography.Text type="secondary">请从左侧选择技能或错因条目。</Typography.Text>
            </Card>
          )}
        </Col>
      </Row>

      {isCategory ? (
        listData ? (
          <CategorySummary
            data={listData}
            mode={categoryMode}
            cursor={cursor}
            pageSize={pageSize}
            onModeChange={setCategoryMode}
            onPageChange={(page) => changePage(page)}
            onPageSizeChange={(size) => changePage(1, size)}
            onOpenLeaf={(code) => {
              const leaf = nodes.find((node) => node.code === code)
              if (leaf) handleSelectNode(leaf)
            }}
            onOpenDetail={handleOpenDetail}
            onScopeRefresh={handleScopeRefresh}
          />
        ) : (
          <Card loading />
        )
      ) : (
        relatedCard
      )}

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
