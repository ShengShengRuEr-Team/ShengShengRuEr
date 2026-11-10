# frontend

浏览器端界面：登录/身份分流、管理端题库管理、学生端听力练习，以及对应的接口适配层。

Windows 首次运行请先阅读 [本地启动指南](../docs/development/startup-guide.md)，按顺序准备数据库、后端与前端，并使用锁文件安装依赖。

## 当前状态（2026-11-08）

模块二前端已实现，共 8 个页面：

- **登录页** `/login`：真实登录、错误提示、`?redirect=` 回跳、开放重定向防护
- **管理端首页** `/admin`：仅 `admin` 角色可进
- **管理端・试卷列表** `/admin/listening-papers`：三状态列（当前批次 / 检查结果 / 开放状态）、级别与年份本地筛选（写入 URL）、逐卷补调状态、行级失败重试
- **管理端・试卷详情** `/admin/listening-papers/:id`：原文与题目左右分栏（共享篇章状态）、检查摘要与抽屉、确认/取消开放、试听音频
- **学生端首页** `/student`：仅 `student` 角色可进，不出现任何管理入口
- **学生端・听力列表** `/student/listening-papers`：只显示可访问试卷，"查看听力"入口
- **学生端・整卷页** `/student/listening-papers/:id`：按篇章分页、播放器页面级常驻、题目只读（无作答入口）
- **无权限页** `/403`：展示当前身份，按角色返回首页

关键能力：

- Vite + React + TypeScript + Ant Design 脚手架，可启动、可构建
- 两套 axios 通道：JSON 接口（`{code,msg,data}` 外壳、Bearer、401/403 分发）与**音频二进制**（`responseType: blob`，绕开 JSON 外壳拦截器）
- 音频整段下载后本地播放，支持播放/暂停、进度拖动、音量、失败重试；组件卸载/切换时取消请求并释放对象 URL
- 状态标签严格区分「当前批次 / 检查结果 / 开放许可 / 审核状态」，不合并为"完成"
- 路由守卫 `RequireAuth` / `RequireRole`；页面级懒加载

## 技术栈（版本已锁定）

| 包 | 精确版本 | 用途 |
| --- | --- | --- |
| react / react-dom | 19.3.1 | UI 运行时 |
| react-router-dom | 7.18.5 | 静态路由表 + 组件级守卫 |
| antd | 6.6.8 | 表格、卡片、抽屉、表单等组件 |
| @ant-design/icons | 6.3.4 | 图标 |
| axios | 1.21.0 | 请求实例与拦截器 |
| vite | 8.3.5 | 开发服务器与构建 |
| @vitejs/plugin-react | 5.2.0 | React 插件 |
| typescript | 6.0.3 | 类型检查 |
| @types/react / @types/react-dom | 19.3.0 | 类型声明 |

`package.json` 的直接依赖**全部写精确版本，禁止 `^` / `~`**；传递依赖由 `package-lock.json` 锁定。

## 环境要求

- Node.js 24.14.0（vite 8 要求 `^20.19.0` 或 `>=22.12.0`；本机 22.x 亦可运行）
- npm 11.9.0

## 安装与启动

```bash
cd frontend
npm ci            # 按 package-lock.json 安装，不要用 npm install 改动依赖版本
npm run dev
```

开发地址固定 `http://127.0.0.1:5173`。`vite.config.ts` 设置了 `strictPort: true`，端口被占用会直接报错，避免自动换端口后与后端 CORS 白名单不一致（后端只放行 `localhost:5173` 与 `127.0.0.1:5173`）。

npm 缓存目录不可写时，把缓存重定向到本目录（`.cache/` 已被根 `.gitignore` 忽略）：

```bash
npm ci --cache .cache/npm --no-audit --no-fund
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
   ├─ styles/global.css
   ├─ api/
   │  ├─ client.ts          JSON 请求实例、外壳解包、Bearer、401/403
   │  ├─ audio.ts           音频二进制通道（Blob、错误体解析、Abort、对象 URL 释放）
   │  ├─ listening.ts       模块二 6 个接口
   │  ├─ types.ts           后端 DTO（snake_case）
   │  ├─ adapters.ts        DTO → camelCase 视图模型
   │  └─ admin.ts / auth.ts / api-error.ts
   ├─ auth/                 AuthContext、token 存储、401 跳转
   ├─ constants/            角色与路由常量
   ├─ router/               路由表 + RequireAuth / RequireRole
   ├─ layouts/              管理端侧边菜单 / 学生端顶部导航
   ├─ pages/
   │  ├─ LoginPage.tsx / ForbiddenPage.tsx
   │  ├─ admin/             首页、试卷列表、试卷详情
   │  └─ student/           首页、听力列表、整卷页
   ├─ ui/                   播放器、状态标签、加载态、message 桥、退出登录
   └─ utils/                时长格式化、限并发
```

## 页面与路由

| 路径 | 页面 | 角色 |
| --- | --- | --- |
| `/login` | 登录页 | 公开 |
| `/admin` | 管理端首页 | `admin` |
| `/admin/listening-papers` | 试卷列表 | `admin` |
| `/admin/listening-papers/:examPaperId` | 试卷详情（检查结果为页内抽屉，无独立路由） | `admin` |
| `/student` | 学生端首页 | `student` |
| `/student/listening-papers` | 听力试卷列表 | `student` |
| `/student/listening-papers/:examPaperId` | 整卷听力页 | `student` |
| `/403` | 无权限页 | 公开 |

`/` 按角色重定向：`admin` → `/admin`，`student` → `/student`。

**越权处理**：前端守卫拦到 `/403`；即使绕过前端直接调管理接口，后端同样返回 403。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | 后端基础地址；代码内已提供同值回退 |

- 只有 `VITE_` 前缀的变量会被打包进浏览器，**不得放任何密钥**。
- 本地覆盖写 `.env.local`（已被根 `.gitignore` 忽略），字段样例见 `.env.example`。

## 实现约定

- **身份以后端为准**：`GET /api/v1/getInfo` 返回的 `roles` 是唯一依据；前端只做菜单显隐与路由分流。
- **token 存储**：`localStorage`，key 为 `ssre_access_token`。
- **401 / 403**：401 清 token 与登录态，跳 `/login?redirect=<当前路径>`；403 不跳转，用 `message.error(msg)` 提示。
- **字段命名**：请求/响应 JSON 保持 `snake_case`，在 `api/adapters.ts` 转成 camelCase 后进入组件。
- **音频**：不得用 `api/client.ts` 的实例下载音频——它强制校验 `response.data.code`，会以"缺少统一响应外壳"拒绝 200 的二进制响应；必须走 `api/audio.ts`。
- **状态口径**：`is_current` / `check_passed` / `is_visible` / `review_status` 分别展示；"已确认开放"是许可，不等于"当前可访问"。
- **筛选**：管理端列表的级别/年份写入 URL query，从详情返回时通过 `location.state.listSearch` 带回。
- **XSS**：不渲染不可信 HTML；原文按纯文本 + `white-space: pre-wrap`。
- 本期不引入 ESLint / Prettier，质量门禁为 `tsc -b` + `vite build`。

## 已知限制

1. 页面**不能单独重新执行检查**：`GET /checks` 只读最近记录；确认开放动作本身会触发一次检查（失败返回 400 并留下新记录），因此「尚未检查 / 检查未通过」不再禁用确认按钮。
2. 音频**整段下载**后播放，不边下边播；进度拖动不产生服务端 `Range` 请求（`Range` 由后端接口单独验证）。
3. 取消开放只约束**新请求**，不追溯已打开页面与已下载音频。
4. 管理端列表状态为**逐卷补调**（`1 + 2N` 次请求），超过 20 套自动降级为"仅基本信息"。
5. 开发模式（`npm run dev`）下 `React.StrictMode` 会执行两次 effect，音频可能出现两条请求、其中一条 `(canceled)`，**不是重复下载缺陷**；生产构建无此行为。
6. 学生端不显示答案/解析/正文，是**服务端裁剪**的结果；题目只读，作答功能属任务三。

## 相关文档

- 需求与验收卡（F01–F18）：`docs/requirements/module-2/frontend-requirements.md`
- 页面原型（线框示意）：`docs/requirements/module-2/frontend-prototype.html`
- 开发与实现记录：`docs/acceptance/module-2/frontend-implementation.md`
- 验收交接说明：`docs/acceptance/module-2/frontend-handoff.md`
- 独立验收报告：`docs/acceptance/module-2/frontend-acceptance-20261109.md`
- 前端验收截图：`docs/acceptance/module-2/screenshots/`
