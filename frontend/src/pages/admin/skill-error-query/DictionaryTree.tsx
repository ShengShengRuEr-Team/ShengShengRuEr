import { Button, Empty, Tag, Tree, Typography } from 'antd'
import type { TreeDataNode } from 'antd'
import type { DictionaryNode } from '../../../api/skill-error-query'

interface DictionaryTreeProps {
  nodes: DictionaryNode[]
  selectedCode?: string
  search: string
  expandedKeys: string[]
  onExpand: (keys: string[]) => void
  onSelect: (node: DictionaryNode) => void
  onClearSearch: () => void
}

function sortNodes(nodes: DictionaryNode[]): DictionaryNode[] {
  return [...nodes].sort((a, b) =>
    a.display_code.localeCompare(b.display_code, 'zh-CN', { numeric: true }),
  )
}

function buildTree(
  nodes: DictionaryNode[],
  search: string,
): TreeDataNode[] {
  const children = new Map<number | null, DictionaryNode[]>()
  for (const node of nodes) {
    const bucket = children.get(node.parent_id) ?? []
    bucket.push(node)
    children.set(node.parent_id, bucket)
  }

  const keyword = search.trim().toLowerCase()
  const matches = (node: DictionaryNode) =>
    !keyword ||
    node.name.toLowerCase().includes(keyword) ||
    node.code.toLowerCase().includes(keyword) ||
    node.display_code.toLowerCase().includes(keyword)

  const leafCount = (parentId: number): number =>
    (children.get(parentId) ?? []).reduce(
      (total, child) =>
        total + (child.level === 3 ? 1 : leafCount(child.id)),
      0,
    )

  const visit = (parentId: number | null): TreeDataNode[] =>
    sortNodes(children.get(parentId) ?? []).flatMap((node) => {
      const childNodes = visit(node.id)
      if (keyword && !matches(node) && childNodes.length === 0) {
        return []
      }
      const isLeaf = node.level === 3
      const count = node.question_count
      const leafTotal = isLeaf ? 0 : leafCount(node.id)
      const groupTotal =
        node.level === 1 ? (children.get(node.id) ?? []).length : 0
      return [
        {
          key: node.code,
          title: (
            <span className="skill-query-tree-title">
              <span className="skill-query-tree-label">
                <span>
                  <Typography.Text strong={isLeaf}>{node.name}</Typography.Text>
                  <Typography.Text type="secondary" className="skill-query-code">
                    {node.display_code}
                  </Typography.Text>
                  {keyword ? (
                    <Tag bordered={false} color="blue">
                      {node.code}
                    </Tag>
                  ) : null}
                  {keyword && isLeaf ? <Tag>三级条目</Tag> : null}
                  {!isLeaf ? (
                    <Typography.Text type="secondary" className="skill-query-tree-meta">
                      {node.level === 1
                        ? `二级 ${groupTotal} 组 / 三级 ${leafTotal} 叶`
                        : `三级 ${leafTotal} 叶`}
                    </Typography.Text>
                  ) : null}
                </span>
                {keyword ? (
                  <Typography.Text type="secondary" className="skill-query-tree-path">
                    {node.path.map((part) => part.name).join(' / ')}
                  </Typography.Text>
                ) : null}
              </span>
              {isLeaf && count !== null ? (
                <Tag bordered={false} color="default">
                  {count} 题
                </Tag>
              ) : null}
            </span>
          ),
          children: childNodes.length ? childNodes : undefined,
        },
      ]
    })

  return visit(null)
}

export default function DictionaryTree({
  nodes,
  selectedCode,
  search,
  expandedKeys,
  onExpand,
  onSelect,
  onClearSearch,
}: DictionaryTreeProps) {
  const byCode = new Map(nodes.map((node) => [node.code, node]))
  const treeData = buildTree(nodes, search)

  if (!treeData.length) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <span>
            未找到匹配条目
            <br />
            <Typography.Text type="secondary">
              请调整名称/代码，或清除分类筛选后重试
            </Typography.Text>
          </span>
        }
      >
        <Button size="small" onClick={onClearSearch}>
          清除搜索
        </Button>
      </Empty>
    )
  }

  return (
    <Tree
      blockNode
      showLine
      treeData={treeData}
      selectedKeys={selectedCode ? [selectedCode] : []}
      expandedKeys={expandedKeys}
      onExpand={(keys) => onExpand(keys.map((key) => String(key)))}
      onSelect={(keys) => {
        const code = String(keys[0] ?? '')
        const node = byCode.get(code)
        if (node) onSelect(node)
      }}
      className="skill-query-tree"
    />
  )
}
