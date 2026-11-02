import { App as AntdApp, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { AuthProvider } from './auth/AuthContext'
import AppRouter from './router'
import MessageBridge from './ui/MessageBridge'

export default function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <AntdApp>
        <MessageBridge />
        <AuthProvider>
          <AppRouter />
        </AuthProvider>
      </AntdApp>
    </ConfigProvider>
  )
}
