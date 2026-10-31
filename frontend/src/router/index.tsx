import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { PERMISSIONS, ROLES } from '../constants/permissions'
import { ROUTES, homePathForRole } from '../constants/routes'
import AdminLayout from '../layouts/AdminLayout'
import StudentLayout from '../layouts/StudentLayout'
import AdminPaperListPage from '../pages/admin/PaperListPage'
import AdminPaperQuestionsPage from '../pages/admin/PaperQuestionsPage'
import AdminTaskListPage from '../pages/admin/TaskListPage'
import ForbiddenPage from '../pages/ForbiddenPage'
import LoginPage from '../pages/LoginPage'
import StudentPaperListPage from '../pages/student/PaperListPage'
import StudentPaperQuestionsPage from '../pages/student/PaperQuestionsPage'
import FullPageLoading from '../ui/FullPageLoading'
import RequireAuth from './RequireAuth'
import RequirePermission from './RequirePermission'
import RequireRole from './RequireRole'

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
 * 第 4 步路由表：
 * - 管理端：/admin/** 先 RequireAuth + RequireRole(admin)，布局内再按权限码守任务页
 * - 学生端：/papers/** 先 RequireAuth，再按 paper:read / question:read 守页面
 * - 守卫只决定“能不能看到页面”，越权请求最终由后端 403 兜底
 */
export default function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path={ROUTES.LOGIN} element={<LoginPage />} />
      <Route path={ROUTES.FORBIDDEN} element={<ForbiddenPage />} />

      <Route
        path="/admin"
        element={
          <RequireAuth>
            <RequireRole role={ROLES.ADMIN}>
              <AdminLayout />
            </RequireRole>
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="papers" replace />} />
        <Route path="papers" element={<AdminPaperListPage />} />
        <Route path="papers/:id" element={<AdminPaperQuestionsPage />} />
        <Route
          path="tasks"
          element={
            <RequirePermission permission={PERMISSIONS.TASK_READ}>
              <AdminTaskListPage />
            </RequirePermission>
          }
        />
      </Route>

      <Route
        path={ROUTES.STUDENT_PAPERS}
        element={
          <RequireAuth>
            <StudentLayout />
          </RequireAuth>
        }
      >
        <Route
          index
          element={
            <RequirePermission permission={PERMISSIONS.PAPER_READ}>
              <StudentPaperListPage />
            </RequirePermission>
          }
        />
        <Route
          path=":id"
          element={
            <RequirePermission permission={PERMISSIONS.QUESTION_READ}>
              <StudentPaperQuestionsPage />
            </RequirePermission>
          }
        />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
