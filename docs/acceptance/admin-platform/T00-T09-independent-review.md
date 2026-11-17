# 管理端 T00–T09 独立验收复核报告

| 字段 | 值 |
| --- | --- |
| 验收角色 | 独立验收人（未参与开发；本轮只复核，不改代码、不 commit、不 push、不建 PR） |
| 执行时间 | 2026-11-17 15:55—18:05（Asia/Shanghai） |
| 待验收分支 | `feature/admin-platform`，HEAD `d5876701091799850cdb3092a3a72d0a572e90f3` |
| 基线 | `develop` `3609186`；`develop..HEAD` 共 20 个提交 |
| 工作区 | 开工时 `git status --short` 为空；复核结束时仍为空，HEAD 未变 |
| 需求文档 | `docs/requirements/admin-platform/requirements.md`，SHA-256 `728105bdefece77759cdf69f30723e35bf48859b75e78dbf8637e5c4dac8cc74`（自算一致） |
| 主开发文档 | `D:\guochuangxiangmu\docs\development\admin-platform\development.md`（V1.0，§14/§16.1 为映射依据） |
| 环境 | Windows；Python 3.13.16（`backend/.venv`）；Node 24.14.0；PostgreSQL 18.6 本地 |
| 数据库边界 | 只使用 `shengshengruer_test` 与临时迁移库 `shengshengruer_accept_mig`（用后删除）；开发库 `shengshengruer` 前后两次只读快照一致 |
| 结论 | **PASS（含 PARTIAL/未实测项；无 A/B 级问题）** |

> 本报告结论来自本人真实执行与代码核对，不照抄开发方 T00–T09 记录；开发方记录仅作为线索。
> 证据原始输出保存在 `C:\Users\zxy\AppData\Local\Temp\admin-acceptance\`（`review-*.txt` 与 `*.py`），不属于仓库内容。

---

## 0. 环境异常说明（非项目缺陷）

开工时命令沙箱全部无法启动：

```text
Error: sandbox-local: windows-acl temp grant materialization failed and its cleanup also failed:
Win32Error: SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\pytemp\dsh-XXXX).
```

根因：本会话 `TMP/TEMP=D:\pytemp`（与委托要求"使用默认 `C:\Users\zxy\AppData\Local\Temp`、不要用 `D:\pytemp`"相反），
DSH 沙箱在该目录物化临时授权失败。ACL 诊断脚本结论为 `VERDICT=NOT_THIS_CLASS`（`D:\pytemp` 自身对当前用户具备
`WRITE_DAC`/`WRITE_OWNER`，无包 SID 允许项可清理），故未做任何权限修复。

处置：本轮所有命令以"完全权限"单次授权执行（只读为主，写入仅限测试库与本人临时目录），
临时脚本/输出一律放在 `C:\Users\zxy\AppData\Local\Temp\admin-acceptance\`，未使用 `D:\pytemp`。
该问题属于运行环境，不影响被验收分支的代码结论，但需要环境负责人修正会话 TEMP 或 ACL 才能恢复常规沙箱。

---

## 1. 独立执行命令与原始结果

### 1.1 分支与基线

```text
$ git status --short          → 空
$ git rev-parse --abbrev-ref HEAD → feature/admin-platform
$ git rev-parse HEAD          → d5876701091799850cdb3092a3a72d0a572e90f3
$ git rev-list --count develop..HEAD → 20
$ git log --oneline -1 develop → 3609186 Merge pull request #16 ...
$ Get-FileHash requirements.md -Algorithm SHA256
  → 728105BDEFECE77759CDF69F30723E35BF48859B75E78DBF8637E5C4DAC8CC74（与文档一致）
```

### 1.2 后端全量测试（独立执行）

```text
cd backend
.\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:warnings

........................................................................ [ 50%]
........................................................................ [ 66%]
........................................................................ [ 83%]
.......................................................................  [100%]
431 passed in 136.23s (0:02:16)
EXIT=0
```

与开发方 T09 声称的 431 passed 一致；无 skip/xfail（全仓 grep `pytest.mark.skip|xfail` 无匹配）。

### 1.3 前端测试 / 类型检查 / 构建（独立执行）

```text
$ npm test -- --run
 Test Files  35 passed (35)
      Tests  193 passed (193)
   Duration  35.94s
EXIT=0

$ npm run typecheck
TYPECHECK_EXIT=0

$ npm run build
✓ 3244 modules transformed.
✓ built in 850ms
BUILD_EXIT=0
（告警：部分 chunk > 500 kB，swagger-ui-es-bundle 1,545.57 kB）
```

与开发方 T09 声称的 193 passed / typecheck / build 通过一致。

### 1.4 迁移往返（独立临时库 `shengshengruer_accept_mig`）

```text
$ alembic heads   → 0008_admin_retention_scheduler (head)      （单 head）
$ alembic upgrade head（空库）
  0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008
$ alembic current → 0008_admin_retention_scheduler (head)
$ alembic check   → No new upgrade operations detected.
$ alembic downgrade base
  0008 → … → 0001（无异常）
$ alembic current → （空）
$ alembic upgrade head（再次）→ 0008 (head)
$ alembic check   → No new upgrade operations detected.
$ 结构报告：alembic_version=0008；public_table_count=25；job_seed_count=1；users.auth_version 列存在
$ DROP DATABASE shengshengruer_accept_mig（已删）
```

结论：单 head、可正向/回退/再正向、两次 `alembic check` 无漂移；0001–0005 历史迁移未被改写。

### 1.5 开发库未被改动（前后两次只读快照）

```text
开工：ALEMBIC_VERSION=0004_expected_count_source；PUBLIC_TABLE_COUNT=16
结束时：ALEMBIC_VERSION=0004_expected_count_source；PUBLIC_TABLE_COUNT=16
表：alembic_version,audio_files,content_checks,content_groups,exam_papers,import_batches,
    paper_visibility,passages,presentations,questions,roles,token_revocations,
    transcript_segments,user_roles,users,visibility_audit_logs
PG_VERSION=18.6
```

开发库保持 0004 / 16 表 / 无新表，与开工一致；本轮迁移与测试未触碰开发库。

### 1.6 枚举生成物一致性

```text
$ python scripts/generate_admin_constants.py --check
管理端常量与后端枚举一致。        CONST_EXIT=0
```

---

## 2. 独立 HTTP 抽查（TestClient + 真实 PostgreSQL 测试库）

分 7 个脚本执行（仅连接 `shengshengruer_test`，表名故障注入均自动恢复；复核后测试库仍为 25 表、无残留 `_accept_tmp`）。

| 轮次 | 覆盖 | 结果 |
| --- | --- | --- |
| 1 | docs 404、受保护 schema、调试白名单、旧 token、权限、账户/会话、审计、日志、CSV、监控、任务、首页、学生回归 | 129 项：123 PASS；6 项初判失败，逐项复核后**全部为脚本假设错误**（见下） |
| 2 | 日志时间参数（正确参数名 `start_at/end_at`）、真实采样、DB 故障注入、审计失败注入 | 全部 PASS |
| 3 | 故障注入（表改名）+ 任务暂停/恢复 + 首页窗口 | 17 PASS；9 项初判失败均为脚本字段名假设错误（`metrics` 名称/`domain` 取值/降级文件是"每请求子目录"） |
| 4 | 首个采样后的指标明细、缓存元数据与清理 happy path | 11 PASS；2 项初判失败为字段名假设错误（磁盘指标名为 `audio_storage_*`、DB size 的 `scope=database`） |
| 5 | 指标来源/单位明细打印 | 只读取证，无断言 |
| 6 | 活动节流 | 3 PASS；1 项初判失败为脚本假设错误（显式标记仍受 30 秒节流，符合"活动最多 30 秒刷新一次"） |
| 7 | 审计降级通道（失败路径） | 401 原错误保留 + 降级文件字段与脱敏均符合 |

### 2.1 关键实测输出（摘录）

```text
AC13 /docs,/redoc,/openapi.json,/api/v1/openapi.json,/docs/oauth2-redirect → 全部 404
AC13 /api/v1/admin/openapi.json：无 token 401；学生 403；管理员 200
     原始 JSON（keys=components,info,openapi,paths,x-admin-debug-allowlist；无 code/data 外壳）
     paths=41；Cache-Control: no-store；无 JWT_SECRET/DATABASE_URL/演示密码
AC14 调试标记：POST→400；导出→400；学生→403；无 token→401；值非 1→400；
     尾斜杠→400；%2F→400；白名单 GET→200 且写 DOC_GET_DEBUG(SUCCESS)；
     目标 404 不被绕过（仍 404，事件 FAILURE）；summary 仅 {method,status_code,path_template}
AC35 去除 auth_version/session_id 的旧 JWT → 401；畸形 token → 401
AC28 admin getInfo permissions=21；student=[]；旧字段 {user,roles,is_admin} 保留
     学生调 /admin/users→403；无 token→401；/admin/users/abc→422（鉴权先于参数解析）
AC01 创建 student 200；重名 400；非法用户名 422；extra 字段 422；详情 200；筛选 total=1
AC02 昵称持久化；停用 changed=true，revoked_session_count=1；旧 token 401；停用后登录 401；
     启用后旧 token 仍 401，重新登录 200
AC04 重置密码后旧会话 401、旧密码 401、新密码 200；重置本人 400
AC05 本人 DTO 仅 {id,username,nickname,role,status,created_at,updated_at}（无部门/岗位）
AC06 旧密码错误 400；改密成功后旧 token 401；新密码登录 200
AC08 两会话均有效→强退其一→{401,200}；重复强退 changed=false；强退当前 400；
     会话 DTO 无 jti/token/jti_hash
AC09 密码错误/未知账号/成功 三类事件均按 request_id 落库；未知账号 actor_user_id=NULL
AC10 停用操作只落 admin_audit_events(USER_STATUS_CHANGED/SUCCESS)，登录表同 request_id 0 行
     重复同状态 changed=false
AC11 审计表无 admin123/eyJ 泄漏
AC12 默认窗口 200；仅 start_at/仅 end_at/反向/超 90 天/无时区/非法 page_size/page=0 → 422；
     未知详情 404；学生 403
AC31 导出 200 text/csv；UTF-8 BOM；CRLF；中文表头；attachment + no-store；
     0 行仅表头（CRLF=1）；5001 行→400 JSON（非 CSV，不截断）
AC32 昵称 "=1+1" 导出为 "'=1+1"；审计失败时 500 且不交付 CSV
AC16 database_size_bytes=28,792,511 bytes(source=postgresql,scope=database)；
     active_connections=1；pool_size=5(source=sqlalchemy_pool)；probe_latency_ms unit=ms
AC18 首次 system_cpu unknown/warmup/value=null；system_memory_used_percent=69.4%；
     process_rss_bytes=96,702,464；audio_storage_free/used（psutil/filesystem）
AC19 module3={status:not_configured,reason:disabled,worker_liveness:unknown}（默认关闭，早退无查询）
AC20 首页首读 cache.status=miss→次读 hit；ttl_seconds=15；entries≤1；redis=not_configured
AC21 非法域 400；实例不符 400；当前实例清理 200 deleted_count=0（无条目）；
     错 instance_id 不伪造成功
AC22 transport={direct_scheme:unknown,external_tls_state:unknown,source:unknown,reason:evidence_missing}
AC23 oauth={status:not_configured,reason:oauth_server_not_deployed,events:[],login_mode:jwt_bearer}
AC27 非白名单任务 400；未知任务 runs 404；无健康调度器时立即执行 400（不留孤儿队列）；
     暂停/重复暂停/恢复 changed 语义正确；scheduler_health=not_configured
AC30 首页 cards 仅 6 项聚合；timezone=Asia/Shanghai；window=[今天-6天00:00, now)；旧 /admin/overview 200
AC34 /health/live 200 alive；/health/ready 200 ready（表格缺失时 503 {"status":"not_ready"}，恢复后 200）
```

### 2.2 故障注入结果（本人执行，非开发方脚本）

| 注入方式（测试库，注入后自动恢复） | 观测 | 结论 |
| --- | --- | --- |
| `ALTER TABLE auth_sessions RENAME` 后请求 `/admin/me` | HTTP 500，body `{"code":500,"msg":"服务器内部错误","data":null}`，无 SQL/psycopg 细节，仍带 `X-Request-ID` | **DB 异常是 500，不伪装 401**，通过 |
| `ALTER TABLE users RENAME` 后 `/health/ready` | 503 `{"status":"not_ready"}`；`/health/live` 仍 200 alive；恢复后 ready 200 | 通过 |
| `ALTER TABLE admin_login_events RENAME` 后"成功登录" | 500，响应无 token | 成功审计失败不签发 token，通过 |
| 同上，改为"错误密码登录" | 仍 401（原错误保留）；降级文件 `<request_id>/audit-current.jsonl` 记录 `channel=login,event_type=LOGIN_FAILED,reason_code=BAD_PASSWORD`；无密码/token | 失败独立通道 + 降级文件，通过 |
| 活动节流 | 读监控不刷新；隐式用户列表不刷新；30 秒内显式标记同样不刷新（节流上限 30 秒） | 通过 |

---

## 3. 验收矩阵（AC-01—AC-36，按主文档 §14/§16.1 映射）

结论口径：**PASS** = 本人真实执行通过；**PARTIAL** = 部分执行/受限，注明缺什么；**未实测** = 开发方也未宣称（真实 TLS、浏览器 DOM/下载、视觉走查等）。

| AC | 验收点（摘要） | 证据来源（本人执行） | 结论 |
| --- | --- | --- | --- |
| AC-01 | 两角色创建/查询、重名仅一行 400、非法 422、401/403、审计 | `review-http.txt` AC01 段；pytest 431 | **PASS** |
| AC-02 | 昵称持久化、停用/启用后旧 token 都失效、重复 changed=false、extra 422 | `review-http.txt` AC02 段 | **PASS** |
| AC-03 | 本人停用 400、有效 admin 不归零、并发/事务一致、业务数据不删 | HTTP 本人停用 400；`guards.py` 保护锁与计数核对；并发与"最后管理员"仅服务层测试 | **PARTIAL**（HTTP 层因"停用本人 400"不可达，缺并发实测） |
| AC-04 | 重置后旧会话/旧密码失效、新密码可用、本人 400、无明文 | `review-http.txt` AC04 段 | **PASS** |
| AC-05 | 本人资料仅昵称、无部门/岗位、额外字段 422、学生 403 | `review-http.txt` AC05 段 | **PASS** |
| AC-06 | 旧密码错误 400、成功后全设备失效并重登 | `review-http.txt` AC06 段 | **PASS** |
| AC-07 | 两会话/账号去重、5 分钟在线、轮询不保活、30 秒节流、跨进程一致 | 两会话与节流实测；5 分钟严格边界、跨 API 进程仅 pytest | **PARTIAL**（边界/跨进程未独立实测） |
| AC-08 | 单条强退、其他会话继续、当前 400、重复幂等、无 jti | `review-http.txt` AC08 段 | **PASS** |
| AC-09 | 四类登录、未知 ID 为空、统一 401、成功日志失败不发 token | AC09 段 + 故障注入（审计失败 500 无 token） | **PASS** |
| AC-10 | 事件归属、通道分离、回滚只见失败、event_id 不重复 | 通道分离实测；回滚与 event_id 去重仅 pytest/代码 | **PARTIAL** |
| AC-11 | DB 故障 500、原错误不覆盖、降级/critical、敏感值 | DB 500 实测；失败降级文件实测；双失败 critical 仅 pytest | **PARTIAL**（critical 分支未独立注入） |
| AC-12 | 筛选/默认 7 天/90 天上限/非法时间/分页/详情 404/无删改 | `review-http2.txt` AC12 段（含正确 `start_at/end_at`） | **PASS** |
| AC-13 | 私有 schema 三身份/过期退出 401/旧入口 404/原始 JSON | `review-http.txt` AC13 段 | **PASS** |
| AC-14 | 默认只读、仅白名单 GET、写/导出/其他 host 拒绝、审计、不绕过目标鉴权 | AC14 段 + `docs_debug_middleware.py` 代码核对 | **PASS** |
| AC-15 | 根与 `/listening/` 静态资源、离线无 CDN、无凭证 | schema 无凭证、构建产物本地 swagger 实测；子路径部署本人未复跑 | **PARTIAL**（子路径静态仅开发方记录） |
| AC-16 | 真实 PG 查询/池指标、来源/单位/范围、探针语义 | `review-http5.txt`（size/connections/pool/latency 明细） | **PASS** |
| AC-17 | 断库/超时/鉴权 500、旧值保留、恢复新样本 | ready 503、DB 500 实测；监控 stale/旧值保留仅 pytest | **PARTIAL** |
| AC-18 | Windows/Linux 采样、首次 CPU unknown、连续 3 次阈值、缺目录不新建、stale 60s | Windows 首采 warmup/内存/RSS/磁盘实测；Linux、60 秒 stale、连续 3 样本仅 pytest | **PARTIAL** |
| AC-19 | 未集成 not_configured、只读字段、无任务≠Worker 在线、无控制调用 | module3 默认关闭实测（`disabled`+worker unknown），代码早退无查询；集成分支无真实表 | **PARTIAL** |
| AC-20 | 首 miss/后 hit/15 秒/最多 1 项/重启计数/Redis 未配置 | miss/hit/ttl/entries/redis 实测；15 秒到期与重启计数仅 pytest | **PARTIAL**（过期与重启未独立实测） |
| AC-21 | 元数据、实例/域校验、清当前实例、双阶段审计、两实例不声称全局 | 域/实例 400、清理 200、deleted_count 实测；审计故障与双实例仅 pytest/代码 | **PARTIAL** |
| AC-22 | 真实外 HTTPS 内 HTTP、伪造头、无证据 unknown、不返回私钥 | transport 实测 `unknown/evidence_missing`（不伪造 TLS）；真实 TLS/代理 **未实测** | **未实测** |
| AC-23 | OAuth 固定未启用、无假授权事件、学生 403、不新增服务 | `review-http.txt` AC23 段 | **PASS** |
| AC-24 | 90/180/7 天边界、严格 `<`、原件/模块三/attempts/users 不变 | `retention.py` 删除 SQL 严格 `<`；边界数据与"无变更"断言仅 pytest | **PARTIAL** |
| AC-25 | 双调度同 slot 一份、并发手动一份、崩溃/锁丢失 INTERRUPTED、计数不完整标志 | 代码核对（`advisory_connection`、获锁后 `recover_stale_runs`、attempt<2 回队否则 INTERRUPTED）；双进程实测未做 | **PARTIAL** |
| AC-26 | 暂停不取消运行、恢复下一计划、24h 只补最近、失败 60s 重试、60s/5 万行 PARTIAL | 暂停/恢复 HTTP 实测；补跑/重试上限仅 pytest | **PARTIAL** |
| AC-27 | 未授权 403、非白名单 400、无健康调度器立即 400 不留队列、QUEUED 非完成 | `review-http.txt`/`http3` AC27 段 | **PASS** |
| AC-28 | 固定 21 码、学生空、移除单码 403、getInfo 兼容、管理员个人结果 403 | getInfo 21/[]、403/401/422、attempt-status 403 实测；前端按钮显隐由 pytest | **PASS**（前端部分为测试佐证） |
| AC-29 | 改枚举未生成则 check 失败、重新生成通过、未知值只读、旧枚举不改 | `--check` 退出 0；"改值失败"由 `test_admin_constants.py` 覆盖 | **PASS**（负向仅测试佐证） |
| AC-30 | 多批次/通过未开放/失败/混合角色/北京时间边界、只返回聚合 | 首页 6 项聚合、时区与窗口实测；SQL 逐项对照仅 pytest | **PASS**（边界为测试佐证） |
| AC-31 | 三类 CSV 与列表一致、0 行/5000/5001、5MiB、15 秒、403/401 | BOM/CRLF/表头/0 行/5001→400/403/401 实测；5MiB 与 15 秒仅 pytest | **PARTIAL**（5MiB、15 秒未独立构造） |
| AC-32 | 引号/换行/公式防护、白名单字段、审计失败不交付、行数准确 | 公式前缀实测；审计失败 500 不交付实测；引号/换行仅 pytest | **PASS**（部分为测试佐证） |
| AC-33 | 1280/1920、键盘焦点、筛选分页保留、状态可辨、双击不重放 | 前端 193 用例通过；真实浏览器/视觉 **未实测** | **未实测** |
| AC-34 | live 不依赖 DB、ready 断库/缺迁移 503 恢复、API 停止外部失败 | live 200、ready 503→200 实测；外部探针（真实停机）未实测 | **PASS**（外部探针未实测） |
| AC-35 | 旧 JWT 统一 401、迁移独立 PG 往返/单 head、无重写历史、回退说明 | 旧 JWT 401、迁移往返、单 head 实测；DD-01 四类回退演练未实测 | **PASS**（回退演练未实测） |
| AC-36 | 原认证/题库/可见性/最低检查/音频/作答门禁、管理员读学生结果 403 | 全量 431 通过；学生试卷列表、管理员 attempt-status 403 实测 | **PASS** |

---

## 4. 问题分级

### A 级（阻断）— 无

未发现阻断交付的缺陷。

### B 级（需修）— 无

本轮未发现必须修复的缺陷。

### C 级（建议）

| 编号 | 现象 | 证据/位置 | 影响 |
| --- | --- | --- | --- |
| C-1 | 应用启动后极短时间内 `/admin/monitor/server` 可能返回 `metrics={}`（脚本 3 观测到空，脚本 4 同环境为 9 项）；首个采样完成前无显式 `unknown` 占位 | `review-http3.txt` 首行 `SERVER_METRIC_KEYS= []`；`review-http4.txt` `EARLY_METRIC_COUNT= 9` | 前端在启动瞬间可能显示空指标；不伪造 0，数秒内自愈。建议采样启动前先写入 `unknown(warmup)` 占位 |
| C-2 | `DocsDebugMiddleware` 位于 CORS 内层，其直接返回的 400/401/403 不带 CORS 响应头 | `main.py:99-109`（CORS 先加、调试后加） | 同源管理端无影响；若未来跨域调用调试接口会出现浏览器侧 CORS 报错 |
| C-3 | T04 记录 §6 写"前端未新增 `/admin/users`、`/admin/profile` 页面…留后续卡"，但 T03-FE 记录已交付用户页/个人中心 | `T04-logs-exports-ui.md:90` vs `T03FE-users-profile-ui.md` | 文档表述不一致，不影响代码；建议在 T04 记录上补一句"已由 T03-FE 交付" |
| C-4 | `npm run build` 提示 chunk > 500 kB（`swagger-ui-es-bundle` 1.5 MB） | `review-build.txt` | 首屏不受影响（文档页懒加载），建议后续按需拆包 |
| C-5 | Alembic 迁移描述在 GBK 控制台显示为乱码 | `review-migration.txt` 中 0004–0008 描述 | 仅控制台编码问题，迁移脚本本身 UTF-8 正常 |

### 未实测（开发方也未宣称，不计为失败）

真实 TLS 终止/证书与真实反向代理、Linux 采样、模块三真实集成、OAuth 真实服务、1280/1920 视觉与键盘走查、
真实浏览器 DOM/CSV 下载、双 API/双调度进程真实编排（仅自动化与代码核对）、DD-01 四类回退演练。

---

## 5. 结论

**PASS（含 PARTIAL/未实测项）。**

- 代码与文档基线一致：分支 `feature/admin-platform` @ `d587670`，20 提交，工作区干净；需求 SHA-256 与文档一致。
- 独立执行门禁全部通过：后端 431 passed、前端 193 passed、typecheck、build、单 head 迁移往返 + 两次 `alembic check` 无漂移、枚举生成物 `--check` 一致。
- 独立 HTTP/故障注入覆盖了安全与事务关键面：公开文档入口真 404、受保护 schema 三身份、调试白名单仅 GET 且不绕过目标鉴权、旧 token 401、DB 异常 500 不伪装 401、审计失败不发 token 且原 401 保留、导出 BOM/CRLF/公式前缀/5001 行拒绝、监控不伪造 0、模块三默认关闭、缓存 miss/hit/TTL、任务权限与白名单。
- 开发库保持 `0004_expected_count_source` / 16 表，未被本轮任何操作触碰；临时迁移库已删除。
- 未发现 A/B 级缺陷；C 级为体验/文档/构建提示类建议，不阻断放行。
- 受限项集中在"必须真实运行环境才能验证"的语义（TLS、双进程、Linux、浏览器、模块三），与开发方在 T09 §7 的自述一致；这些项应在部署环境或后续阶段补验，而不是以本轮自动化结果替代。

**放行建议**：可作为阶段一交付合入 `develop`；合并前请在 PR 描述中保留 §4 的未实测清单与 C-1/C-2 两项已知限制。

---

## 附录：本轮证据文件（临时目录，非仓库）

| 文件 | 内容 |
| --- | --- |
| `review-backend-pytest.txt` | 后端全量 431 passed 原始输出 |
| `review-frontend-test.txt` | 前端 35 文件 / 193 用例原始输出 |
| `review-typecheck.txt`、`review-build.txt` | typecheck 与 build 原始输出 |
| `review-migration.txt` | 迁移往返 + alembic check 原始输出 |
| `review-http.txt` | 第一轮 129 项 HTTP 抽查 |
| `review-http2.txt` | 日志时间参数 + 真实采样 + 故障注入 |
| `review-http3.txt` | 表名故障注入 + 任务控制 + 首页窗口 |
| `review-http4.txt` | 首个采样后指标 + 缓存清理 |
| `review-http5.txt` | 指标来源/单位明细 |
| `review-http6.txt` | 活动节流 |
| `review-http7.txt` | 审计失败降级通道 |
| `devdb_snapshot.py`、`verify_tables.py`、`http_checks*.py`、`migration_roundtrip.ps1` | 本人使用的只读/测试库脚本 |

本报告只写入 `D:\guochuangxiangmu\docs\acceptance\admin-platform\T00-T09-independent-review.md`，未修改仓库任何文件，未 commit、未 push、未建 PR。
