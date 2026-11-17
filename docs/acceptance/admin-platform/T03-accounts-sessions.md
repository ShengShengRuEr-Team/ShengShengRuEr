# T03 账户 / 本人 / 在线 · 证据记录

| 字段 | 值 |
| --- | --- |
| ac_id | AC-01、AC-02、AC-03、AC-04、AC-05、AC-06、AC-07、AC-08（AC-07 的 5 分钟窗口与节流、AC-08 单会话强退） |
| requirement_ids | ADM-USR01/02/03、ADM-SELF01/02、ADM-MON01 |
| executor | 开发实施人（lead agent） |
| executed_at | 2026-11-17 12:25—12:50（Asia/Shanghai） |
| commit_sha | 起点 `5e8a386`；T03 改动随本卡本地提交（不 push） |
| workspace_state | 3 个已跟踪文件修改 + 15 个新文件（路由/模型/服务/仓储/测试）+ 证据 |
| environment | Windows；Python 3.13.16；PostgreSQL 本地；测试库 `shengshengruer_test` |
| migration_heads | `0007_admin_audit_events (head)`，T03 零迁移 |
| dependency_versions | 无新增、无升级 |
| result | **PASS** |

## 1 改动文件

### 1.1 修改（3）

| 文件 | 改动 |
| --- | --- |
| `app/main.py` | 注册 `admin_platform` 的 users/me/sessions 三个 router |
| `app/api/deps.py` | 活动节流：独立短事务 + 30 秒条件更新 + 排除清单；失败只 warning 且不输出异常正文 |
| `app/core/admin_permissions.py` | 新增 `role_snapshot()` 共享函数（auth 与审计共用） |

### 1.2 新增（15）

| 文件 | 说明 |
| --- | --- |
| `app/api/admin_platform/{__init__,common,users,me,sessions}.py` | 路由层；路径参数按字符串接收、认证后解析 |
| `app/schemas_admin/{__init__,common,users,sessions}.py` | DTO、分页、密码/用户名/reason 校验，输入 `extra='forbid'` |
| `app/services/admin/{guards,accounts,sessions,events}.py` | 保护锁/锁顺序、账户事务、在线查询与强退、审计事件辅助 |
| `app/repositories/admin/{__init__,users,sessions}.py` | 角色投影、固定筛选、集合计数 |
| `backend/tests/admin_support.py` | T03 测试支持（临时用户、会话、审计查询） |
| `backend/tests/test_admin_{users_api,me_api,sessions_api,activity}.py` | 27 例 |

`git diff --stat`（已跟踪文件）：`deps.py +73`、`admin_permissions.py +11`、`main.py +4`，共 3 files / 85 insertions。

## 2 接口与顺序

证据原文：`evidence/T03-api-cases.txt`。

```text
== 顺序：401 → 403 → 422 ==
no token  GET /admin/users/abc -> 401
student   GET /admin/users/abc -> 403
admin     GET /admin/users/abc -> 422

== 创建 / 停用 / 旧 token 失效 ==
create -> 200 role=student
disable -> 200 changed=True revoked_session_count=1
old token after disable -> 401
relogin disabled -> 401

== 在线会话 DTO 与强退 ==
item keys=[expires_at, ip, is_current, issued_at, last_activity_at, role,
           session_id, user_agent_summary, user_id, username]
contains jti/token in body: False
revoke -> 200 {'session_id': …, 'changed': True}
revoked token -> 401
other session still -> 200
revoke current -> 400

== 活动节流 ==
after monitor  unchanged=True
after poll     unchanged=True
after explicit refreshed=True
```

路径参数统一按字符串接收、认证依赖之后解析，因此未登录/学生携带畸形 id 不会先得到 422。

## 3 测试

```text
$ pytest tests/test_admin_users_api.py tests/test_admin_me_api.py \
         tests/test_admin_sessions_api.py tests/test_admin_activity.py -q
27 passed in 28.28s

$ pytest -o addopts= -q -p no:warnings
330 passed in 92.90s
```

原文：`evidence/T03-targeted-pytest.txt`、`evidence/T03-backend-pytest.txt`。无 skip/xfail。

### 3.1 新增用例清单（27）

| 文件 | 用例 |
| --- | --- |
| `test_admin_users_api.py`（10） | 列表形状与 401/403、筛选与参数校验、详情/404/422、创建与重复/并发重名仅一行、PATCH 昵称与同值审计、停用撤销会话与版本、停用本人 400、最后管理员服务层保护、重置密码全流程 |
| `test_admin_me_api.py`（5） | GET /me 与 403、PATCH 昵称（含同值审计与 extra 422）、改密撤销全部会话并与审计、学生 403、密码等于用户名 400 |
| `test_admin_sessions_api.py`（7） | DTO 与无 jti/token、认证顺序、筛选与分页、5 分钟严格边界、强退他人会话/幂等、强退当前 400、未知会话 404、UUID/reason/extra 422 |
| `test_admin_activity.py`（5） | 30 秒节流且 expires_at 不变、监控读取不保活、列表需显式标记、活动写失败仅 warning 不阻塞 |

## 4 迁移与前端

```text
$ alembic current → 0007_admin_audit_events (head)
$ alembic check   → No new upgrade operations detected.
$ git status --short frontend → （空）
$ npm test -- --run → Test Files 18 passed (18) / Tests 129 passed (129)
```

原文：`evidence/T03-alembic-check.txt`、`evidence/T03-frontend-test.txt`。T03 零迁移，未改 0001–0007；开发库仍 0004 未触碰。

## 5 实现要点

1. **权限顺序**：`require_permission` 依赖先于路径/查询参数解析；畸形 id 由认证后的 `parse_positive_int`/`parse_uuid` 抛 422，集成用例锁定三态。
2. **锁顺序**：停用/重置先取 `ADMIN_GUARD_LOCK_KEY` 事务级 advisory lock，再按 users id 升序 `FOR UPDATE`，锁内重验操作者（active + 版本一致）与最后管理员计数；`lock_timeout=3000ms`。
3. **失效**：停用/重置/本人改密 `auth_version+1` 并撤销全部未关闭会话；启用不恢复旧版本；单条强退只改一条、不增版本。
4. **活动节流**：认证成功后独立短事务条件更新 `last_activity_at`（30 秒），不写 `expires_at`；监控/首页/日志/schema/探针排除，列表刷新需显式标记；写失败只记 `error_type`，不打印异常正文（避免泄露业务数据）。
5. **审计**：6 类操作事件均已存在于 T02 白名单，未新增事件类型；成功同事务、失败（400/404）独立事务，异常不覆盖原错误码。

## 6 未覆盖项

- 日志列表/详情与 CSV、枚举生成、前端权限组件：T04。
- 首页统计与缓存：T05。
- 私有文档与 GET 调试：T06。
- 留存调度：T07；监控采样/TLS/OAuth：T08。
- 双实例与真实代理/TLS 演练、AC-35 回退演练：T09。
- 最后管理员保护在 HTTP 层不可达（受「停用本人 400」限制），仅服务层防御性验证；验收时需确认此判定。

## 7 结论

**PASS**。AC-01—AC-08 的接口、事务/锁、失效、节流与审计按主文档实现；定向 27 通过、全量 330 通过、前端 129 通过且零改动、零迁移且 `alembic check` 无漂移。
