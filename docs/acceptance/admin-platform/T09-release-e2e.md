# T09 联调与交付 · 执行记录

| 字段 | 值 |
| --- | --- |
| ac_id | AC-33、AC-34、AC-35、AC-36（AC-22 仍为未实测） |
| executor | 开发实施人（lead agent） |
| executed_at | 2026-11-17 15:34—15:56（Asia/Shanghai） |
| environment | Windows 10.0.26100；Python 3.13.16；Node 24.14.0；psycopg 3.3.6；测试库 `shengshengruer_test` |
| branch / head | `feature/admin-platform` / `7c426d0`（演练后） |
| migration_heads | `0008_admin_retention_scheduler (head)`，T09 零迁移 |
| result | **PASS（含 PARTIAL/未实测项，见第 7 节）** |

## 1. 启动与路径

| 项 | 结果 | 证据 |
| --- | --- | --- |
| 根路径 `uvicorn app.main:application --no-proxy-headers` | PASS：live/ready 200、登录 200 | `T09-core-e2e.txt` |
| 子路径 `/listening/`（`--root-path` + 一次性代理剥离） | PASS：index 200、`/listening/assets/*` 200、深链刷新 200（SPA）、代理登录/`me` 200 | `T09-subpath-proxy.txt` |
| 后端直连 `/listening/api/...` | 404（证明 `root_path` 不参与路由，必须由代理剥离） | 同上 |
| 登录 redirect 白名单 | 代码守卫存在（拒绝 `//`、反斜杠、登录页自跳），T01/T03 既有测试覆盖；T09 未另做浏览器开放重定向实测 | `LoginPage.tsx` 用例 |

子路径构建：`VITE_BASE=/listening/ VITE_API_BASE_URL=/listening/api/v1 npm run build`，产物引用 `/listening/assets/...`。

## 2. 双实例联调（测试库，8001/8002）

- 跨实例：A 登录 → B `/admin/me` **200**。
- 跨实例撤销：在 B 撤销 A 签发的会话 → 同一 token 在 A、B 均 **401**。
- 实例隔离：两实例 `/monitor/cache` 与 `/monitor/database` 的 `instance_id` 不同；池指标按实例返回，未相加。
- 学生端：B 登录 + `/listening-papers` **200**。
- 导出：`/admin/exports/users` **200**、`text/csv; charset=utf-8`、首行表头（含 BOM）。
- 活动节流跨实例：**未单独实测**（T03 自动化覆盖 30 秒/不延长 expires）。
- 缓存 hits 在两实例均为 0（首次访问，未额外制造命中差异）。

证据：`T09-core-e2e.txt`。

## 3. 调度进程（独立进程）

- 心跳：monitor/jobs `scheduler_health=ok`，实例数 1。
- 手动触发：200 `{state:"QUEUED"}`，调度执行后 `SUCCEEDED`、attempt=1、counts_complete=true。
- 暂停/恢复：均 200、changed=true。
- 停止 62 秒：`stale`；重启后恢复 `ok`。
- 证据：`T09-scheduler.txt`。

## 4. 迁移演练（AC-35）

临时库 `shengshengruer_migration_test`（用后已删）：0001→0008 全链 upgrade → downgrade base → upgrade。

```text
alembic heads → 单 head 0008
alembic check → No new upgrade operations detected.（两次）
alembic_version=0008；job_seed_count=1；public_table_count=25（升级后）
downgrade base 后仅 alembic_version 保留（表数 1）
re-upgrade 后表数 25、seed 1、check 无漂移
```

说明：downgrade base 会删除业务表，往返验证的是 schema 可重建与 seed 可读，**不承诺业务数据保留**。证据：`T09-migration-roundtrip.txt`。

## 5. 安全回退与探针

- JWT 轮换：K1 签发 token → 以 K2 重启 → 旧 token `/admin/me` **401**，新登录 **200**；未修改 `.env`/密钥文件。
- `/health/live`：200 `{"status":"alive"}`（含 DB 不可达实例）。
- `/health/ready`：正常 200 `{"status":"ready"}`；`DATABASE_URL` 指向不可达端口（5999）的实例 → **503** `{"status":"not_ready"}`，响应无连接串/版本。
- 证据：`T09-probes-jwt.txt`。

## 6. 真实代理/TLS（AC-22）

- 一次性本地反向代理（`D:\pytemp\t09_proxy.py`，不引入依赖）验证了前缀剥离、静态资源、深链、登录。
- 通过代理注入 `X-Forwarded-Proto: https` 且 peer 可信 → `/monitor/transport` 返回 `external_tls_state=tls`、`source=x_forwarded`。
- **TLS 未真实终止**（HTTP 代理 + 头模拟），无证书/真实 TLS 反代；**AC-22 不声称通过**，真实代理/TLS 登记“未实测”。

## 7. 未实测 / PARTIAL 清单

| 项 | 状态 | 原因 |
| --- | --- | --- |
| 跨实例活动节流 | 未实测 | 未单独构造跨实例调用序列；T03 自动化覆盖 |
| 个人中心改密后旧会话 401 | 未实测 | 避免改动种子 admin 凭据；T03 自动化覆盖 |
| 登录/操作日志页、用户管理页真实浏览器 DOM | 未实测 | 无浏览器自动化依赖；前端单测+API 覆盖 |
| 真实浏览器 CSV 下载 | 未实测 | 仅 API 校验 Content-Type/表头 |
| 1280/1920 布局、键盘焦点 | 未实测 | 按约定不新增 Playwright；无截图 |
| 真实 TLS 终止/证书 | 未实测 | 不安装反代工具，仅头模拟 |
| 子路径下受保护 schema 经代理 | 未单独测 | 直连 404 已证明 root_path 不路由；登录/me 已走代理 |
| 模块三观测 | 未集成 | 仓库无模块三表，默认关闭（已知限制） |

## 8. 缺陷清单

| 编号 | 现象 | 修复 | 回归 |
| --- | --- | --- | --- |
| T09-D1 | 前端无 `base`/`basename`，子路径构建资源与路由会 404 | `7c426d0`：Vite `VITE_BASE` + BrowserRouter basename；新增 `basename.test.ts` | 前端 193 通过；子路径构建/代理实测通过 |

无其它代码缺陷；未夹带无关改动。

## 9. 回归与交付状态

```text
后端全量：431 passed
前端全量：193 passed（新增 basename 1 例）
typecheck：通过
build：✓ built
alembic heads：0008 单 head
alembic check：No new upgrade operations detected.
开发库：0004_expected_count_source，未迁移、未写数据
```

注意：`requirements.txt` 当前 SHA-256 为 `6f964878…a78f`，与基线 `728105b…cc74` 不同，原因是按 T08 批准新增 `psutil==7.2.2`；不是未授权漂移，发布检查表已登记。

结论：**PASS（含上表未实测项）**；AC-22 仍为未实测，不在本卡宣称通过。
