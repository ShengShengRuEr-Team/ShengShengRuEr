import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { ROLES } from '../constants/permissions'
import { ROUTES, homePathForRole } from '../constants/routes'
import AdminLayout from '../layouts/AdminLayout'
import StudentLayout from '../layouts/StudentLayout'
import FullPageLoading from '../ui/FullPageLoading'
import RequireAuth from './RequireAuth'
import RequireRole from './RequireRole'

// 路由级代码分割：页面单独成 chunk，首屏只加载登录页与守卫。
// 布局保持同步引入，避免登录后切换页面时反复闪加载态。
const LoginPage = lazy(() => import('../pages/LoginPage'))
const ForbiddenPage = lazy(() => import('../pages/ForbiddenPage'))
const AdminHomePage = lazy(() => import('../pages/admin/HomePage'))
const StudentHomePage = lazy(() => import('../pages/student/HomePage'))

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
 * 模块一路由表：
 * - 管理端 `/admin`：RequireAuth + RequireRole(admin)
 * - 学生端 `/student`：RequireAuth + RequireRole(student)
 * - 守卫只决定「能不能看到页面」，越权请求最终由后端 403 兜底
 */
export default function AppRouter() {
  return (
    <Suspense fallback={<FullPageLoading />}>
      <Routes>
        <Route path="/" element={<HomeRedirect />} />
        <Route path={ROUTES.LOGIN} element={<LoginPage />} />
        <Route path={ROUTES.FORBIDDEN} element={<ForbiddenPage />} />

        <Route
          path={ROUTES.ADMIN_HOME}
          element={
            <RequireAuth>
              <RequireRole role={ROLES.ADMIN}>
                <AdminLayout />
              </RequireRole>
            </RequireAuth>
          }
        >
          <Route index element={<AdminHomePage />} />
        </Route>

        <Route
          path={ROUTES.STUDENT_HOME}
          element={
            <RequireAuth>
              <RequireRole role={ROLES.STUDENT}>
                <StudentLayout />
              </RequireRole>
            </RequireAuth>
          }
        >
          <Route index element={<StudentHomePage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
