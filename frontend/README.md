# frontend

浏览器端界面：登录/身份分流、管理端题库管理、学生端听力练习，以及对应的接口适配层。

Windows 首次运行请先阅读 [本地启动指南](../docs/development/startup-guide.md)，按顺序准备数据库、后端与前端，并使用锁文件安装依赖。

## 当前状态（2026-11-16）

模块二前端 + 作答系统（任务二）已实现：

- **登录页** `/login`：真实登录、错误提示、`?redirect=` 回跳、开放重定向防护
- **管理端首页** `/admin`：仅 `admin` 角色可进
- **管理端・试卷列表** `/admin/listening-papers`：三状态列（当前批次 / 检查结果 / 开放状态）、级别与年份本地筛选（写入 URL）、逐卷补调状态、行级失败重试
- **管理端・试卷详情** `/admin/listening-papers/:id`：原文与题目左右分栏（共享篇章状态）、检查摘要与抽屉、确认/取消开放、试听音频
- **学生端首页** `/student`：仅 `student` 角色可进，不出现任何管理入口
- **学生端・听力列表** `/student/listening-papers`：只显示可访问试卷；入口四态（开始作答 / 继续作答 x/y / 结果待确认 / 已提交），只读本机草稿/信封/标记，不逐卷查 API-3
- **学生端・整卷页** `/student/listening-papers/:id`：作答（选项/清除/标记/答题卡/翻篇/交卷）、本机草稿与续答、`pending`/`pending-unrecoverable` 冻结、已提交只读汇总 + 中性题号导航、播放器页面级常驻
- **无权限页** `/403`：展示当前身份，按角色返回首页

作答系统能力：

- 作答选择/清除/标记/整卷计数；键盘方向键切换选项，状态不只靠颜色
- 本机草稿（30 天、每用户 10 份）与独立提交信封（不参与淘汰）；`仅当前浏览器`，不跨设备
- 提交：`Idempotency-Key` UUIDv4、先写信封并读回、同键重试、E08/E09/E04/未知错误保护、双击防护
- 终态：先写共享提交标记 → `storage` 事件冻结其他标签 → 删草稿/信封；保存与 `pagehide` flush 前检查终态，防复活
- API-3 分层解析：已提交有/无汇总、未提交、状态冲突、查询不可用；冲突只保护性冻结
- 桌面布局：`>=1280` 右侧 sticky 答题卡，`[1024,1280)` 顶部折叠；`<1024` 不承诺

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
npm test            # Vitest（jsdom + RTL），17 files / 117 tests
npm run test:watch  # 监听模式
```

测试依赖：Vitest 5.1.0、jsdom 28.1.0、RTL 16.3.3、user-event 14.6.1、jest-dom 6.9.1。
不接 CI、不设覆盖率门槛（按需求）。真实浏览器 E2E 脚本：`node scripts/e2e_attempt.mjs`（需要后端 + dev server，见验收指南）。

## 目录结构

```text
frontend/
├─ index.html
├─ package.json / package-lock.json
├─ tsconfig.json / tsconfig.app.json / tsconfig.node.json
├─ vite.config.ts / vitest.config.ts
├─ .env.example
└─ src/
   ├─ main.tsx              入口（BrowserRouter + antd reset.css）
   ├─ App.tsx               全局 Provider 与路由出口
   ├─ styles/global.css
   ├─ api/
   │  ├─ client.ts          JSON 请求实例、外壳解包、Bearer、401/403
   │  ├─ audio.ts           音频二进制通道（Blob、错误体解析、Abort、对象 URL 释放）
   │  ├─ listening.ts       模块二 6 个接口
   │  ├─ attempts.ts        API-1 提交 / API-3 状态查询
   │  ├─ types.ts           后端 DTO（snake_case）
   │  ├─ adapters.ts        DTO → camelCase 视图模型 + API-3 分层解析
   │  └─ admin.ts / auth.ts / api-error.ts
   ├─ attempt/              草稿/信封/标记 codec+storage+payload+errors+retention+state+submit
   ├─ auth/                 AuthContext、token 存储、401 跳转
   ├─ constants/            角色与路由常量
   ├─ router/               路由表 + RequireAuth / RequireRole
   ├─ layouts/              管理端侧边菜单 / 学生端顶部导航
   ├─ pages/
   │  ├─ LoginPage.tsx / ForbiddenPage.tsx
   │  ├─ admin/             首页、试卷列表、试卷详情
   │  └─ student/           首页、听力列表、整卷页、attempt/ 作答组件
   ├─ test/                 setup、fixtures、smoke
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
- 本期不引入 ESLint / Prettier；质量门禁为 `tsc -b` + `vite build` + `npm test`。

## 已知限制

1. 页面**不能单独重新执行检查**：`GET /checks` 只读最近记录；确认开放动作本身会触发一次检查（失败返回 400 并留下新记录），因此「尚未检查 / 检查未通过」不再禁用确认按钮。
2. 音频**整段下载**后播放，不边下边播；进度拖动不产生服务端 `Range` 请求（`Range` 由后端接口单独验证）。
3. 取消开放只约束**新请求**，不追溯已打开页面与已下载音频。
4. 管理端列表状态为**逐卷补调**（`1 + 2N` 次请求），超过 20 套自动降级为"仅基本信息"。
5. 开发模式（`npm run dev`）下 `React.StrictMode` 会执行两次 effect，音频可能出现两条请求、其中一条 `(canceled)`，**不是重复下载缺陷**；生产构建无此行为。
6. 学生端不显示答案/解析/正文，是**服务端裁剪**的结果；作答后进入只读，无“再答一次”。
7. 作答草稿只保存在 `localStorage`（`ssre.attempt*`），不跨设备；共享设备可被开发者工具查看。
8. 同一试卷仅可提交一次（后端 `ATTEMPT_LIMIT_PER_PAPER = 1`）；幂等键保留期未知，自动重试关闭，需手动同键重试。
9. `<1024px` 不承诺；手机/平板不在本轮验收范围。

## 相关文档

- 需求与验收卡（F01–F18）：`docs/requirements/module-2/frontend-requirements.md`
- 页面原型（线框示意）：`docs/requirements/module-2/frontend-prototype.html`
- 作答系统需求口径同步：`docs/requirements/attempt-system/attempt-system-sync-20261116.md`
- 开发与实现记录：`docs/development/attempt-system/api.md`、`implementation.md`
- 作答系统验收交接：`docs/acceptance/attempt-system/验收交接文档.md`（PR16 整改说明：`PR16-整改说明-20261116.md`）
- 前端验收截图：`docs/acceptance/module-2/screenshots/`、`docs/acceptance/attempt-system/screenshots/`
