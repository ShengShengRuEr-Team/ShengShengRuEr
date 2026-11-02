# frontend

负责浏览器端界面：登录页、管理端与学生端页面框架，以及调用模块一后端 API 的适配层。

## 当前状态（2026-10-31）

模块一前端已实现，页面共 4 个：

- **登录页**：真实登录、错误提示、`?redirect=` 回跳、开放重定向防护
- **管理端首页** `/admin`：仅 `admin` 角色可进，进入后调用管理端接口
- **学生端首页** `/student`：仅 `student` 角色可进，不出现任何管理入口
- **无权限页** `/403`：展示当前身份，按角色返回首页

已完成的能力：

- Vite + React + TypeScript + Ant Design 脚手架，可启动、可构建
- axios 封装：统一外壳解包、Bearer 注入、401 / 403 分发
- AuthContext：token 持久化、刷新页面自动 `getInfo`、登录 / 退出
- 路由：`BrowserRouter` 静态路由表 + `RequireAuth` / `RequireRole` 守卫
- 布局：管理端侧边菜单、学生端顶部导航，学生端不出现管理端入口
- 路由级代码分割：页面 `React.lazy` + 单个 `Suspense`

## 技术栈（版本已锁定）

| 包 | 精确版本 | 用途 |
| --- | --- | --- |
| react / react-dom | 19.3.1 | UI 运行时 |
| react-router-dom | 7.18.5 | 静态路由表 + 组件级守卫 |
| antd | 6.6.8 | 表单、菜单、卡片等组件 |
| @ant-design/icons | 6.3.4 | 图标 |
| axios | 1.21.0 | 请求实例与拦截器 |
| vite | 8.3.5 | 开发服务器与构建 |
| @vitejs/plugin-react | 5.2.0 | React 插件（不选 6.x，peer 依赖更少） |
| typescript | 6.0.3 | 类型检查（不使用 7.x） |
| @types/react / @types/react-dom | 19.3.0 | 类型声明 |

`package.json` 中的直接依赖**全部写精确版本，禁止 `^` / `~`**；传递依赖由 `package-lock.json` 锁定，锁文件必须提交。

选型理由见 [技术决策 0002](../docs/decisions/0002-frontend-stack.md)。

## 环境要求

- Node.js 24.14.0（vite 8 要求 `^20.19.0` 或 `>=22.12.0`）
- npm 11.9.0

## 安装与启动

```bash
cd frontend
npm install
npm run dev
```

开发地址固定为 `http://127.0.0.1:5173`。`vite.config.ts` 设置了 `strictPort: true`，
端口被占用会直接报错，避免自动换端口后与后端 CORS 白名单不一致
（后端只放行 `localhost:5173` 和 `127.0.0.1:5173`）。

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
   ├─ api/                  请求封装、DTO 类型、认证接口、snake_case 适配
   ├─ auth/                 AuthContext、token 存储、401 跳转
   ├─ constants/            角色与路由常量
   ├─ router/               路由表 + RequireAuth / RequireRole
   ├─ layouts/              管理端侧边菜单 / 学生端顶部导航
   ├─ pages/                4 个页面（登录 / 管理端首页 / 学生端首页 / 403）
   └─ ui/                   加载态、message 桥、退出登录按钮
```

## 页面与路由

| 路径 | 页面 | 角色 | 说明 |
| --- | --- | --- | --- |
| `/login` | 登录页 | 公开 | 登录成功后按角色跳转；已登录访问会跳回角色首页 |
| `/admin` | 管理端首页 | `admin` | 加载时调用 `/api/v1/admin/overview` |
| `/student` | 学生端首页 | `student` | 无任何管理入口 |
| `/403` | 无权限页 | 公开 | 展示当前身份，按角色返回首页 |

`/` 按角色重定向：`admin` → `/admin`，`student` → `/student`。

**角色不是管理员时访问 `/admin`**：前端守卫拦到 `/403`；
即使绕过前端直接调 `/api/v1/admin/overview`，后端同样返回 403。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | 后端基础地址；代码内已提供同值回退 |

- 只有 `VITE_` 前缀的变量会被打包进浏览器，**不得放任何密钥**。
- 本地覆盖写 `.env.local`（已被根 `.gitignore` 忽略），字段样例见 `.env.example`。
- 开发期直连后端 8000，不使用 Vite proxy；后端 CORS 已按 5173 配置。

## 已验证（2026-10-31）

- `npm run typecheck`：`tsc -b` **零错误**。
- `npm run build`：`vite build` 通过，页面按路由拆分为独立 chunk。
- 拦截器行为（本地 mock 验证）：baseURL 回退、外壳解包、Bearer 注入、
  403 提示不跳转、401 清 token 并跳 `/login?redirect=...`、HTTP 200 但 `code !== 200` 抛 `ApiError`。
- 与真实后端联调：管理员登录进入 `/admin` 并成功调用管理端接口；
  学生登录进入 `/student` 且无管理菜单；学生访问 `/admin` 被拦到 `/403`；
  学生 token 调 `/api/v1/admin/overview` 返回 403；退出后回到 `/login` 且 token 已清除。

## 实现约定

- **身份以后端为准**：`GET /api/v1/getInfo` 返回的 `roles` 是唯一依据，
  前端只做菜单显隐与路由分流；前端隐藏不等于安全，越权请求最终由后端 403 兜底。
- **token 存储**：`localStorage`，key 为 `ssre_access_token`。
- **401 / 403**：401 清 token 与登录态，跳 `/login?redirect=<当前路径>`，不在拦截器里弹窗；
  403 不跳转，用 `message.error(msg)` 提示（通过 antd `App.useApp()` 的模块级桥，
  避免静态方法脱离上下文）。
- **字段命名**：请求 / 响应 JSON 保持 `snake_case`，在 `src/api/adapters.ts`
  转成 `camelCase` 视图模型后再进入组件。
- **命名**：按 [命名规范](../docs/naming-conventions.md)；页面与 UI 组件用 `PascalCase`。
  `useXxx.ts` 是 React 社区惯例特例。
- **XSS**：不渲染不可信 HTML；token 放 localStorage 的残余风险由
  「不渲染不可信 HTML + 后续 CSP」缓解。
- 本期不引入 ESLint / Prettier，质量门禁为 `tsc -b` + `vite build`。

## 一期边界

- 只实现模块一：登录、退出、身份区分与页面框架。
- **不包含**试卷列表、题目页、任务管理、作答判分等页面，这些在后续模块中实现。
