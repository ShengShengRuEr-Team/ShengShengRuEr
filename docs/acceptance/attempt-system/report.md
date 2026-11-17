# 作答系统任务卡回填报告

> 日期：2026-11-16  
> 仓库：`D:\ssre_V1\ShengShengRuEr`  
> 分支/基线：`main@846270b`（“稳定版：登录和题库管理”，已含 API-1 与 `0005_attempt_system` 迁移）  
> 版本：需求 V1.2 / 开发 V1.1 / 原型图集 V1.1（评审结论“通过”，签字按用户指示暂不处理）  
> 工作区：**有未提交改动**（本任务成果）；未提交、未推送、未合并。

## 0. 基线核查（DOC-01A）

| 检查 | 实际结果 | 说明 |
| --- | --- | --- |
| 分支/提交 | `main@846270b` | 本任务开始前工作区在 `feature/m2-frontend-listening-papers@c6e1b62`；该基线**无 API-1**。核对时远端 main 已前进到 846270b，移交给的实施环境切到 main 后，API-1/三表/`0005_attempt_system` 已在基线中 |
| API-1 | 已存在：`api/attempts.py`、`services/attempts.py`、`schemas_attempts.py`、`repositories/attempt_keys.py`、`attempt_content.py`、`db/models_attempt.py` | 契约冻结：路径/请求/错误码/判定顺序/限次不变 |
| 数据库迁移 | `alembic/versions/0005_attempt_system.py`（基线） | 发现并删除工作区遗留的重复迁移 `0005_attempts.py`（上一轮在旧基线自建，与基线同 revision 冲突）；**最终无新增/修改迁移** |
| 后端基线 | 265 pytest 全绿（含 API-1 既有用例） | 实际 Python 3.12.10（venv）、PostgreSQL 16（服务 `postgresql-x64-16`，监听 `127.0.0.1:5433`） |
| 前端基线 | typecheck/build 通过；无测试框架 | 实际 Node 24.14.0 / npm 11.9.0 |
| `backend/.env` | 写了 5432，实际服务在 5433 | 测试/启动一律通过环境变量覆盖端口；**未修改 `.env`、未输出密码** |
| P-03 保留期 | **未确认** | `KEY_RETENTION_POLICY = { kind: 'unknown' }`，自动重试关闭 |
| 原型 | 图集 V1.1 标注评审通过、签字表姓名/日期待回填 | 按用户指示本轮不处理签字 |
| 错误契约 | 前端错误白名单与后端 `schemas_attempts.py` 的 E03–E09 文案不一致（上一轮按旧基线自拟） | 已按基线真实文案/状态码对齐（见 §2 FE-03） |

**处置**：保留基线 API-1 不动，只新增 API-3 与前端作答域；删除重复迁移与重复消息模块 `core/attempt_messages.py`；前端错误白名单改为按真实 `status + msg` 匹配。

## 1. 任务卡逐项回填

### DOC-01A 需求/契约冻结与基线确认

- 状态：**PARTIAL**
- 实际改动：无应用代码；核查结论见 §0 与 `docs/development/attempt-system/api.md` §0
- 证据：`git log/status`、`alembic/versions/`、265 pytest
- 未覆盖：D6/D11 正式签字、UX-01 四方签字（用户指示暂不处理）
- 下一步：验收人确认基线（main@846270b 含 API-1）与“无新增迁移”结论

### UX-01 页面原型评审

- 状态：**PARTIAL**（评审结论“通过”；签字留痕未回填）
- 证据：`作答系统页面原型图集与说明_V1.1_20261114.md` §5.5
- 未覆盖：四方姓名/日期签字
- 下一步：按项目流程补签后关闭 UX-01

### BE-01 API-3 Schema 与汇总复用

- 状态：**PASS**
- 实际改动：新增 `backend/app/schemas_attempt_status.py`（`AttemptStatusData` 含 `check_status_invariants`、`AttemptStatusResponse` 复用 `ApiResponse`、`MSG_STATUS_SUCCESS`）；`services/attempts.py` 将私有 `_data_from_attempt` 提取为公开 `attempt_summary_from_attempt`（同实现，API-1 行为不变）
- 测试：`test_status_schema_invariants_rejected`、B-05/B-15/B-16
- 证据：`evidence/backend-pytest.txt`
- 未覆盖：无
- 下一步：无

### BE-02 API-3 单快照服务/仓储

- 状态：**PASS**
- 实际改动：新增 `backend/app/repositories/attempt_status.py`（一条 `select(Attempt, count().over())` + `limit(1)`）、`backend/app/services/attempt_status.py`（准入 404 + 汇总复用；只读、不 commit）
- 测试：`test_status_uses_single_window_statement`（监听 SQL 断言只有 1 条 `FROM attempts`，含窗口计数与 LIMIT）、`test_status_concurrent_with_submit_is_consistent`
- 证据：`evidence/backend-pytest.txt`；AC-43
- 未覆盖：未做大表 `EXPLAIN` 压测（索引 `ix_attempts_student_paper` 已存在）
- 下一步：可选归档执行计划

### BE-03 API-3 路由/权限/响应头

- 状态：**PASS**
- 实际改动：新增 `backend/app/api/attempt_status.py`（`GET /listening-papers/{id}/attempt-status`，`PathId`、`require_student`、`Cache-Control: no-store`、404 也带 no-store）；`app/main.py` 注册 router
- 测试：B-01/B-02/B-03/B-14；API-E2E
- 证据：`e2e-api-results.json`
- 未覆盖：无
- 下一步：无

### BE-04 API-3 后端测试

- 状态：**PASS**
- 实际改动：新增 `backend/tests/test_attempt_status_api.py`（12 项）、`backend/tests/attempt_support.py`（自包含数据工厂：试卷/批次/音频/呈现/可见性/第二学生）；`backend/tests/conftest.py` 增加作答数据清理夹具；`attempt_support` 清理顺序先删 attempts/answers/rejections 再删试卷
- 测试：B-01–B-16 + 单语句策略；全量 265 passed
- 证据：`evidence/backend-pytest.txt`
- 未覆盖：无
- 下一步：无

### FE-00 前端测试工具链

- 状态：**PASS**
- 实际改动：`frontend/package.json`（`test`/`test:watch`；devDeps：Vitest 5.1.0、jsdom 28.1.0、RTL 16.3.3、user-event 14.6.1、jest-dom 6.9.1、playwright-core 1.56.1）、`package-lock.json`、`vitest.config.ts`、`src/test/setup.ts`、smoke test
- 测试：`npm test` 17 files / 117 tests passed
- 证据：`evidence/frontend-test.txt`
- 未覆盖：无 CI（按需求不做）
- 下一步：无

### FE-01 API 客户端/DTO/适配器/结果类型

- 状态：**PASS**
- 实际改动：`api/types.ts` 仅加 DTO（`AttemptSubmitRequestDto/AttemptAnswerDto/PracticeScoreDto/AttemptSummaryDto/AttemptStatusDto`）；`api/adapters.ts` 加视图模型与 `toAttemptStatusResult`/`toAttemptSubmitSuccess`/`toAttemptSummary`（严格校验、冲突分层、`OptionLetter`/`isOptionLetter`）；`api/attempts.ts` 调 API-1/API-3
- 测试：`api/adapters.test.ts`（9 项）
- 证据：`evidence/frontend-test.txt`
- 未覆盖：无
- 下一步：无

### FE-02 草稿/信封/标记存储与 codec

- 状态：**PASS**
- 实际改动：`attempt/types.ts`、`attempt/codec.ts`、`attempt/storage.ts`（三对象分离、键命名空间、TTL 30 天、每用户 10 份淘汰、写后读回、损坏保护、写入前终态检查）
- 测试：`codec.test.ts`、`storage.test.ts`
- 未覆盖：无
- 下一步：无

### FE-03 payload/错误/保留期/状态机/提交编排

- 状态：**PASS**
- 实际改动：`attempt/payload.ts`（顺序/字母/去重/重建）、`attempt/errors.ts`（按真实后端 `status + msg`：E03/E14=404「资源不存在」、E04/E05/E07/E08/E09=400 各自文案、422 按状态）、`attempt/retention.ts`（unknown）、`attempt/state.ts`、`attempt/submit.ts`（first/replay/unknown/memory envelope/rebuild）
- 测试：`payload/errors/retention/submit` 单测
- 未覆盖：自动重试真实场景（P-03 未确认）
- 下一步：P-03 确认后仅改策略常量

### FE-04 作答组件

- 状态：**PASS**
- 实际改动：`pages/student/attempt/` 新增 `QuestionCard`、`AnswerSheet`、`SubmitConfirmModal`、`DraftBanner`、`SubmitSummaryPanel`、`PendingPanel`、`SubmitResultAlert`；`styles/global.css` 增加作答域样式与 1280/1024 断点
- 测试：C-01–C-07 组件测试
- 未覆盖：A-01 附录图例使用 CSS 近似
- 下一步：视觉走查

### FE-05 页面容器/状态门禁/恢复/已提交

- 状态：**PASS**
- 实际改动：重写 `pages/student/ListeningPaperPage.tsx`：详情→本机信封/草稿→API-3 门禁；五类页态（作答/pending/pending-unrecoverable/已提交/不可访问）；冲突冻结；API-3 404 不展示汇总；已提交清内存答案并中性导航
- 测试：`ListeningPaperPage.test.tsx`（12 项）+ `ListeningPaperPage.extra.test.tsx`（6 项）+ `ListeningPaperPage.review.test.tsx`（PR16 定向回归 12 项）；E2E
- 未覆盖：E04/401 页面级真实场景
- 下一步：补浏览器场景（见矩阵 BLOCKED）
- PR16 整改：一轮 F01（损坏信封优先保护）、F02（手动查询冲突冻结）、F06（同题数版本提示）、malformed 冻结、查询入口；二次 F08（冲突后 false 恢复）、F09（手动 malformed 冻结）

### FE-06 提交编排/pending/多标签/终态

- 状态：**PASS**（核心路径）
- 实际改动：确认→读/写信封→发送；内存信封 Modal；200/E08/E09/E04/明确失败/未知 400/500/401 分支；同键重试；双击防护（提交中禁用 + `inFlightRef`）；终态先写标记→取消 timer→删草稿/信封；storage 事件 + 写入前检查
- 测试：`submit.test.ts`、P（成功/E08/E09/未知 400/存储不可用/跨标签/写入前检查/双击/E03 重建）；R（F03 恢复冻结答案、F04 重新开始取消 timer）；E2E 多标签
- 未覆盖：跨标签“后台挂起/即将关闭”两态
- 下一步：Playwright 双页签脚本补两态
- PR16 整改：F03（E09 false 先恢复答案）、F04（重新开始二次确认 + 取消 timer）

### FE-07 自动保存/存储降级/401

- 状态：**PASS**（主路径）
- 实际改动：300ms 防抖写草稿+索引；`visibilitychange=hidden`/`pagehide` flush；两类写入前同步检查提交标记；`storage` 事件冻结其他标签；401 交给 client 清会话
- 测试：P（恢复/存储不可用/写入前检查/跨标签）；R（F05 卸载 flush）；U storage
- 未覆盖：401 真实回跳；quota 真实浏览器场景（组件测试覆盖）
- 下一步：补真实 401 场景
- PR16 整改：F05（SPA 站内离开卸载时 flush 最后一次作答）

### FE-08 文案/列表/首页/响应式

- 状态：**PASS**
- 实际改动：`ListeningPaperListPage.tsx` 四态（开始/继续/待确认/已提交）+ 已答 x/y；删除“查看听力/后续开放”；`HomePage.tsx` 文案；`global.css` 两档断点；README 补“本机草稿/仅桌面/仅一次/测试命令”
- 测试：`ListeningPaperListPage.test.tsx`；E2E 列表/1440+1280+1024 提交栏视口截图
- 未覆盖：`<1024` 按需求不承诺
- 下一步：无

### QA-01 前端单元/组件测试

- 状态：**PASS**
- 测试：18 files / 129 tests（含 PR16 定向回归 12 项）
- 证据：`evidence/frontend-test.txt`
- 未覆盖：真实布局/音频（jsdom 限制，E2E 补主链路）
- 下一步：持续补 BLOCKED 场景

### QA-02 后端回归

- 状态：**PASS**
- 测试：265 passed；本次新增/修改文件 ruff 全绿；全仓 ruff 178 = 基线 178（零新增）
- 证据：`evidence/backend-pytest.txt`、`ruff-changed.txt`、`ruff-full.txt`
- 未覆盖：全仓历史 ruff 问题未修（基线 178，本次未扩大）
- 下一步：另立技术债

### QA-03 E2E/验收/回填

- 状态：**BLOCKED（部分核心证据不足）**
- 证据：真实浏览器 21/21 PASS；真实 API 23/23 PASS；PR16 F01–F09 已整改并回归；AC-01–AC-50、B、R、E2E 1–20 见矩阵
- 未覆盖：AC-35/38、R-04、UX-01 等真实组合/人工核听/签字；F06 真实换批
- 下一步：验收负责人复跑整改场景，补齐 BLOCKED 证据后重判整轮

### DOC-01B1 验收前文档同步

- 状态：**PASS**
- 实际改动：本报告、`acceptance-matrix.md`、`验收交接文档.md`、`PR16-整改说明-20261116.md`、`README.md`（验收指南）、`docs/development/attempt-system/api.md`、`implementation.md`、`docs/requirements/attempt-system/attempt-system-sync-20261116.md`、`frontend/README.md`、`backend/README.md`
- 未覆盖：需求主文件（工作区根目录 V1.2）与原型受控主件不在仓库内，未改动；P-01/P-03 结论以同步说明记录
- 下一步：受控主件归档时按附录 A 同步原型版本引用

### DOC-01B2 验收后证据归档

- 状态：**PENDING**（验收后执行）
- 输入：本次证据 + 验收人结论
- 下一步：回填最终结论、BLOCKED 重判责任人与 AC-25 关闭记录

## 2. 实际改动清单

### 2.1 后端（新增 5、修改 4）

```text
新增：app/schemas_attempt_status.py
      app/repositories/attempt_status.py
      app/services/attempt_status.py
      app/api/attempt_status.py
      tests/test_attempt_status_api.py            （12 项）
      tests/attempt_support.py                    （数据工厂 + 级联清理）
      scripts/e2e_attempt_setup.py                （独立 E2E 库/3 套试卷/第二学生）
      scripts/e2e_attempt_api.py                  （23 项真实 API 验收）
修改：app/services/attempts.py                    （私有汇总函数提取为公开，行为不变）
      app/main.py                                （注册 API-3 router）
      tests/conftest.py                          （作答数据清理夹具）
      tests/attempt_support.py                   （音频文件落盘、清理顺序）
删除：alembic/versions/0005_attempts.py           （与基线 0005_attempt_system 重复，自建遗留）
      app/core/attempt_messages.py                （重复消息模块，改用 schemas_attempts 常量）
```

### 2.2 前端（新增 24、修改 11）

```text
新增：api/attempts.ts
      attempt/{types,codec,storage,payload,errors,retention,state,submit}.ts
      pages/student/attempt/{QuestionCard,AnswerSheet,SubmitConfirmModal,DraftBanner,
                             SubmitSummaryPanel,PendingPanel,SubmitResultAlert}.tsx
      test/{setup,fixtures,smoke.test}.ts
      vitest.config.ts
      scripts/e2e_attempt.mjs
      9 个单测文件、7 个组件测试文件、2 个页面测试文件、1 个列表页测试文件
修改：api/types.ts（DTO）、api/adapters.ts（视图模型/解析）、
      pages/student/ListeningPaperPage.tsx（重写为作答/冻结/只读容器）、
      pages/student/ListeningPaperListPage.tsx（四态入口）、
      pages/student/HomePage.tsx（文案）、styles/global.css（作答布局/断点）、
      package.json / package-lock.json（测试工具链）
```

### 2.3 未提交差异

- 二次整改提交（相对 `e67d616`）：**26 files changed, 780 insertions(+), 252 deletions(-)**（代码、定向回归、E2E、文档与证据）。
- 一轮整改提交（相对 `b47e901`）：34 files changed，含 `handoff.md` → `验收交接文档.md` 重命名。
- 未推送至 `develop`（分支保护，须走 PR）；未改动 API-1 契约/迁移；未读取或输出密钥明文。

## 3. 测试命令与结果

| 命令 | 结果 | 证据 |
| --- | --- | --- |
| `python -m pytest`（`DATABASE_URL` 端口覆盖为 5433） | **265 passed**, 1 warning | `evidence/backend-pytest.txt` |
| `ruff check <本次新增/修改文件>` | All checks passed | `evidence/ruff-changed.txt` |
| `ruff check .` | 178 = 基线 178（本次零新增；`services/attempts.py` 4 项为基线既有行） | `evidence/ruff-full.txt` |
| `npm test` | **18 files / 129 tests passed**（含 PR16 定向回归 12 项） | `evidence/frontend-test.txt` |
| `npm run typecheck` | 通过 | `evidence/frontend-typecheck.txt` |
| `npm run build` | 通过（仅 chunk 体积提示） | `evidence/frontend-build.txt` |
| 真实浏览器 E2E | **21/21 PASS**（含 F01/F02/F04/F05/F06/F07/F08/F09 视口断言） | `evidence/browser-e2e.txt`、`screenshots/e2e-results.json` |
| 真实 API E2E | **23/23 PASS** | `evidence/api-e2e.txt`、`e2e-api-results.json` |

E2E 环境：独立库 `shengshengruer_e2e`、后端 `127.0.0.1:8000`、前端 `127.0.0.1:5173`、Playwright Core 1.56.1 驱动本机 Edge（未下载额外浏览器）。

## 4. 版本与环境（实测）

| 项 | 版本 |
| --- | --- |
| 仓库基线 | `main@846270b` |
| Node / npm | 24.14.0 / 11.9.0 |
| Python（backend/venv） | 3.12.10 |
| PostgreSQL | 16（`127.0.0.1:5433`） |
| React / antd / axios / Vite / TS | 19.3.1 / 6.6.8 / 1.21.0 / 8.3.5 / 6.0.3 |
| Vitest / jsdom / RTL / user-event / jest-dom | 5.1.0 / 28.1.0 / 16.3.3 / 14.6.1 / 6.9.1 |
| pytest | 9.2.0 |

## 5. 未覆盖项与下一步

| 项 | 原因 | 影响 | 后续 |
| --- | --- | --- | --- |
| AC-35、AC-38 的剩余组合 | 缺真实“后台挂起/即将关闭”“pending+换批”页面场景 | 核心项 BLOCKED | 验收负责人补测/书面裁定 |
| AC-05/08/13/15/29、R-04、E2E 多项 | 需真实关闭/换批/401/人工核听/故障注入 | 非核心 BLOCKED | 补跑或书面裁定 |
| P-03 保留期 | 未确认 | 自动重试关闭 | 确认后仅改 `KEY_RETENTION_POLICY` |
| UX-01 签字 | 用户指示暂不处理 | 流程留痕未闭环 | 按流程补签 |
| F06 真实换批 | 仅响应注入 | 版本提示已修，真实换批未验 | 补管理员真实换批 E2E |
| 全仓 ruff 178 | 基线历史问题 | 低（本次零新增） | 另立技术债 |
| `backend/.env` 端口 5432 | 与实际 5433 不符 | 本地直跑会连不上 | 不改用户配置，命令用环境变量覆盖；验收指南已注明 |

## 6. PR16 独立验收整改记录

> 依据《PR16 独立验收报告_20261116.md》《PR16 二次独立验收报告_20261117.md》；详见 [一轮整改说明](PR16-整改说明-20261116.md) 与 [二次整改说明](PR16-二次整改说明-20261117.md)。

| 问题 | 严重级 | 修复摘要 | 回归证据 |
| --- | --- | --- | --- |
| F01 损坏信封 + malformed 放开编辑 | P1 | boot 状态分发前增加损坏信封优先保护 | R「F01」；E2E-10 |
| F02 手动查询矛盾仍可编辑 | P1 | 所有来源 conflict 统一 `setFrozen(true)` | R「F02」；E2E-11 |
| F03 E09 false 丢冻结答案 | P1 | 先恢复答案/草稿并读回，成功才清信封 | R「F03」 |
| F04 重新开始旧 timer 复活 | P2 | 二次确认 + 取消 token timer | R「F04」；E2E-12 |
| F05 SPA 离开丢最后作答 | P2 | 卸载 flush | R「F05」；E2E-13 |
| F06 同题数换批缺版本提示 | P2 | 有汇总即提示版本 | R「F06」；E2E-14 |
| F07 提交栏视口不可见 | P2 | 固定底部栏 + 页面留白 + 视口断言 | E2E-09；1440/1280/1024 截图 |
| F08 冲突后一致 false 不能解除冻结 | P2 | 手动 false 分支按 answering/pending/unrecoverable 分别恢复；pending 保留信封并解除重试禁用 | R「F08A/F08B」；E2E-15/16 |
| F09 手动查询 malformed 仍可编辑 | P2 | 手动 malformed 与首次加载统一冻结（AC-48） | R「F09」；E2E-17 |

补充处理：冲突/冻结页查询入口、汇总不可用页查询入口、无信封 malformed 统一冻结（AC-48）、冲突文案去重。

两次整改后：前端 18 files / 129 tests；浏览器 E2E 21/21；API E2E 23/23；pytest 265。AC-05 已由二次独立报告补齐；仍存在核心 BLOCKED（AC-35/38、R-04、UX-01），不代签、不判整轮通过。
