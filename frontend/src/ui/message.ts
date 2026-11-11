import type { MessageInstance } from 'antd/es/message/interface'

/**
 * antd 6 不推荐使用静态 message 方法（脱离 ConfigProvider / App 上下文）。
 * 这里保存 <App> 内 App.useApp() 提供的实例，供 axios 拦截器等 React 树外代码调用。
 */
let messageApi: MessageInstance | null = null

export function registerMessageApi(api: MessageInstance | null): void {
  messageApi = api
}

/** 403 等场景的统一提示入口；实例未就绪时退化为控制台输出，不抛错。 */
export function showError(content: string): void {
  if (messageApi) {
    void messageApi.error(content)
    return
  }
  console.error(content)
}
