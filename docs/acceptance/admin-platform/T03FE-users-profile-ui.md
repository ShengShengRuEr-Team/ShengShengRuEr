# T03-FE 用户管理 / 个人中心页面 · 证据记录

| 字段 | 值 |
| --- | --- |
| ac_id | AC-01/02/03/04（页面部分）、AC-05/06（个人中心）、AC-28（前端权限显隐）、AC-33（共用交互） |
| requirement_ids | ADM-USR01/02/03、ADM-SELF01/02、ADM-PERM01 |
| executor | 开发实施人（lead agent） |
| executed_at | 2026-11-17 13:55—14:05（Asia/Shanghai） |
| commit_sha | 起点 `5aec78d`；T03-FE 本地提交（不 push） |
| workspace_state | 仅前端改动；后端 `git diff HEAD -- backend` 为空 |
| environment | Windows；Node 24.14.0；前端测试环境 jsdom |
| migration_heads | 无迁移改动，仍 `0007_admin_audit_events` |
| dependency_versions | 无新增、无升级 |
| result | **PASS** |

## 1 文件落点

**新增**

| 文件 | 说明 |
| --- | --- |
| `api/admin/users.ts` | 9 个用户/本人接口调用（路径/参数与后端逐字一致） |
| `utils/passwordRules.ts` | 用户名/密码/reason/昵称前端校验，规则与后端逐字一致 |
| `ui/admin/useUserFilters.ts` | 筛选与分页的 URL 唯一来源 |
| `ui/admin/UserCreateModal.tsx` | 创建用户（student 默认，可选 admin） |
| `ui/admin/UserNicknameModal.tsx` | 改昵称 |
| `ui/admin/UserStatusModal.tsx` | 启停 + reason + 结果提示 |
| `ui/admin/ResetPasswordModal.tsx` | 重置密码 + reason + 撤销会话提示 |
| `ui/admin/UserDetailDrawer.tsx` | 详情（按 id 拉取，404/500 可重试） |
| `pages/admin/UsersPage.tsx`、`pages/admin/ProfilePage.tsx` | 两个页面 |

**修改**

| 文件 | 改动 |
| --- | --- |
| `api/admin/types.ts` | 追加用户/本人 DTO |
| `auth/AuthContext.tsx` | 新增 `clearLocalSession()`（仅清本地，不请求服务端） |
| `ui/message.ts` | 新增 `showSuccess()`（与 `showError` 同一实例） |
| `constants/routes.ts` | `ADMIN_USERS`、`ADMIN_PROFILE` |
| `router/index.tsx` | 两条路由 + `RequirePermission` |
| `layouts/AdminLayout.tsx` | 菜单项与权限过滤；导出纯函数 `visibleAdminMenu` 供测试 |
| 既有测试 `LoginLogsPage.test.tsx`、`Can.test.tsx` | 仅在 mock 的 AuthContext 值中补 `clearLocalSession: vi.fn()`，**未改任何断言** |

## 2 接口与权限

| 动作 | 接口 | 权限 |
| --- | --- | --- |
| 列表/详情 | `GET /admin/users`、`GET /admin/users/{id}` | `admin:user:read` |
| 创建 | `POST /admin/users` | `admin:user:create` |
| 改昵称 | `PATCH /admin/users/{id}` | `admin:user:update` |
| 启停 | `POST /admin/users/{id}/status` | `admin:user:status` |
| 重置密码 | `POST /admin/users/{id}/reset-password` | `admin:user:resetPassword` |
| 本人查看 | `GET /admin/me` | `admin:self:read` |
| 本人改昵称 | `PATCH /admin/me` | `admin:self:update` |
| 本人改密 | `POST /admin/me/password` | `admin:self:password` |

路由守卫：`/admin/users` → `admin:user:read`，`/admin/profile` → `admin:self:read`；菜单同权限过滤。无分配角色、无解锁、无删除入口。

## 3 错误与结果语义

- 401 由 `client.ts` 清会话跳登录；403 只提示不跳转。
- 404 详情显示「用户不存在或已被删除」并可重试。
- 400（重名/停用本人/最后管理员/重置本人/旧密码错误等）显示后端文案；改密 400 只清新密码字段。
- 500/网络：显示「结果未确认，请刷新核实」，按钮恢复可点，不自动重放。
- 启停 `changed=false` → 提示「状态未变化」，不报错。
- 改密 200 `reauth_required` → `clearLocalSession()` → `navigate('/login', {replace:true})`，提示「密码已修改，请重新登录」，不重发请求。

## 4 测试

```text
$ npm test -- --run
Test Files  28 passed (28)
Tests       171 passed (171)
$ npm run typecheck → 通过
$ npm run build → ✓ built
```

新增 23 例：

| 文件 | 用例 |
| --- | --- |
| `utils/passwordRules.test.ts`（6） | 用户名边界、密码长度/字符集、**中文 72 字节边界**、reason、昵称 |
| `api/admin/users.test.ts`（3） | 列表参数清洗、9 个接口路径/数据、本人接口 |
| `pages/admin/UsersPage.test.tsx`（7） | 列表标签、无权限不发请求、500 错误重试、筛选写 URL、无创建权限隐藏按钮、创建校验与提交、启停同状态提示 |
| `pages/admin/ProfilePage.test.tsx`（4） | 展示本人、改昵称、改密成功清认证并跳登录、旧密码 400 |
| `layouts/AdminLayout.test.tsx`（2） | 有/无权限时菜单显隐 |

既有 148 例全绿（171 = 148 + 23），未修改任何旧断言。

## 5 后端零改动证据

```text
$ git diff --stat HEAD -- backend   → （空）
$ git status --short backend        → （空）
```

未改 0001–0007、未碰开发库、未新增依赖/权限码/事件类型。

## 6 未覆盖项

- 页面级端到端（真实浏览器）留 T09。
- 管理端首页/监控/任务/文档页面属 T05–T08。
- 分配角色、解锁、删除按文档不提供，未实现。

## 7 结论

**PASS**。两页功能、权限显隐、错误态与改密强制重登均按 §4.3/§11.2/§11.3 实现；前端 171 全绿，typecheck/build 通过，后端零改动。
