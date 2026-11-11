import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import 'antd/dist/reset.css'
import './styles/global.css'
import App from './App'
import { ROUTES } from './constants/routes'

// 在 Router 初始化前只消费本次文档的刷新事件。导航类型在文档存活期间
// 始终为 reload，不能让列表的 effect 据此反复清掉新选择的筛选。
const navigation = performance.getEntriesByType('navigation')[0] as
  | PerformanceNavigationTiming
  | undefined
if (navigation?.type === 'reload' && window.location.pathname === ROUTES.ADMIN_LISTENING_PAPERS) {
  const url = new URL(window.location.href)
  if (url.searchParams.has('level') || url.searchParams.has('year')) {
    url.searchParams.delete('level')
    url.searchParams.delete('year')
    window.history.replaceState(window.history.state, '', url)
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
