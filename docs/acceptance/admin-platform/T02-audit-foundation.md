# T02 审计基础 · 证据记录

| 字段 | 值 |
| --- | --- |
| ac_id | AC-09（登录四类事件/成功原子）、AC-10（事件归属与去重，登录/退出部分）、AC-11（DB 故障与降级通道，基础） |
| requirement_ids | ADM-LOG01、ADM-LOG02（T02 部分） |
| executor | 开发实施人（lead agent） |
| executed_at | 2026-11-17 12:10—12:45（Asia/Shanghai） |
| commit_sha | 起点 `92bc80a`（T00–T01 检查点）；T02 改动随本卡本地提交（不 push） |
| workspace_state | 5 个已跟踪文件修改 + 4 个新代码/测试文件 + 证据文档；前端零改动 |
| environment | Windows；Python 3.13.16；PostgreSQL 本地；测试库 `shengshengruer_test`；迁移验证库 `shengshengruer_migration_test`（用后即删） |
| migration_heads | `0007_admin_audit_events (head)` |
| dependency_versions | 无新增、无升级 |
| result | **PASS** |

## 1 改动文件全清单

### 1.1 新增

| 文件 | 说明 |
| --- | --- |
| `backend/alembic/versions/0007_admin_audit_events.py` | `admin_login_events`、`admin_audit_events` + 索引/约束 |
| `backend/app/core/request_context.py` | request_id / event_id 上下文与单调时钟 |
| `backend/app/services/admin/audit.py` | 审计事务服务、summary 白名单、降级文件、健康状态 |
| `backend/app/services/admin/__init__.py` | 包标记 |
| `backend/tests/test_admin_audit.py` | 20 例（见 §5） |

### 1.2 修改

| 文件 | 改动 |
| --- | --- |
| `backend/app/db/models_admin.py` | 新增 `AdminLoginEvent`、`AdminAuditEvent` 模型与索引 |
| `backend/app/api/auth.py` | 登录四类事件接入；`LOGOUT` 同事务；失败路径先回滚业务事务再写独立审计 |
| `backend/app/main.py` | request_id 中间件；统一响应/异常头带 `X-Request-ID`；CORS 暴露该头 |
| `backend/app/core/config.py` | `ADMIN_AUDIT_FALLBACK_DIR` 与路径属性 |
| `.gitignore` | 忽略运行期 `backend/var/` |

### 1.3 `git diff --stat`（提交前）

```text
 .gitignore                     |   1 +
 backend/app/api/auth.py        | 203 ++++++++++++++++++++++++++++++++++++++---
 backend/app/core/config.py     |   9 ++
 backend/app/db/models_admin.py | 155 ++++++++++++++++++++++++++++++-
 backend/app/main.py            |  35 ++++++-
 5 files changed, 388 insertions(+), 15 deletions(-)
```

另有 4 个新文件未计入 `--stat`：`0007_admin_audit_events.py`、`request_context.py`、`services/admin/audit.py`、`services/admin/__init__.py`、`tests/test_admin_audit.py`。

## 2 迁移 0007 往返 + `alembic check`

证据原文：`evidence/T02-migration-roundtrip.txt`。

```text
$ alembic heads
0007_admin_audit_events (head)
$ alembic upgrade head（空库）
... Running upgrade 0006_admin_auth_session -> 0007_admin_audit_events ...
$ alembic current
0007_admin_audit_events (head)
$ alembic check
No new upgrade operations detected.
$ （报告）admin_login_events=admin_login_events
         admin_audit_events=admin_audit_events
         索引：登录表 5 个 ix + pk；操作表 5 个 ix + pk
         公共表数 22
$ alembic downgrade base
... Running downgrade 0007_admin_audit_events -> 0006_admin_auth_session ...
... 直至 base
$ （报告）三张新表均为 None；公共表数 1
$ alembic upgrade head（再次）
$ alembic current → 0007_admin_audit_events (head)
$ alembic check → No new upgrade operations detected.
$ drop database shengshengruer_migration_test
```

结论：0001–0006 未修改；0007 正向/回退/再正向均可；单 head；`alembic check` 两次均无漂移。开发库仍为 `0004_expected_count_source`，未触碰。

## 3 登录四类事件与降级通道（真实输出）

证据原文：`evidence/T02-audit-cases.txt`。

```text
== 1. LOGIN_SUCCEEDED ==
status=200 X-Request-ID=e4b782cd-…
event_type=LOGIN_SUCCEEDED result=SUCCESS reason_code=None actor_user_id=1
username_attempted=admin role_snapshot=admin
summary={'session_id': 'ef334df0-…', 'auth_version': 0}

== 2. UNKNOWN_ACCOUNT ==
status=401
event_type=LOGIN_FAILED result=FAILURE reason_code=UNKNOWN_ACCOUNT
actor_user_id=None username_attempted=ghost_99169a
summary={'failure_type': 'UNKNOWN_ACCOUNT'}

== 3. BAD_PASSWORD ==
status=401
event_type=LOGIN_FAILED result=FAILURE reason_code=BAD_PASSWORD
actor_user_id=1 role_snapshot=admin summary={'failure_type': 'BAD_PASSWORD'}

== 4. DISABLED ==
status=401
event_type=LOGIN_FAILED result=FAILURE reason_code=DISABLED
actor_user_id=16 role_snapshot=student summary={'failure_type': 'DISABLED'}

== 5. DB 写失败 → 降级文件（原 401 不覆盖） ==
status=401
fallback files=['audit-current.jsonl']
fallback event_type=LOGIN_FAILED reason_code=BAD_PASSWORD request_id=ef7ea212-…
health state=warning, last_error_code=AUDIT_DB_WRITE_FAILED

== 6. DB 与文件都失败 → stderr + critical ==
status=401
health state=critical, last_error_code=AUDIT_STORAGE_UNAVAILABLE
log: AUDIT_DB_WRITE_FAILED ...
log: AUDIT_FALLBACK_WRITE_FAILED error_type=FileExistsError
log: AUDIT_STORAGE_CRITICAL request_id=562f26f5-… event_id=653f2ffb-…

== 7. request_id 头 ==
200 header=f7a455c2-… / 401 header=e852eca8-… / 500 header=c8315af4-…

== 8. summary 白名单与 2KiB 上限 ==
keys=['auth_version', 'session_id'] bytes=237 limit=2048

== 9. 审计表敏感字段扫描 ==
contains 'admin123': False / 'password_hash': False / 'eyJ': False / 'jti_hash': False
```

### 3.1 通道分离（复核后修复）

证据原文：`evidence/T02-channel-split.txt`。

```text
audit table rows: 6 -> 7            # USER_STATUS_CHANGED 落 admin_audit_events
login table rows: 139 -> 139        # 登录表不新增
audit row event_type=USER_STATUS_CHANGED result=FAILURE
login row for same request_id: None
fallback record: channel=login event_type=LOGIN_FAILED reason_code=BAD_PASSWORD
fallback record: channel=audit event_type=EXPORT_FAILED reason_code=export_timeout
```

`alembic current / check`（测试库，`0007` 后）：`0007_admin_audit_events (head)`、`No new upgrade operations detected.`，原文 `evidence/T02-alembic-check.txt`。

## 4 全量测试与前端

```text
$ python -m pytest -o addopts= -q -p no:warnings
303 passed in 67.07s
$ git status --short frontend
（空）
$ npm test -- --run
Test Files 18 passed (18) / Tests 129 passed (129)
```

原文：`evidence/T02-backend-pytest.txt`、`evidence/T02-frontend-test.txt`。前端零改动。

## 5 新增测试清单（`tests/test_admin_audit.py`，20 例）

| 用例 | 覆盖点 |
| --- | --- |
| `test_login_success_event_is_committed_with_session` | 成功事件与会话同事务、字段与 summary |
| `test_unknown_account_event` | 未知账号：actor 空、username 落库 |
| `test_bad_password_event` | 密码错误事件 |
| `test_disabled_account_event` | 停用账号事件（actor 有值） |
| `test_failure_audit_uses_independent_commit` | 失败事件独立提交、立即可见 |
| `test_operation_failure_goes_to_audit_table` | 操作失败事件只落 `admin_audit_events`，登录表不新增 |
| `test_operation_failure_db_down_falls_back_with_channel_audit` | 操作通道降级记录 `channel=audit` |
| `test_success_audit_failure_blocks_login` | 成功审计失败 → 500、不发 token、不留 session |
| `test_audit_db_down_falls_back_to_file` | DB 故障 → JSONL 降级、原 401 保留、无敏感值 |
| `test_audit_db_and_file_failure_goes_critical` | 双失败 → stderr 固定码 + critical |
| `test_request_id_header_on_every_response` | 401/200/422/500 均带头且互不相同 |
| `test_summary_whitelist_and_size_cap` | 白名单、≤2KiB、拒绝未登记事件 |
| `test_event_id_is_unique_in_database` | event_id 主键去重 |
| `test_result_check_constraint_rejects_unknown_value` | result CHECK 约束 |
| `test_no_password_token_or_jti_stored` | 密码/token/jti 不落库 |
| `test_logout_writes_same_transaction_event` | LOGOUT 同事务 |
| `test_logout_audit_failure_rolls_back_revocation` | 退出审计失败 → 500 且撤销回滚 |
| `test_occurred_at_is_utc_aware` | 时间带时区 |
| `test_fallback_writer_rotates_and_prunes` | 10MiB/10 份轮转与裁剪 |
| `test_health_snapshot_shape` | 健康状态结构 |

## 6 实现要点与遇到的两个真实问题

1. **失败审计与登录行锁的自死锁**：停用账号路径在 `FOR UPDATE` 持锁后写独立审计事务，外键检查需要同一 `users` 行的 KEY SHARE，会被自身业务事务阻塞。修复：失败路径先 `db.rollback()` 释放锁，再写独立审计；审计异常不覆盖原始 401。
2. **`AppError.headers` 可为 None**：统一异常处理器合并 `X-Request-ID` 时触发 `TypeError`，导致 45 个既有用例失败；改为 `**(exc.headers or {})` 后全量恢复 301 通过。这是回归过程中发现并修复的真实缺陷，已包含在最终测试结果中。
3. **（复核反馈）失败通道未区分事件类型**：`_persist_independent()` 原先无条件调用 `login_row()`，`persist_audit_failure()` 会把操作失败事件写进 `admin_login_events`，撞 `reason_code` CHECK 后静默降级到文件。修复：按通道拆分（`CHANNEL_LOGIN`/`CHANNEL_AUDIT`），登录失败只写登录表、操作失败只写操作表，降级记录新增 `channel` 字段；新增 2 例测试（操作事件落表、降级 `channel=audit`），既有四类登录事件与降级用例保持不变。

## 7 未覆盖项

- 登录/操作日志查询接口与详情 404（AC-12）：T04。
- 操作类事件（用户、任务、缓存、导出、文档调试）只登记了事件类型与 summary 白名单，实际写入由 T03–T06 接入。
- 审计降级文件的“重启后恢复未处理故障提示”与采样页 `server.audit_storage_health` 指标：T08。
- 日志留存清理（90/180 天）：T07。
- 双实例并发审计与真实故障演练：T09。

## 8 结论

**PASS**。0007 可往返且 `alembic check` 无漂移；四类登录事件与 LOGOUT 按事务边界落库；登录/操作两条审计通道分离，降级记录带 `channel`；三级失败通道行为符合主文档 §7.2；后端 303 通过、前端 129 通过且零改动。
