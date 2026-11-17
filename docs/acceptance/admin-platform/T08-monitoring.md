# T08 监控能力 · 证据记录

| 字段 | 值 |
| --- | --- |
| ac_id | AC-16—19、AC-20/21、AC-22、AC-23、AC-34 |
| requirement_ids | ADM-MON03/04/05/06/07/08 |
| executed_at | 2026-11-17 15:10—15:32（Asia/Shanghai） |
| commit_sha | T08a `b696f1b`、T08b `cc0c5a5`、T08c 随本记录提交 |
| environment | Windows；Python 3.13.16（psutil 7.2.2）；Node 24.14.0 |
| migration_heads | `0008_admin_retention_scheduler (head)`，**零迁移** |
| result | **PASS** |

## 1 采样与指标

- lifespan 按 `ADMIN_MONITORING_ENABLED`（默认 true，测试 false）启动 15 秒采样；首次立即采样；停止时取消任务并 dispose 专用引擎。
- DB 专用连接 `connect_timeout=2`、`statement_timeout=1500ms`；失败/超时丢弃连接，不还池。
- 指标含 `instance_id/booted_at/observed_at/source/scope/status/reason/severity`；首次 CPU `unknown(warmup)`；失败保留 `last_success_at`，60 秒后 stale；阈值需连续 3 个有效样本。
- 权限不足/缺表/未启用分别 `unknown/not_configured/not_applicable`，值为 null。
- psutil 安装与版本证据：`T08-psutil-install.txt`（`psutil 7.2.2`）。

## 2 接口

- `GET /admin/monitor/{database,server,cache,cache/entries,transport,oauth}`（monitor:read）；`POST /cache/clear`（cache:clear）。
- 缓存清理实测：域/实例校验 400；`deleted_count=0` 成功；STARTED 提交失败不删除；删除后 CLEARED 失败 → 500 + 降级 + 结果未确认（服务级用例）。
- TLS：`application = TransportEvidenceMiddleware(app)` 最外层；可信代理单一模式；直连/可信 https/伪造/重复/多级链用例；TLS 测试用 `TestClient(application)`。
- OAuth 固定 `not_configured`，`events=[]`。
- `/health/live` 不连库；`/health/ready` 校验 9 张表 + `users.auth_version`，缺结构/断库 503，响应仅 `{"status":"not_ready"}`。
- 模块三默认关闭零查询；开启缺表 `not_configured(missing_table)`；Worker 存活始终 unknown。
- 调试白名单补登 8 条监控 GET（共 17 条）；用例校验每条与真实路由、method、权限闭包一致，并实测可调试、写接口仍 400。

## 3 前端

- `/admin/monitor/{database,server,cache,transport,oauth}`（monitor:read）、`/monitor/jobs`（job:read）。
- `useMonitorPolling`：15 秒、hidden 停止、visible 立即、非重入、AbortController、序号丢弃旧响应。
- 状态用文字呈现：正常/错误/未知/数据过期/未启用未配置/不适用；TLS 页明确静态 origin ≠ 已验证；OAuth 页说明未部署与 JWT 现状。
- 缓存页只展示元数据，清理需理由并回显“无条目/已清理”。

## 4 测试

```text
后端定向：17 passed in 6.83s（采样 6 + 监控 API/健康/白名单 11）
后端全量：431 passed in 126.62s（420 + 11）
前端全量：192 passed（187 + 5）
typecheck：通过；build：✓ built
alembic current → 0008；alembic check → No new upgrade operations detected.
```

## 5 未覆盖项

- 真实反向代理/证书部署演练、Uvicorn `--no-proxy-headers` 实机启动属 T09。
- 模块三真实表不存在，开启分支只验证“缺表/断库”语义。
- 前端 1280/1920 视觉走查、真实浏览器长轮询属 T09。
- 双实例缓存/监控的集群视图未实现（按单实例设计）。

## 6 结论

**PASS**。采样、指标、缓存、TLS、OAuth、健康、模块三只读与白名单按 §9 实现；零迁移、无新权限/事件码，后端 431、前端 192 全绿。
