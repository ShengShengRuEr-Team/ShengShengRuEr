import { useEffect } from 'react'
import { App } from 'antd'
import { registerMessageApi } from './message'

/**
 * 把 antd App 上下文中的 message 实例注册到模块级桥，
 * 让 axios 拦截器（React 树外）也能按文档 5.4 的要求调用 message.error。
 * 必须放在 <App> 内部、AuthProvider 之外。
 */
export default function MessageBridge() {
  const { message } = App.useApp()

  useEffect(() => {
    registerMessageApi(message)
    return () => {
      registerMessageApi(null)
    }
  }, [message])

  return null
}
