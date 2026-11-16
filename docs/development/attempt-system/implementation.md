# 作答系统实施记录（任务二 / 模块三作答）

> 日期：2026-11-16  
> 需求：V1.2；开发：V1.1；原型：图集 V1.1（评审结论“通过”，签字按用户指示暂不处理）  
> 基线：`main@846270b`（已含 API-1 与迁移 `0005_attempt_system`；工作区含本任务未提交改动）

## 1. 前置核查结论（DOC-01A）

| 项 | 结论 |
| --- | --- |
| 代码基线 | `D:\ssre_V1\ShengShengRuEr`，`main@846270b` |
| API-1 / attempts 表 | **基线已存在**：`api/attempts.py`、`services/attempts.py`、`schemas_attempts.py`、`db/models_attempt.py`、`repositories/attempt_keys.py`、`repositories/attempt_content.py`、`alembic/versions/0005_attempt_system.py` |
| 迁移处置 | 删除工区遗留重复迁移 `0005_attempts.py`（上一轮按旧基线自建）；**最终零迁移变更** |
| 消息模块 | 删除重复的 `app/core/attempt_messages.py`；统一使用 `schemas_attempts.py` 的 E03–E09 常量 |
| 数据库 | PostgreSQL 16，`127.0.0.1:5433`；`backend/.env` 写 5432，测试/启动用环境变量覆盖（不改 `.env`、不输出密码） |
| Python | `backend/venv` 3.12.10 |
| Node / npm | 24.14.0 / 11.9.0 |
| 前端基线 | typecheck/build 通过；无测试框架 |
| P-03 保留期 | **未确认**；`KEY_RETENTION_POLICY = { kind: 'unknown' }`，自动重试关闭 |
| 原型门禁 | 图集说明标注“已评审通过、四方签字待回填”；按用户指示本轮不处理 |

## 2. 后端实施（BE-01–BE-04）

| 任务 | 交付 | 状态 |
| --- | --- | --- |
| BE-01 | `schemas_attempt_status.py`（不变量校验、`ApiResponse` 复用）；`services/attempts.py` 公开 `attempt_summary_from_attempt` | PASS |
| BE-02 | `repositories/attempt_status.py` 单条窗口 SQL；`services/attempt_status.py` 准入 404 + 汇总复用；只读 | PASS |
| BE-03 | `api/attempt_status.py`（PathId、require_student、no-store）；`main.py` 注册 | PASS |
| BE-04 | `tests/test_attempt_status_api.py`（12 项：B-01–B-16 + 单语句策略 + 并发）、`tests/attempt_support.py`、`tests/conftest.py` 清理夹具 | PASS |

### 2.1 关键实现点

- **API-3**：认证→角色（管理员 403）→准入（404）→查询；成功/404 均 `no-store`；不写库、不 join answers。
- **单快照**：`select(Attempt, func.count().over()) ... order_by(submitted_at desc, id desc).limit(1)`；无行返回 0/null；**没有两次查询回退**。
- **语义不变量**：Pydantic `model_validator` 拒绝 `false+latest`、`false+count>0`、`true+count=0`、嵌套 `exam_paper_id` 不一致。
- **错误顺序**：路由依赖 `require_student` 先于 body 校验（API-E2E 验证未登录 401 优先）。
- **前端错误契约**：以基线真实 `status+msg` 为准（E03/E14=404「资源不存在」；E04/E05/E07/E08/E09=400 各自文案）。

### 2.2 修改/新增路径

```text
backend/app/schemas_attempt_status.py          新增
backend/app/repositories/attempt_status.py     新增
backend/app/services/attempt_status.py         新增
backend/app/api/attempt_status.py              新增
backend/app/services/attempts.py               修改（私有汇总函数提取为公开，行为不变）
backend/app/main.py                            修改（注册 API-3 router）
backend/tests/attempt_support.py               新增（数据工厂/音频落盘/级联清理）
backend/tests/test_attempt_status_api.py       新增（12 项）
backend/tests/conftest.py                      修改（作答数据清理夹具）
backend/scripts/e2e_attempt_setup.py           新增（独立 E2E 库、3 套试卷、第二学生）
backend/scripts/e2e_attempt_api.py             新增（23 项真实 API 验收）
删除：backend/alembic/versions/0005_attempts.py、backend/app/core/attempt_messages.py
```

## 3. 前端实施（FE-00–FE-08）

| 任务 | 交付 | 状态 |
| --- | --- | --- |
| FE-00 | Vitest 5.1.0 + jsdom 28.1.0 + RTL 16.3.3 + user-event + jest-dom + playwright-core；`vitest.config.ts`、`src/test/setup.ts`、smoke、`npm test` | PASS |
| FE-01 | `api/types.ts` 仅 DTO；`api/adapters.ts` 视图模型 + API-3 分层解析/语义校验；`api/attempts.ts` | PASS |
| FE-02 | `attempt/{types,codec,storage}.ts`：三对象分离、TTL/10 份、写后读回、损坏保护、写入前终态检查 | PASS |
| FE-03 | `attempt/{payload,errors,retention,state,submit}.ts`（含 N04 重建） | PASS |
| FE-04 | `pages/student/attempt/*.tsx` 7 个组件 + CSS 两档断点 | PASS |
| FE-05 | `ListeningPaperPage.tsx` 重写：门禁/五类页态/冲突冻结/404 不展示汇总/中性导航 | PASS |
| FE-06 | 提交编排（同键/内存信封/E08/E09/E04/未知/401）、双击防护、终态顺序、storage 事件 | PASS（核心） |
| FE-07 | 300ms 防抖 + 隐藏/pagehide flush + 写入前终态检查 + 401 交 client | PASS（核心） |
| FE-08 | 列表四态、首页文案、1280/1024 布局、README | PASS |

### 3.1 前端结构

```text
frontend/vitest.config.ts
frontend/scripts/e2e_attempt.mjs
frontend/src/test/{setup.ts,fixtures.ts,smoke.test.ts}
frontend/src/api/{attempts.ts,types.ts,adapters.ts}
frontend/src/attempt/{types,codec,storage,payload,errors,retention,state,submit}.ts
frontend/src/pages/student/attempt/*.tsx
frontend/src/pages/student/ListeningPaperPage.tsx
frontend/src/pages/student/ListeningPaperListPage.tsx
frontend/src/pages/student/HomePage.tsx
frontend/src/styles/global.css
frontend/package.json / package-lock.json
```

### 3.2 N01–N08 落地

| 编号 | 落地 |
| --- | --- |
| N01 | 终态先写 `ssre.attemptSubmitted.v2.*` → `terminalRef`/取消 timer → 删草稿/信封；页面监听 `storage`；防抖保存与 pagehide flush 写入前 `hasSubmittedMarker` 检查；E2E 多标签 + 单测覆盖 |
| N02 | 适配器与后端 Schema 双向校验 `submitted === (count>0)`、`false→count=0/latest=null`、`true→count>=1`、嵌套试卷 ID；冲突只冻结、不清理、不写新事实 |
| N03 | `submittedAt: string|null`；E08/坏汇总/`latest=null` 写 null；页面无真实时间不渲染时间行 |
| N04 | `rebuildDraftFromEnvelope` + 页面 `restore-answer` 分支：集合一致才重建、写入读回成功才清信封；不兼容/写入失败保留冻结；E04 例外 |
| N05 | API-3 单条窗口 SQL；单语句断言 + 并发一致性测试；无两次查询回退 |
| N06 | 验收矩阵区分核心项；AC-25 文档在 QA-03 关闭前完成；BLOCKED/PARTIAL 重判责任人写入交接 |
| N07 | API-1 404（明确失败→重建答案→清旧信封）与 API-3 404（保留信封/冻结/不展示汇总）分流 |
| N08 | `pending-unrecoverable` 页面状态；仅查询/强警告清除；不构造合法信封、不重发、不自动删 |

## 4. 测试与证据

| 命令 | 结果 | 证据 |
| --- | --- | --- |
| `python -m pytest` | **265 passed**, 1 warning | `docs/acceptance/attempt-system/evidence/backend-pytest.txt` |
| `ruff check`（本次新增/修改文件） | All checks passed | `evidence/ruff-changed.txt` |
| `ruff check .`（全仓） | 178 = 基线 178（零新增；`services/attempts.py` 4 项为基线既有行） | `evidence/ruff-full.txt` |
| `npm test` | **17 files / 117 tests passed** | `evidence/frontend-test.txt` |
| `npm run typecheck` | 通过 | `evidence/frontend-typecheck.txt` |
| `npm run build` | 通过（仅 chunk 体积提示） | `evidence/frontend-build.txt` |
| 真实浏览器 E2E | **11/11 PASS** | `screenshots/`、`e2e-results.json` |
| 真实 API E2E | **23/23 PASS** | `e2e-api-results.json` |

E2E 环境：独立库 `shengshengruer_e2e`、后端 `127.0.0.1:8000`、前端 `127.0.0.1:5173`、Playwright Core 1.56.1 驱动本机 Edge（未下载额外浏览器）。

## 5. 未覆盖与风险

1. **核心项 PARTIAL**：AC-35（pending+内容变化三组合页面级）、AC-38（后台挂起/即将关闭两态）缺真实组合证据。
2. **P-03 未确认**：自动重试关闭；`permanent/days` 分支仅单测。
3. **其它 PARTIAL**：401 提交中、E04 页面换批、真实 500 注入、空卷提交、已提交换批版本提示、人工音频核听（见矩阵）。
4. **antd 6 弃用告警**：`Alert.message`、`Space.direction`、`Modal.maskClosable` 控制台 warning；项目既有用法一致，不影响功能。
5. **`backend/.env` 端口**：写 5432，实际 5433；未改用户配置，测试/启动用环境变量覆盖。
6. **未提交**：全部改动仍在工作区，未 commit/push/merge。

## 6. 下一步

- 验收负责人裁定 AC-35/AC-38 等 PARTIAL：接受或补测；
- P-03 保留期确认后仅改 `KEY_RETENTION_POLICY`；
- UX-01 按项目流程补签；
- 全仓 ruff 历史问题另立技术债。
