# 模块二前端 · 验收交接说明

- 交接日期：2026-11-08
- 交给人：前端验收人（由组内指定）
- 依据：`docs/requirements/module-2/frontend-requirements.md` V0.4（验收项 F01–F18；本文为 2026-11-08 历史交接原文，确认规则调整见整改说明）
- 原型：`docs/requirements/module-2/frontend-prototype.html`（示意稿，非实施依据的视觉标准）

## 一、代码在哪

| 项目 | 内容 |
| --- | --- |
| 仓库 | `ShengShengRuEr-Team/ShengShengRuEr` |
| 分支 | `feature/m2-frontend-listening-papers`（已推送） |
| 提交 | `247328a`（基于 `develop` @ `b965a0f`） |
| 改动范围 | 仅 `frontend/src/`，17 个文件、+2472 行；**未改后端、未改数据库结构、未新增 npm 依赖** |
| PR | 已创建 [PR #12](https://github.com/ShengShengRuEr-Team/ShengShengRuEr/pull/12)（base `develop`）——真实 E2E 通过前请勿合并。本文其余内容为 2026-11-08 历史交接原文 |

拉取：

```bash
git fetch origin
git switch -c feature/m2-frontend-listening-papers origin/feature/m2-frontend-listening-papers
```

## 二、怎么跑起来

```bash
# 1) 后端（沿用现有开发环境）
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2) 前端
cd frontend
npm ci            # 按 lock 文件安装，勿用 npm install 改版本
npm run dev       # 固定 http://127.0.0.1:5173
```

账号：`admin / admin123`（管理员）、`student / student123`（学生）。
样例数据：`CET4_2025_06_1`，25 题 / 8 篇章 / 165 片段 / 音频 23:36，批次 `CET4_2025_06_1-0f92b33a001b`。

若本机库还没有数据，先按 `docs/development/module-2/delivery.md` 执行 `alembic upgrade head` → `app.seed` → 样例导入，再开始验收。
前端安装请用 `npm ci`（按 lock 文件），**不要用 `npm install`**，否则可能改动依赖版本。

## 三、验收范围

**覆盖（4 个页面）**

| 路由 | 角色 | 重点 |
| --- | --- | --- |
| `/admin/listening-papers` | 管理员 | 列表、筛选、状态三列、行内失败重试 |
| `/admin/listening-papers/1` | 管理员 | 分栏核对、检查摘要/抽屉、确认与取消开放、试听 |
| `/student/listening-papers` | 学生 | 只显示可访问试卷、"查看听力" |
| `/student/listening-papers/1` | 学生 | 分篇翻页、播放/暂停、本地拖动、题目只读 |

**不覆盖**：作答/判分（任务三）、模块三处理台、推荐与 RAG、视觉风格体系、移动端布局、后端接口改动。

## 四、开发自查结果（2026-11-08）

| 编号 | 结果 | 说明 |
| --- | --- | --- |
| F01 工程门禁 | PASS | `tsc -b` 0 错误；`vite build` 通过 |
| F02 路由与权限 | PASS | 学生访问 `/admin/*` 跳 `/403` |
| F03 管理端列表 | PASS | 真实数据正常；**500 错误态为浏览器层模拟**（Alert + 重试，空态不再误导） |
| F04 详情内容一致 | PASS | 8 篇章 / 第 1 篇 2 题 / 13 片段与接口一致 |
| F05 答案表达 | PARTIAL | 两个答案字母均显示；**本题库映射为恒等，重排提示未触发** |
| F06 检查结果 | PASS（模拟） | 通过 / 未通过（2 个问题）/ 尚未检查三态均验证；**未通过与尚未检查由拦截响应构造，未改数据** |
| F07 确认开放 | PASS | 真实操作成功，`is_visible` 变为 true |
| F08 取消开放 | PASS | 取消后学生列表为空；恢复后重新出现；详情/音频 404 未单独复测 |
| F09 学生端列表 | PASS | 无管理入口与后台状态词 |
| F10 学生端整卷 | PASS | 真实鼠标事件播放成功；失败有提示且题目仍可读 |
| F11 学生字段裁剪 | PASS | 页面无答案/解析/正文；无 `/admin/` 请求 |
| F12 只读约束 | PASS | 无交卷入口，选项不可选 |
| F13 异常与持久化 | PARTIAL | 500 提示与重试已验证（模拟）；**断库、重启后端未测** |
| F14 文档同步 | PASS | 基线表、截图、接口路径均已核实 |
| F15 篇章分页 | PASS | 篇数取 `passages.length`；翻篇不重置音频（2.46s→4.02s→4.91s）；翻篇回顶（331→0） |
| F16 音频适配 | PARTIAL | Blob 通道正常；**错误 Blob 解析与 URL 释放未单独观测** |
| F17 分栏同步 | PASS | 左右共享 `currentPassageId`，同时刷新 |
| F18 无当前批次 | PASS（模拟） | 显示"暂无当前批次"，确认/取消均禁用；**companion 响应为模拟构造** |

## 五、建议验收顺序（约 20 分钟）

1. `npm ci && npm run build`，确认零错误。
2. 管理员登录 → 列表：看三列状态是否与接口一致；筛选后进详情再返回，确认筛选还在。
3. 详情：切两个篇章，确认左右同时变且指向同一篇；对比答案、解析、原文。
4. 检查结果：点"查看检查结果"看抽屉；确认"确认开放/取消开放"的禁用条件符合文档 §4.2。
5. 试听：点"试听音频"，确认能播、能拖进度。
6. 学生登录 → 列表 → 进入整卷：播放、拖进度、翻篇（重点看音频是否被打断、是否回到顶部）。
7. 打开 DevTools Network：学生端**不应出现**任何 `/admin/` 请求。
8. 学生直接访问 `/admin/listening-papers`：应跳 `/403`。

## 六、已知限制（不是缺陷，请勿按缺陷记）

1. 页面**不能重新执行检查**，只能读最近一次记录；数据修好后需跑导入/检查工具（需求 D8）。
2. 音频**整段下载**后播放，不边下边播、拖动不产生服务端请求；`Range` 由后端单独验证（D5）。
3. 取消开放只约束**新请求**，不追溯已打开页面与已下载音频（F08）。
4. 管理端列表状态是**逐卷补调**（1+2N），超过 20 套自动降级为"仅基本信息"（D3）。
5. 学生端不显示答案/解析/正文，是**服务端裁剪**的结果（需求 §1.4）。
6. 题目只读、无交卷入口，是**本轮范围**（作答属任务三）。
7. 25 题 `review_status` 均为"待审核"、B16 人工核对未完成——页面如实显示，不代表内容已验收。
8. **开发模式（`npm run dev`）下音频会请求两次**：`React.StrictMode` 会执行两次 effect，第一次在组件卸载/重挂时被取消并释放。Network 里看到两条 `audio` 记录、其中一条 `(canceled)` 属正常，**不是重复下载缺陷**；`npm run build` 的生产构建没有该行为。

## 七、对开发库的影响（验收前请知悉）

开发自查时为验证 F07/F08，对试卷 `id=1` 做过一次"取消开放 → 确认开放"：

- 新增 2 条 `visibility_audit_logs`、1 条 `content_checks`；
- 当前状态已复核：`is_current=true`、`check_passed=true`、`is_visible=true`。

若验收需要干净数据，建议在独立库重跑迁移与导入后再验。

## 八、反馈方式

问题请按「页面 / 操作步骤 / 期望 / 实际 / 截图」记录，附对应 F 编号，发回后按最小改动修正并复验。
