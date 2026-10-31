# frontend

负责浏览器端界面：登录、管理端试卷 / 题目 / 任务页、学生端试卷 / 题目页，以及调用模块一后端 API 的适配层。

## 当前状态（2026-10-31）

已完成 **第 1–3 步**：

- 第 1 步：Vite + React + TypeScript + Ant Design 脚手架，可启动、可构建。
- 第 2 步：axios 封装（统一外壳解包、Bearer 注入、401 / 403 处理）、AuthContext、token 存储、5 个权限码常量，以及 9 个接口的类型与请求函数。
- 第 3 步：`BrowserRouter` 路由骨架、登录页（真实登录 + 错误提示 + `?redirect=` 回跳 + 开放重定向防护）、`/` 按角色分流、`/403` 可用占位页；5 个业务路由先挂占位页。

路由守卫、两套布局与 7 个业务页面在后续步骤接入。

## 技术栈（版本已锁定）

| 包 | 精确版本 | 用途 |
| --- | --- | --- |
| react / react-dom | 19.3.1 | UI 运行时 |
| react-router-dom | 7.18.5 | 静态路由表 + 组件级守卫 |
| antd | 6.6.8 | 表格、表单、菜单等后台组件 |
| @ant-design/icons | 6.3.4 | 图标 |
| axios | 1.21.0 | 请求实例与拦截器 |
| vite | 8.3.5 | 开发服务器与构建 |
| @vitejs/plugin-react | 5.2.0 | React 插件（不选 6.x，peer 依赖更少） |
| typescript | 6.0.3 | 类型检查（不使用 7.x） |
| @types/react / @types/react-dom | 19.3.0 | 类型声明 |

`package.json` 中的直接依赖**全部写精确版本，禁止 `^` / `~`**；传递依赖由 `package-lock.json` 锁定，锁文件必须提交。升级依赖时同步改 `package.json` 与锁文件，并重新验证构建。选型理由见 [技术决策 0002](../docs/decisions/0002-frontend-stack.md)。

## 环境要求

- Node.js 24.14.0（vite 8 要求 `^20.19.0` 或 `>=22.12.0`）
- npm 11.9.0

## 安装与启动

```bash
cd frontend
npm install
npm run dev
```

开发地址固定为 `http://127.0.0.1:5173`。`vite.config.ts` 里设置了 `strictPort: true`，端口被占用会直接报错，避免自动换端口后与后端 CORS 白名单不一致（后端只放行 `localhost:5173` 和 `127.0.0.1:5173`）。

如果所在环境的 npm 缓存目录不可写，把缓存重定向到本目录（`.cache/` 已被根 `.gitignore` 忽略）：

```bash
npm install --cache .cache/npm --no-audit --no-fund
```

其他命令：

```bash
npm run typecheck   # 只跑 tsc -b
npm run build       # tsc -b + vite build
npm run preview     # 预览 dist/
```

## 目录结构

```text
frontend/
├─ index.html
├─ package.json / package-lock.json
├─ tsconfig.json / tsconfig.app.json / tsconfig.node.json
├─ vite.config.ts
├─ .env.example
└─ src/
   ├─ main.tsx              入口（BrowserRouter + antd reset.css）
   ├─ App.tsx               全局 Provider 与路由出口
   ├─ vite-env.d.ts         环境变量类型
   ├─ styles/global.css
   ├─ api/                  请求封装、DTO 类型、snake_case → camelCase 适配（已实现）
   ├─ auth/                 AuthContext、token 存储、401 跳转（已实现）
   ├─ constants/            权限码 / 角色常量（已实现）
   ├─ router/               路由表（已实现骨架，第 4 步补守卫）
   ├─ layouts/              管理端侧边栏 / 学生端顶部导航（待实现）
   └─ pages/                登录页、403 已实现；5 个业务页为占位（第 5 / 6 步）
```

## 已验证（2026-10-31）

- `npm run build`：`tsc -b` 零错误，`vite build` 通过（antd 全量引入，单 chunk 偏大，后续按路由拆分）。
- 拦截器行为用本地 mock 服务验证 8 项：baseURL 回退、login / getInfo 外壳解包、Bearer 注入、403 提示不跳转、401 清 token 并跳 `/login?redirect=...`、登录页 401 不重复跳转、HTTP 200 + `code !== 200` 抛 `ApiError`、缺少外壳抛 `ApiError`；全部通过。
- 第 3 步用无头 Edge + DevTools Protocol 跑通 9 项：未登录访问 `/` 跳登录、管理员登录落 `/admin/papers`、token 写入 `ssre_access_token`、401 跳 `/login?redirect=/admin/tasks`、登录后回跳原路径、学生登录落 `/papers`、未知路径回角色首页、`/403` 可访问、错误口令停留登录页并提示；全部通过。真实后端联调在第 8 步执行。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | 后端基础地址；代码内已提供同值回退 |

- 只有 `VITE_` 前缀的变量会被打包进浏览器，**不得放任何密钥**。
- 本地覆盖写 `.env.local`（已被根 `.gitignore` 忽略），字段样例见 `.env.example`。
- 开发期直连后端 8000，不使用 Vite proxy；后端 CORS 已按 5173 配置。

## 页面与路由（按模块一开发文档 v0.2 第 5 章）

| 路径 | 页面 | 角色 | 权限 | 状态 |
| --- | --- | --- | --- | --- |
| `/login` | 登录页 | 公开 | — | 已实现（第 3 步） |
| `/admin/papers` | 管理端试卷列表 | admin | `paper:read` | 路由占位（第 5 步） |
| `/admin/papers/:id` | 管理端题目页（含答案 / 解析 / 原文） | admin | `question:read_sensitive` | 路由占位（第 5 步） |
| `/admin/tasks` | 管理端任务页 | admin | `task:read` | 路由占位（第 5 步） |
| `/papers` | 学生端试卷列表 | student | `paper:read` | 路由占位（第 6 步） |
| `/papers/:id` | 学生端题目页（无答案 / 解析 / 原文） | student | `question:read` | 路由占位（第 6 步） |
| `/403` | 无权限页 | 公开 | — | 可用占位（第 7 步完善视觉） |

`/` 按角色重定向：admin → `/admin/papers`，student → `/papers`。

## 实现约定

- **身份与权限以后端为准**：`GET /api/v1/getInfo` 返回的 `roles` / `permissions` 是唯一依据，前端只做菜单显隐与路由跳转；前端隐藏不等于安全，越权请求最终由后端 403 兜底。
- **学生端不渲染敏感字段**：`correct_option`、`explanation_text`、`transcript_text` 只出现在管理端题目页。学生接口本身不返回这些字段，前端也只在管理端 DTO 类型中声明。
- **token 存储**：`localStorage`，key 为 `ssre_access_token`。
- **401 / 403**：401 清 token 与登录态，跳 `/login?redirect=<当前路径>`，不在拦截器里弹窗；403 不跳转，用 `message.error(msg)` 提示（通过 antd `App.useApp()` 的模块级桥，避免静态方法脱离上下文）。
- **字段命名**：请求 / 响应 JSON 保持 `snake_case`，在 `src/api/adapters.ts` 转成 `camelCase` 视图模型后再进入组件。
- **命名**：按 [命名规范](../docs/naming-conventions.md)；页面与 UI 组件用 `PascalCase`。`useXxx.ts` 是 React 社区惯例特例。
- **XSS**：不渲染不可信 HTML；token 放 localStorage 的残余风险由「不渲染不可信 HTML + 后续 CSP」缓解。
- 本期不引入 ESLint / Prettier，质量门禁为 `tsc -b` + `vite build`，避免为小规模页面引入未锁定版本的工具链。

## 关联文档

- [技术决策 0002：模块一前端技术栈](../docs/decisions/0002-frontend-stack.md)
- [命名规范](../docs/naming-conventions.md)
- [API 契约](../docs/api/README.md)
- 《模块一开发文档 v0.2》第 5 章（外部工作目录，未入库；本 README 的版本与页面信息以其为准）
