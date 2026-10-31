import { useEffect, useState } from 'react'
import { ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Table, Typography } from 'antd'
import type { TableProps } from 'antd'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../../api/api-error'
import { toPaper } from '../../api/adapters'
import type { Paper } from '../../api/adapters'
import { getPapers } from '../../api/papers'
import { formatExamLevel } from '../../constants/paper'

/** 学生端试卷列表：接口 4（后端按角色只返回已发布试卷）。 */
export default function StudentPaperListPage() {
  const navigate = useNavigate()
  const [papers, setPapers] = useState<Paper[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadPapers = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getPapers()
      setPapers(data.items.map(toPaper))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '试卷列表加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadPapers()
  }, [])

  const columns: TableProps<Paper>['columns'] = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    { title: '标题', dataIndex: 'title' },
    {
      title: '级别',
      dataIndex: 'examLevel',
      width: 100,
      render: (value: string) => formatExamLevel(value),
    },
    { title: '年份', dataIndex: 'examYear', width: 90 },
    { title: '月份', dataIndex: 'examMonth', width: 90 },
    { title: '套号', dataIndex: 'setNo', width: 90 },
    {
      title: '操作',
      key: 'action',
      width: 110,
      render: (_, record) => (
        <Button
          type="link"
          onClick={(event) => {
            event.stopPropagation()
            navigate(`/papers/${record.id}`)
          }}
        >
          开始练习
        </Button>
      ),
    },
  ]

  return (
    <Card>
      <div className="page-header">
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            试卷列表
          </Typography.Title>
          <Typography.Text type="secondary">
            仅显示已发布的试卷，共 {papers.length} 套
          </Typography.Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void loadPapers()} loading={loading}>
          刷新
        </Button>
      </div>

      {error && (
        <Alert
          type="error"
          showIcon
          message={error}
          style={{ marginBottom: 16 }}
          action={
            <Button size="small" onClick={() => void loadPapers()}>
              重试
            </Button>
          }
        />
      )}

      <Table<Paper>
        rowKey="id"
        columns={columns}
        dataSource={papers}
        loading={loading}
        pagination={false}
        locale={{ emptyText: '暂无已发布的试卷' }}
        onRow={(record) => ({
          onClick: () => navigate(`/papers/${record.id}`),
          style: { cursor: 'pointer' },
        })}
      />
    </Card>
  )
}
