import { useMemo } from 'react'
import { Tag, Tree, Typography } from 'antd'
import type { TreeDataNode } from 'antd'
import type { DictionaryNode } from '../../../api/skill-error-query'

interface DictionaryTreeProps {
  nodes: DictionaryNode[]
  selectedCode?: string
  search: string
  onSelect: (node: DictionaryNode) => void
}

function sortNodes(nodes: DictionaryNode[]): DictionaryNode[] {
  return [...nodes].sort((a, b) =>
    a.display_code.localeCompare(b.display_code, 'zh-CN', { numeric: true }),
  )
}

function buildTree(nodes: DictionaryNode[], search: string): TreeDataNode[] {
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

  const visit = (parentId: number | null): TreeDataNode[] =>
    sortNodes(children.get(parentId) ?? []).flatMap((node) => {
      const childNodes = visit(node.id)
      if (keyword && !matches(node) && childNodes.length === 0) {
        return []
      }
      const isLeaf = node.level === 3
      const count = node.question_count
      return [
        {
          key: node.code,
          title: (
            <span className="skill-query-tree-title">
              <span>
                <Typography.Text strong={node.level === 3}>{node.name}</Typography.Text>
                <Typography.Text type="secondary" className="skill-query-code">
                  {node.display_code}
                </Typography.Text>
              </span>
              {isLeaf && count !== null ? (
                <Tag bordered={false} color="default">
                  {count}
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
  onSelect,
}: DictionaryTreeProps) {
  const byCode = useMemo(
    () => new Map(nodes.map((node) => [node.code, node])),
    [nodes],
  )
  const treeData = useMemo(() => buildTree(nodes, search), [nodes, search])
  const expandedKeys = useMemo(() => {
    if (!search.trim()) return undefined
    return nodes.map((node) => node.code)
  }, [nodes, search])

  return (
    <Tree
      blockNode
      showLine
      treeData={treeData}
      selectedKeys={selectedCode ? [selectedCode] : []}
      expandedKeys={expandedKeys}
      onSelect={(keys) => {
        const code = String(keys[0] ?? '')
        const node = byCode.get(code)
        if (node) onSelect(node)
      }}
      className="skill-query-tree"
    />
  )
}
