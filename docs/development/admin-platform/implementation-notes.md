# 管理端阶段一：实施方案与文件清单（T00–T02）

- 编写日期：2026-11-17（Asia/Shanghai）；分支 `feature/admin-platform`，起点 `develop @ 3609186a9a98787bfe4bbc9943b7162896a2d80f`。
- 依据：主文档 `development.md` V1.0（§3 文件落点、§4.2 权限码、§5 数据模型、§6 认证、§7 审计、§15 任务卡）。
- 本轮范围：T00 基线/归档、T01 会话与权限、T02 审计基础。T03 及以后不在本轮，未创建任何 T03+ 接口或页面。

## 1 开工基线（真实执行，输出见 evidence/）

| 项 | 事实 | 证据 |
| --- | --- | --- |
| 分支 / HEAD | `develop` → 新建 `feature/admin-platform`；HEAD `3609186a9a98787bfe4bbc9943b7162896a2d80f` | `evidence/T00-git.txt` |
| 工作区 | 开工时 `git status --short` 为空 | `T00-baseline.md` 步骤 1 |
| Alembic head | `0005_attempt_system (head)`，单链 0001→0002→0003→0004→0005 | `evidence/T00-alembic.txt` |
| 开发库 | `alembic_version = 0004_expected_count_source`，落后 head 一个版本；`auth_sessions`、`admin_login_events` 均不存在；public 表 16 张。**只读确认，本轮不迁移开发库** | `evidence/T00-devdb-readonly.txt` |
| Python | 3.13.16（`backend/.venv`） | `evidence/T00-env.txt` |
| Node / npm | 24.14.0 / 11.9.0（package.json 要求 `>=22.12.0`） | `evidence/T00-env.txt` |
| 后端测试 | `pytest -o addopts= -q -p no:warnings` → 265 passed | `evidence/T00-backend-pytest.txt` |
| 前端测试 | `npm ci` 后 `npm test -- --run` → 18 files / 129 tests passed | `evidence/T00-frontend-test.txt` |
| 需求 SHA-256 | `728105bdefece77759cdf69f30723e35bf48859b75e78dbf8637e5c4dac8cc74`，与归档件一致 | `evidence/T00-docs-sha256.txt` |

开发库落后是既有事实（PR16 合入后未执行迁移），不是本轮引入；本轮所有迁移验证只在独立测试库执行。

## 2 文档状态与冲突处理

1. **本地缺失**：主文档引用的《第三轮复验意见》《参考开发文档借鉴评估》在 `D:\guochuangxiangmu\docs\` 下不存在（含两种可能文件名均已检索）。按用户指令以主文档为准，缺失内容一律不引用、不补写；缺失事实登记于 `T00-baseline.md`。
2. **配套文档口径冲突**：`docs/development/admin-platform/tasks.md` 与 `api.md` 仍是一期旧口径（11 个权限码如 `user:list`、只做 T01–T07、14–20 人日、一期不含会话与监控），与主文档（21 个 `admin:*` 权限码、T00–T09、29–45 人日）冲突。**一律以主文档为准**，不从 tasks.md/api.md 取用旧权限码或旧范围；其接口字段描述只在主文档未覆盖且不冲突时参考。
3. **外部参考稿** `D:\guochuangxiangmu\docs\admin-platform-development.md` 只作参考，不采用其范围、权限码与角色分配。

## 3 迁移计划（从真实 head 续接，不改 0001—0005）

| 顺序 | revision | down_revision | 内容 | downgrade |
| --- | --- | --- | --- | --- |
| 1（T01） | `0006_admin_auth_session` | `0005_attempt_system` | `ALTER TABLE users ADD COLUMN auth_version INTEGER NOT NULL DEFAULT 0` + `CHECK (auth_version >= 0)`；建 `auth_sessions`（UUID PK、user_id BIGINT FK `users.id` ON DELETE RESTRICT、jti_hash CHAR(64) UNIQUE、auth_version、issued_at/expires_at/last_activity_at TIMESTAMPTZ、revoked_at/revoke_reason、ip INET、user_agent VARCHAR(256)）；索引 `(user_id, revoked_at, expires_at)`、`(last_activity_at DESC, id DESC)`、`expires_at` | 删索引与 `auth_sessions`，删 `users.auth_version` 及其约束 |
| 2（T02） | `0007_admin_audit_events` | `0006_admin_auth_session` | 建 `admin_login_events`、`admin_audit_events`（共享列：event_id UUID PK、request_id UUID、event_type、actor_user_id BIGINT NULL FK SET NULL、actor_name、role_snapshot、target_type、target_id、result CHECK SUCCESS/FAILURE、reason_code、summary JSONB、ip INET、user_agent、duration_ms、occurred_at；登录表加 `username_attempted`，操作表加 `run_id UUID NULL`）；查询索引按主文档 §5.2 | 删两张表及其索引 |

约束：单 head；每个 revision 均可 `downgrade`（0007 → 0006 → 0005）；全部新列有默认值，存量数据保留；不 seed 账号、不 seed 权限表、不写通配符。

验证方式（T01、T02 各自执行一次）：在独立库 `shengshengruer_migration_test` 执行 `upgrade head` → `downgrade base` → `upgrade head`，并检查单 head 与既有表可读；开发库不做迁移。

## 4 文件清单（本轮计划新增/修改）

| 文件 | 卡 | 动作 | 说明 |
| --- | --- | --- | --- |
| `backend/app/core/admin_permissions.py` | T01 | 新增 | 21 个权限码目录、admin/student 映射、文档调试白名单占位常量 |
| `backend/app/db/models_admin.py` | T01/T02 | 新增 | `AuthSession`（T01）；`AdminLoginEvent`、`AdminAuditEvent`（T02） |
| `backend/alembic/versions/0006_admin_auth_session.py` | T01 | 新增 | 见 §3 |
| `backend/alembic/versions/0007_admin_audit_events.py` | T02 | 新增 | 见 §3 |
| `backend/app/core/security.py` | T01 | 修改 | JWT 增加 `auth_version`、`session_id`；`decode_access_token` 强制校验 |
| `backend/app/core/request_context.py` | T02 | 新增 | request_id/event_id/UTC 上下文 |
| `backend/app/services/admin/audit.py` | T02 | 新增 | 成功同事务、失败独立事务、降级文件通道、summary 白名单 |
| `backend/app/api/deps.py` | T01 | 修改 | 会话校验、`require_permission` |
| `backend/app/api/auth.py` | T01/T02 | 修改 | T01 登录建 session（不写审计）、退出撤会话；T02 接入四类登录事件 |
| `backend/app/api/admin.py` | T01 | 修改 | `/admin/overview` 改由 `require_permission("admin:dashboard:read")` 守卫 |
| `backend/app/schemas.py` | T01 | 修改 | `GetInfoData` 增加 `permissions` |
| `backend/app/db/models.py` | T01 | 修改 | `User.auth_version` |
| `backend/app/main.py` | T02 | 修改 | request_id 中间件 |
| `backend/alembic/env.py` | T01 | 修改 | 注册 `models_admin` |
| `.gitignore` | T02 | 修改 | 忽略运行期 `backend/var/` |
| `backend/tests/test_admin_permissions.py` | T01 | 新增 | 权限码契约 |
| `backend/tests/test_auth_session.py` | T01 | 新增 | 会话/认证/退出/跨实例 |
| `backend/tests/test_admin_audit.py` | T02 | 新增 | 审计事务与降级 |
| `backend/tests/test_attempt_regression.py` | T01 | 修改 | 只调整 t07 清理顺序（先删 auth_sessions），不改断言语义 |
| `frontend/**` | — | 不改 | 前端本轮零改动，`permissions` 消费延后至 T04 |

## 5 依赖固定（本轮不新增、不升级）

- 后端沿用 `backend/requirements.txt` 现有锁定：fastapi 0.143.0、uvicorn 0.54.0、pydantic 2.14.1、SQLAlchemy 2.1.4、alembic 1.20.0、psycopg[binary] 3.3.6、pydantic-settings 2.16.2、PyJWT 2.15.1、bcrypt 5.0.0、python-dotenv 1.2.4、pytest 9.2.0、pytest-asyncio 1.4.1、httpx 0.28.1。
- 前端沿用 `frontend/package.json` + `package-lock.json` 现有锁定：React 19.3.1、antd 6.6.8、react-router-dom 7.18.5、axios 1.21.0、TypeScript 6.0.3、Vite 8.3.5、vitest 5.1.0。
- `psutil==7.2.2` 与 `swagger-ui-dist==5.35.0` 属 T08/T06，本轮**不安装、不写入依赖文件**。

## 6 外部探针入口计划（本轮只登记，不实现）

- 计划命令：`python -m app.probes --base-url https://部署站点/listening --timeout 3`，只查 `/health/live`、`/health/ready`，输出时间与状态，失败退出码非 0，不带管理令牌。
- 归属：主文档 §12.1 与 §15 的 T08/T09；本轮不创建 `app/probes.py`、不创建健康探针路由。
- 契约登记目的：避免 T08/T09 实现时另起命令格式。

## 7 本轮验证命令

```text
cd backend
$env:TEMP='D:\pytemp'; $env:TMP='D:\pytemp'
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:warnings
cd ..\frontend
npm test -- --run
npm run typecheck
```

迁移往返在独立库 `shengshengruer_migration_test` 另行执行并记录。

## 8 T03 口径推定记录（按文档 §4.1/§4.3/§6.2–§6.3 推定，验收时复核）

| 项 | 推定口径 | 依据 |
| --- | --- | --- |
| `PATCH /admin/users/{id}` 同昵称 | 200 返回用户对象，仍写 `PROFILE_UPDATED`，`summary.changed_fields=[]`；**不返回 400** | §4.3「必须且只接收 nickname；返回更新后用户」与「昵称相同可 changed=false，但不能跳过必要审计」；固定 DTO 无 `changed` 字段，故 changed 只体现于审计摘要 |
| 新建用户默认角色 | `student` | §4.3 创建接口「role（默认student）」 |
| 分页允许值 | `page_size` 仅 10/20/50/100，默认 20；`page>=1` | §4.1 |
| 写操作 404 的失败审计 | 记 `FAILURE`（`reason_code=user_not_found`/`session_not_found`）；读接口不记 | 2026-11-17 用户确认 |
| 最后管理员保护 | 锁内 `count`；因「停用本人 400」+ 权限链，API 层实际不可达，作为防御性分支在服务层用例覆盖 | §6.2、AC-03 |
| 活动节流排除范围 | `/admin/monitor/*`、`/admin/dashboard`、`/admin/logs`、`/admin/openapi.json`、`/health/*`；`GET /admin/users` 需 `X-Admin-Activity: explicit` 才刷新 | §6.3 |
| 撤会话计数 | 只统计「未撤销且未过期」的会话 | §5.4、§6.2 |
| T03 迁移 | 零迁移（`users.auth_version`、`auth_sessions` 已在 0006）；若实测需加索引/字段先停下确认 | §5.1、§15 T03 |

## 9 T04 口径推定记录（验收时复核）

| 项 | 推定口径 | 依据 |
| --- | --- | --- |
| CSV 列名 | 中文列名，逐字按 §11.1 | 用户 2026-11-17 确认 |
| CSV 的「操作者名称ID」「目标类型ID」 | 拆为「操作者名称/操作者ID」「目标类型/目标ID」四列 | §11.1 斜杠分隔，用户确认拆列 |
| CSV 枚举值 | 角色/状态/结果/原因/事件类型/目标类型输出中文标签，未知值原样输出 | §11.4 生成标签用于展示 |
| 操作日志「摘要」列 | 过滤后的 summary 以紧凑 JSON（`sort_keys`）输出 | §7.2 summary 白名单 |
| 导出 `EXPORT_FAILED.stage` | `read` / `limit_rows` / `limit_bytes` / `timeout` / `generate` / `audit` | §11.1、DD-03 |
| 15 秒 deadline | 每批读取前检查；超时 500 且不截断 | §11.1「读快照和生成合计 ≤15 秒」 |
| 日志读取 summary | 读取侧按事件类型白名单再过滤一次 | 用户 2026-11-17 约束 |
| 枚举事件类型 | 生成物按字典序输出 `EVENT_TYPES`，标签按稳定键排序 | §11.4 稳定键排序 |
| 题库 `exam_level` | 只登记现有真实值 `CET4`；其它值按「未知（原值）」 | §11.4 不新造值 |
| 前端旧用例 | 129 例全绿，**0 处**需要按 §11.2 改写 | 实测 |

## 10 T04 生成与检查命令

```text
cd backend
python scripts/generate_admin_constants.py          # 写入 frontend/src/generated/adminConstants.ts
python scripts/generate_admin_constants.py --check  # 不一致返回非零（CI/提交门禁）
python -m pytest tests/test_admin_constants.py -q    # 生成物与后端枚举一致
```

## 11 T05 口径与推定记录

| 项 | 口径 | 依据 |
| --- | --- | --- |
| `paper_count` | `SELECT count(*) FROM exam_papers`；不限定当前批次 | 需求 §10.1 原文「exam_papers 按主键计数，同卷多个批次不重复计卷」；每卷一行，故不 JOIN 批次 |
| 待确认 / 失败 | 仅统计唯一当前 `is_current` 且 `status='active'` 批次内的卷；检查按 `(checked_at DESC, id DESC)`、可见性按 `(updated_at DESC, id DESC)` 取最新 | 需求 §10.2 |
| 学生计数 | student 角色且无 admin 角色，按用户去重，按 status 分列 | 需求 §10.1、DD-05 |
| `successful_attempts_7d` | `attempts.submitted_at ∈ [北京时间今天00:00−6天, min(明天00:00, as_of))`；只数 attempts 行，不读 answers/rejections | 需求 §10.1 |
| 缓存关闭状态 | `enabled=false, status=not_configured` | 主文档 §9.5「可选关闭配置需显示 not_configured」 |
| 缓存 TTL | 固定 15 秒，单调时钟判断；`as_of` 为快照生成时刻 | §9.5 |
| `/admin` 首页与菜单 | `RequirePermission(admin:dashboard:read)` | §11.3 页面读取权限 |
| 菜单测试契约 | 「首页」原为无条件显示，现随 `admin:dashboard:read` 显隐；`AdminLayout.test.tsx` 对应用例同步更新（T05 起生效） | §4.2/§11.3 |

## 12 T05 首页缓存与查询实现要点

- 统计连接：`SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY` 作为事务第一条语句，随后 `SET LOCAL statement_timeout='5000ms'`；单条 CTE SQL 计算全部卡片。
- 缓存：`app/services/admin/dashboard_cache.py`，域 `admin_dashboard_summary`/键 `overview`，每进程 1 项，实例锁单飞，hits/misses 从启动累加，`instance_id` 每进程 UUID。
- 失败（SQL/超时/异常）500，不写缓存、不返回部分计数。

## 13 T06 私有文档与受限调试记录

| 项 | 口径 | 依据 |
| --- | --- | --- |
| 公开入口 | `/docs`、`/docs/oauth2-redirect`、`/redoc`、`/openapi.json`、`/api/v1/openapi.json` 全局 404（含开发环境） | §8.1、用户确认 |
| 受保护 schema | `GET /api/v1/admin/openapi.json`，`admin:docs:read`，原始 JSON、`no-store`、追加 `x-admin-debug-allowlist` | §8.1 |
| 白名单 | 当前 9 条现存只读 GET（用户/本人/会话/日志/首页）；**监控读取延后到 T08**：对应路由尚未实现，提前登记不存在的路径会让 schema 与文档失真；T08 增路由时在同一常量补登 | §8.2 |
| 歧义路径 | 只解码一次；含 `%`（二次编码）、`%2F`/`%5C`、双斜杠、尾斜杠、反斜杠一律 400；模板参数匹配单段 | §8.2、用户约束 |
| 调试审计 | `DOC_GET_DEBUG` 独立短事务（只读请求无业务事务），审计失败把响应替换为 500；不记录 query/Authorization/响应体 | §8.2、用户确认（推定：§7.2「成功同事务」针对有业务变更的事件） |
| 依赖 | 新增 `swagger-ui-dist@5.35.0`（精确锁版本，`package.json` + `package-lock.json`），本地打包无 CDN | §1.2 |
| 调试标记 | `X-Admin-Docs-Debug: 1`；仅前置校验，命中后仍走原路由鉴权；无标记请求零改动 | §8.2 |

## 14 T06 前端文档页要点

- `/admin/tools/api`（`admin:docs:read`）：schema 经受保护 `rawClient` 取得后以 `spec` 对象传入 Swagger UI，无公开 URL、无 iframe JWT、无外部 validator。
- `persistAuthorization=false`、`validatorUrl=null`、`supportedSubmitMethods` 默认 `[]`；同时具备 `admin:docs:debug` 才显示「启用调试」，启用后仅 `get`。
- requestInterceptor：按 method + 模板 + 同源校验，注入 Bearer 与调试标记；非白名单本地拒绝。
- 资源由 Vite 打包（`import 'swagger-ui-dist/swagger-ui.css'` + 动态 import bundle），不硬编码根路径/localhost；卸载时清空容器与引用。

## 15 T07 留存调度口径与实现要点

| 项 | 口径 | 依据 |
| --- | --- | --- |
| 迁移 | 仅新增 0008 三张表，`down_revision=0007`，downgrade 可回 0007 | §5.3/§5.5 |
| 种子 | 唯一任务定义一行；`next_scheduled_at` 迁移时置 NULL，进程启动/`ensure_next_scheduled` 计算并持久化（推定项，用户确认） | §5.3 |
| 互斥 | 调度执行用专用连接 session 级 advisory lock（键 `918273645`，与管理员保护锁不同）；手动触发用 `pg_try_advisory_xact_lock` 与 QUEUED 插入同事务，HTTP 线程不持有 session 锁 | §10.2、用户约束 |
| 锁顺序 | advisory 任务锁 → `admin_job_definitions` 行锁 → `admin_job_runs` 行 | §6.2/§10.2 |
| 状态机 | QUEUED→RUNNING→SUCCEEDED/PARTIAL/FAILED（attempt=1 时 60 秒后同 run 重试，最多 2 次）/INTERRUPTED；INTERRUPTED 有剩余额度则同 run 重新排队 | §10.3 |
| 补跑 | 只对最近一个 03:10 建 run；更早的按天差累计 `missed_slots`；已有同 slot/活动 run 不新建；暂停不累计，恢复把下次计划设为严格未来 | §10.3 |
| 删除 | 白名单 5 张表；每批 ≤1000；批间提交；单 attempt ≤60 秒/≤50000 行；严格 `<`，相等保留；提交未知 → `counts_complete=false` | §5.4/§10.2 |
| 控制 API | 暂停/恢复共用 `POST .../enabled`；重复值 200 `changed=false`；`job_running`/`scheduler_unavailable`/非白名单统一 **400**（文档口径，不用 409）；读取未知任务 404 | §10.1 |
| 事件 | `JOB_PAUSED/RESUMED/TRIGGERED/FINISHED`（T02 白名单内）；配置/run 同事务，失败拒绝独立事务 | §7.1 |
| 前端 | `/admin/monitor/jobs`（`admin:job:read`）；轮询 15 秒、`document.hidden` 停止；`/admin/monitor` 已在 T03 活动排除清单 | §10.1/§6.3 |

实现注意：advisory 锁连接的 `SELECT pg_try_advisory_lock` 会开启事务，取得锁后必须 `commit()` 结束该事务，否则后续 `Session.commit()` 只是内部子事务、连接关闭时写入整体回滚（已在 T07b 修复并由测试锁定）。
