import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { ROUTES, homePathForRole } from '../constants/routes'
import ForbiddenPage from '../pages/ForbiddenPage'
import LoginPage from '../pages/LoginPage'
import PlaceholderPage from '../pages/PlaceholderPage'
import FullPageLoading from '../ui/FullPageLoading'

/** `/`：按登录态与角色分流；未登录去登录页。 */
function HomeRedirect() {
  const { status, isAdmin } = useAuth()

  if (status === 'loading') {
    return <FullPageLoading />
  }
  if (status === 'anonymous') {
    return <Navigate to={ROUTES.LOGIN} replace />
  }
  return <Navigate to={homePathForRole(isAdmin)} replace />
}

/**
 * 第 3 步路由骨架：
 * - /login 与 /403 已实现（/403 第 7 步再完善视觉）
 * - 5 个业务路由先挂占位页，第 4 步加守卫与布局，第 5/6 步替换成真实页面
 * - 未知路径回到 `/` 再分流，避免直接 404 空白
 */
export default function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path={ROUTES.LOGIN} element={<LoginPage />} />
      <Route path={ROUTES.FORBIDDEN} element={<ForbiddenPage />} />

      <Route
        path={ROUTES.ADMIN_PAPERS}
        element={<PlaceholderPage title="管理端试卷列表" step="第 5 步" />}
      />
      <Route
        path={ROUTES.ADMIN_PAPER_DETAIL}
        element={<PlaceholderPage title="管理端题目页" step="第 5 步" />}
      />
      <Route
        path={ROUTES.ADMIN_TASKS}
        element={<PlaceholderPage title="管理端任务页" step="第 5 步" />}
      />
      <Route
        path={ROUTES.STUDENT_PAPERS}
        element={<PlaceholderPage title="学生端试卷列表" step="第 6 步" />}
      />
      <Route
        path={ROUTES.STUDENT_PAPER_DETAIL}
        element={<PlaceholderPage title="学生端题目页" step="第 6 步" />}
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
