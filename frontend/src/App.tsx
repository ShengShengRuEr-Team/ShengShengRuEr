import { App as AntdApp, Card, ConfigProvider, Spin, Tag, Typography } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { API_BASE_URL } from './api/client'
import { AuthProvider } from './auth/AuthContext'
import { useAuth } from './auth/useAuth'
import MessageBridge from './ui/MessageBridge'

const STACK = [
  { name: 'React', version: '19.3.1' },
  { name: 'Vite', version: '8.3.5' },
  { name: 'TypeScript', version: '6.0.3' },
  { name: 'Ant Design', version: '6.6.8' },
  { name: 'axios', version: '1.21.0' },
] as const

/**
 * 第 1–2 步占位页：验证构建链路与 AuthContext 启动流程。
 * 登录页、路由守卫与两端页面在第 3–7 步接入，届时本组件被路由表替换。
 */
function ScaffoldStatus() {
  const { status, user, roles, permissions } = useAuth()

  const statusLabel =
    status === 'loading' ? '恢复中…' : status === 'authenticated' ? '已登录' : '未登录'

  return (
    <div className="scaffold-page">
      <Card className="scaffold-card">
        <Typography.Title level={2}>声声入耳 · 前端脚手架就绪</Typography.Title>
        <Typography.Paragraph type="secondary">
          第 1–2 步已完成：工程脚手架、axios 封装、AuthContext、token
          存储与 401 / 403 统一处理。登录页、路由守卫与两端页面在第 3–7 步接入。
        </Typography.Paragraph>

        <div className="scaffold-tags">
          <Tag color={status === 'authenticated' ? 'green' : 'default'}>
            登录态：{statusLabel}
          </Tag>
          {status === 'loading' && <Spin size="small" />}
          {user && <Tag color="blue">{user.nickname || user.username}</Tag>}
          {roles.map((role) => (
            <Tag key={role}>{role}</Tag>
          ))}
          {status === 'authenticated' && <Tag>{permissions.length} 项权限</Tag>}
        </div>

        <div className="scaffold-tags">
          {STACK.map((item) => (
            <Tag key={item.name} color="blue">
              {item.name} {item.version}
            </Tag>
          ))}
        </div>

        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
          接口地址 {API_BASE_URL}/api/v1（前端端口固定 5173）。开发期后端未启动时，显示「未登录」属预期。
        </Typography.Paragraph>
      </Card>
    </div>
  )
}

export default function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <AntdApp>
        <MessageBridge />
        <AuthProvider>
          <ScaffoldStatus />
        </AuthProvider>
      </AntdApp>
    </ConfigProvider>
  )
}
