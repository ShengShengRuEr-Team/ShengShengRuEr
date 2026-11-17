# T07 留存调度 · 证据记录

| 字段 | 值 |
| --- | --- |
| ac_id | AC-24、AC-25、AC-26、AC-27（AC-35 迁移往返、AC-36 回归） |
| requirement_ids | ADM-MON02 |
| executor | 开发实施人（lead agent） |
| executed_at | 2026-11-17 14:48—15:10（Asia/Shanghai） |
| commit_sha | 起点 `2eb999c`；T07 三个子提交：`026f77b`(a)、`82354cc`(b)、T07c 随本记录提交 |
| workspace_state | 后端三表/调度进程/控制 API；前端任务监控页；仅新增 0008 |
| environment | Windows；Python 3.13.16；Node 24.14.0；PostgreSQL 本地；测试库 `shengshengruer_test` |
| migration_heads | `0008_admin_retention_scheduler (head)` |
| dependency_versions | 无新增、无升级；未引入 Celery/APScheduler/Redis |
| result | **PASS** |

## 1 迁移 0008

`down_revision=0007_admin_audit_events`，只新增三表并 seed 唯一任务定义；实测独立库：

```text
upgrade head → 0008；report: admin_job_* 三表存在，job_seed_count=1，公共表 25
alembic check → No new upgrade operations detected.
downgrade base → 三表 None、表数 1
upgrade head → 0008；alembic check 再次无漂移
```

`next_scheduled_at` 迁移时 NULL，由调度进程启动时计算并持久化（推定项，已确认）。

## 2 调度进程与状态机

- `python -m app.admin_scheduler`：独立进程、不嵌入 API lifespan、不启动模块三 Worker；15 秒心跳线程。
- 互斥：专用连接 session 级 advisory lock；取得锁后提交结束 SELECT 事务；异常路径 unlock + close，不还池。
- 手动触发：`pg_try_advisory_xact_lock` 与 QUEUED 插入同事务；API 提交后调度进程可立刻获锁（用例锁定）。
- 补跑：只建最近 03:10 slot；更早累计 missed_slots；暂停不累计；恢复下次计划严格未来。
- 状态机：attempt≤2、60 秒重试、RUNNING>120 秒为候选、新执行者获锁后才判 INTERRUPTED/重新排队。

## 3 删除与计数

- 白名单 5 表；每批 1000；批间提交；60 秒/50000 行预算；严格 `<`、相等保留。
- 实测边界：登录 90 天、审计 180 天（排除当前 run）、job_runs 180 天（终态且非 retry_pending）、auth_sessions 7 天（`greatest(expires,revoked)`）、token_revocations `expires_at < as_of`。
- 预算测试：行数上限与注入时钟超时均返回 `PARTIAL`，剩余数据保留、不紧循环。
- 失败：提交未知时 `counts_complete=false`、FAILED、保留 active 并排 60 秒重试。
- 模块三/attempts/users/roles/音频计数前后不变（用例逐项断言）。

## 4 控制 API 与事件

| 接口 | 权限 | 实测 |
| --- | --- | --- |
| `GET /admin/monitor/jobs` | job:read | not_configured / ok / stale；实例心跳列表 |
| `GET /admin/monitor/jobs/{job_id}/runs` | job:read | 分页；未知任务 404；page_size 非法 422 |
| `POST .../enabled` | job:control | changed/重复 changed=false 不写事件；JOB_PAUSED/RESUMED 同事务 |
| `POST .../run` | job:control | 无/过期心跳 400；已有保留位 400；成功 200 `{run_id,QUEUED}` + JOB_TRIGGERED |

401/403 顺序、学生 403；非白名单 job 400；`/admin/monitor` 读取不刷新活动时间（用例）。

## 5 前端

- `/admin/monitor/jobs`（`admin:job:read`）：任务配置、启用开关、下次/上次 slot、missed、active/last run、实例心跳、执行记录（状态/尝试/重试/计数完整/错误码）。
- 轮询 15 秒；`document.hidden` 停止、visible 立即刷新；在途请求不重入。
- 暂停/恢复与立即执行均需 1—200 字理由；`QUEUED` 明确“等待调度执行”；`counts_complete=false` 显示“结果未确认”。

## 6 测试

```text
后端定向：29 passed in 6.18s（模型 5、状态机/互斥 16、控制 API 8）
后端全量：414 passed in 122.00s（406 + 8）
前端全量：187 passed（182 + 5）
typecheck：通过；build：✓ built
alembic check：无漂移
```

## 7 过程中发现并修复

1. 0008 约束名被命名约定重复加前缀（`ck_admin_job_runs_ck_...`）→ 迁移使用短名，由约定生成完整名。
2. advisory 锁连接上的 `SELECT pg_try_advisory_lock` 开启事务，导致后续 Session.commit 只在子事务内、连接关闭整体回滚、run 消失 → 取得锁后立即 `commit()` 结束该事务；tick 端到端用例锁定。
3. 跨用例状态污染（残留活动 run / 旧撤销记录）→ 调度与留存用例在前后复位定义、清理标记数据；健康度用例先清心跳再构造 stale。

## 8 未覆盖项

- 真实双调度进程/双 API 进程编排与 SIGTERM 优雅退出 E2E 属 T09。
- 调度进程的自动重连策略未实现（按文档“断连退出当前执行、不自动重连后继续删除”）。
- 前端 1280/1920 视觉走查与真实浏览器轮询属 T09。

## 9 结论

**PASS**。三表与 0008、独立调度进程、互斥/补跑/重试/中断、批删除与计数、控制 API/事件、任务监控页均按 §5.3/§10 实现；后端 414、前端 187 全绿，迁移往返与 check 无漂移。
