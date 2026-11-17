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
