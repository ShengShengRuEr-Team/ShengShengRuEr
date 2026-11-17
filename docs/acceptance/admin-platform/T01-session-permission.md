# T01 会话与权限 · 证据记录

| 字段 | 值 |
| --- | --- |
| ac_id | AC-28（完整后端）、AC-35（旧 JWT 全失效 + 迁移往返部分）、AC-07/08（后端地基） |
| requirement_ids | ADM-PERM01、ADM-MON01（会话/版本部分） |
| executor | 开发实施人（lead agent） |
| executed_at | 2026-11-17 11:50—12:20（Asia/Shanghai） |
| commit_sha | 基线 `3609186a9a98787bfe4bbc9943b7162896a2d80f`；本轮改动**未提交** |
| workspace_state | 10 个已跟踪文件修改 + 5 个新文件 + 文档目录未跟踪；前端零改动 |
| environment | Windows；Python 3.13.16（`backend/.venv`）；PostgreSQL 本地；测试库 `shengshengruer_test`；迁移验证库 `shengshengruer_migration_test`（用后即删） |
| migration_heads | T01 后单 head：`0006_admin_auth_session` |
| dependency_versions | 无新增、无升级（见 `implementation-notes.md` §5） |
| result | **PASS** |

## 1 改动文件全清单

### 1.1 新增文件（5 个代码/测试 + 证据文档）

| 文件 | 说明 |
| --- | --- |
| `backend/app/core/admin_permissions.py` | 21 个权限码目录、admin/student 映射、文档调试白名单占位（空） |
| `backend/app/db/models_admin.py` | `AuthSession` 模型（T02 再增两类审计模型） |
| `backend/alembic/versions/0006_admin_auth_session.py` | `users.auth_version` + `auth_sessions` |
| `backend/tests/test_admin_permissions.py` | 权限码契约 + getInfo 兼容 + 移除单码 403（6 例） |
| `backend/tests/test_auth_session.py` | 会话/认证/退出/跨实例/DB 异常（12 例） |

### 1.2 修改文件（10 个，含共享文件）

| 文件 | 类型 | 改动 |
| --- | --- | --- |
| `backend/app/core/security.py` | **共享认证** | JWT 增加 `auth_version`/`session_id`，解码强制校验；bool 版本拒绝 |
| `backend/app/api/deps.py` | **共享认证** | `get_current_user` 改独立短 Session，核对旧撤销表、用户 FOR SHARE、会话指纹/撤销/过期/版本；新增 `require_permission(code)` |
| `backend/app/api/auth.py` | **共享认证** | 登录事务内锁行重验并建会话（不写审计）；退出撤会话 + 幂等写旧撤销表；getInfo 增 `permissions` |
| `backend/app/api/admin.py` | 共享路由 | `/admin/overview` 改由 `require_permission("admin:dashboard:read")` 守卫 |
| `backend/app/schemas.py` | 共享契约 | `GetInfoData` 增 `permissions: list[str] = []`，旧字段不变 |
| `backend/app/db/models.py` | 共享模型 | `User.auth_version` + CHECK |
| `backend/app/core/errors.py` | 共享错误 | 新增 `permission_denied()`（403 固定文案） |
| `backend/alembic/env.py` | 迁移注册 | 导入 `models_admin` |
| `backend/tests/test_attempt_regression.py` | 既有测试 | **仅**清理顺序适配（先删 auth_sessions）+ 1 行键集断言（见 §6） |
| `backend/tests/test_attempt_models.py` | 既有测试 | 迁移版本断言由硬编码 0005 改为“等于当前唯一 head”（见 §6） |

### 1.3 `git diff --stat`

```text
 backend/alembic/env.py                   |   1 +
 backend/app/api/admin.py                 |   8 ++-
 backend/app/api/auth.py                  | 114 +++++++++++++++++++++++++++----
 backend/app/api/deps.py                  |  95 ++++++++++++++++++++------
 backend/app/core/errors.py               |   4 ++
 backend/app/core/security.py             |  45 +++++++++++-
 backend/app/db/models.py                 |   6 ++
 backend/app/schemas.py                   |   2 +
 backend/tests/test_attempt_models.py     |  20 +++++-
 backend/tests/test_attempt_regression.py |  14 +++-
 10 files changed, 269 insertions(+), 40 deletions(-)
```

## 2 迁移 0006 往返（独立库，未碰开发库）

证据原文：`evidence/T01-migration-roundtrip.txt`（真实命令输出）。

```text
$ alembic heads
0006_admin_auth_session (head)
$ alembic upgrade head        # 空库，从 base 依次执行 0001→0006
... Running upgrade 0005_attempt_system -> 0006_admin_auth_session ...
$ alembic current
0006_admin_auth_session (head)
$ （报告）alembic_version=0006_admin_auth_session
         auth_sessions=auth_sessions
         users_auth_version=('integer', 'NO', '0')
         public_table_count=20
         auth_sessions_indexes=['ix_auth_sessions_expires_at',
           'ix_auth_sessions_last_activity_id',
           'ix_auth_sessions_user_revoked_expires',
           'pk_auth_sessions', 'uq_auth_sessions_jti_hash']
$ alembic downgrade base      # 逐级回退到空库
... Running downgrade 0006_admin_auth_session -> 0005_attempt_system ...
$ （报告）alembic_version=None / auth_sessions=None / users_auth_version=None
         public_table_count=1（仅剩 alembic_version）
         rows_users=UndefinedTable（表已删除，符合预期）
$ alembic upgrade head        # 再次升级
$ alembic current
0006_admin_auth_session (head)
$ （报告）auth_sessions=auth_sessions，索引 5 项，public_table_count=20
$ drop database shengshengruer_migration_test
```

结论：0001—0005 未修改；0006 可正向、可回退、可再正向；单 head；旧表在往返后结构完整（空库验证，行数 0 属正常）。

## 3 认证关键用例实际输出

证据原文：`evidence/T01-auth-cases.txt`（真实 TestClient + 真实 PostgreSQL）。

```text
issued session_id=ad4fd5e0-68c2-4eee-9266-eaa5a12f2d1f auth_version=0
1. valid new token -> /api/v1/getInfo: 200
2. legacy token without auth_version/session_id -> 401
3. auth_version bumped -> 401
4. account disabled -> 401
5. second TestClient before revocation -> 200
6. second TestClient after revocation -> 401
7. first TestClient after revocation -> 401
8. no token -> 401
9. fresh login -> 200
10. logout -> 200
11. old token after logout -> 401
12. session row after kick: ('5e6bb590…a73a05', 2026-11-17T03:47:59Z, 'kicked')
13. auth_sessions rows in test db: 119
```

数据库异常单独取证：`evidence/T01-db-error-500.txt`

```text
login before breaking db -> 200
getInfo with database error -> 500
body -> {'code': 500, 'msg': '服务器内部错误', 'data': None}
```

对应 pytest 用例（`tests/test_auth_session.py`）：

| 用例 | 断言 |
| --- | --- |
| `test_login_creates_session_and_stores_only_jti_hash` | 会话行存在、只存 jti 的 SHA-256、原始 jti 不落库、旧撤销表未写 |
| `test_legacy_token_without_new_claims_returns_401` | 缺 `auth_version`/`session_id` 均 401 |
| `test_bool_auth_version_is_rejected` | `auth_version=true` 401 |
| `test_disabled_user_token_returns_401` | 停用后 401，且重新登录 401 |
| `test_auth_version_bump_invalidates_token` | 版本递增后 401 |
| `test_revoked_session_returns_401` | 会话撤销后 401 |
| `test_expired_session_returns_401` | 会话过期后 401 |
| `test_missing_session_row_returns_401` | 会话行删除后 401 |
| `test_logout_revokes_session_and_token` | 登出写 `revoked_at/reason=logout` + 旧撤销表，旧 token 401 |
| `test_cross_instance_revocation` | 两独立 TestClient：撤销前均 200，撤销后均 401 |
| `test_database_error_is_500_not_401` | 500 外壳，body `{code:500,msg:"服务器内部错误",data:null}` |

权限侧（`tests/test_admin_permissions.py`）：21 码逐字一致、admin 21 条、student `[]`、旧字段 `{user,roles,is_admin}` 仍在、无 token 401 → 学生 403 → 管理员 200、移除 `admin:dashboard:read` 后管理员 403 且 getInfo 只剩 20 条。

## 4 全量 pytest

```text
$ python -m pytest -o addopts= -q -p no:warnings
283 passed in 62.73s
```

（T00 基线 265 + 本轮新增 18；无 skip/xfail 掩盖。）原文：`evidence/T01-backend-pytest.txt`。

## 5 前端零改动

```text
$ git status --short frontend
（空）
$ npm test -- --run
Test Files  18 passed (18)
     Tests  129 passed (129)
```

原文：`evidence/T01-frontend-test.txt`。前端未改任何文件；`getInfo.permissions` 的消费与权限组件属 T04。

## 6 既有测试的两处修改（均非弱化）

### 6.1 `tests/test_attempt_regression.py`（经你批准的契约更新 + 清理顺序）

| 位置 | 前 | 后 |
| --- | --- | --- |
| `t07_users` 清理（约 302 行） | 仅 `DELETE token_revocations` | **新增** `DELETE FROM auth_sessions WHERE user_id=:user`，其余删除与断言不动 |
| `test_module1_auth_regression`（原 532 行） | `set(data) == {"user","roles","is_admin"}` | `set(data) == {"user","roles","is_admin","permissions"}` + 新增 `permissions == []` |

原因：主文档 §4.2 强制 getInfo 新增 `permissions`，属契约升级；断言从 3 键扩展为 4 键并**新增**一条 student 空集正向断言，未删除任何原有校验。全仓已用 `grep is_admin backend/tests` 复核：`test_acceptance.py` 只按键取值（不受影响），仅此一处是键集全等断言。

### 6.2 `tests/test_attempt_models.py`（计划外，必须报告）

`test_a2_alembic_version_is_0005` 硬编码 `version == "0005_attempt_system"`，新增 0006 后必然失败。改为 `test_a2_alembic_version_is_single_head`：从 `alembic.ini` 读取当前唯一 head 并与数据库 `alembic_version` 比较，语义由“等于 0005”变为“等于当前唯一 head”，仍会抓住多 head、未迁移、错版本；避免 T02/T07 每次加迁移都要改断言。

## 7 存量 token 全失效（部署说明）

JWT 新增两个**必需**声明 `auth_version`、`session_id`；解码时缺失即 `TokenValidationError` → 401。因此：

- 部署 T01 后，所有部署前签发的 token 立即失效，全部在线用户需重新登录；
- 这是本期设计预期（配合持久会话与版本撤销），**不是故障**，也不需要清库或轮换密钥；
- 旧 `token_revocations` 表继续被检查，历史撤销记录仍生效；
- 学生端只回归共享认证兼容，无新增页面/业务。

## 8 未覆盖项

- 会话列表/强退接口（AC-07/08 的 HTTP 部分）：T03。
- 登录四类审计事件（LOGIN_SUCCEEDED/UNKNOWN_ACCOUNT/BAD_PASSWORD/DISABLED）：按本轮修正留 T02。
- AC-35 的发布/回退演练与双实例跨进程验证：T09。
- AC-28 的前端权限消费与页面守卫：T04。
- 活动节流（30 秒条件更新）：T03。

## 9 结论

**PASS**。T01 交付：0006 迁移（可往返）、持久会话、JWT 版本/会话校验、登录/退出改造、21 码权限目录与 getInfo 契约；后端 283 通过、前端 129 通过且零改动。
