# T04 日志 / 导出 / 共用 UI · 证据记录

| 字段 | 值 |
| --- | --- |
| ac_id | AC-12、AC-28（前端权限）、AC-29（枚举生成）、AC-31、AC-32、AC-33（共用 UI 与错误态） |
| requirement_ids | ADM-LOG01、ADM-LOG02、ADM-PERM01、ADM-ENUM01、ADM-EXP01、ADM-UI01 |
| executor | 开发实施人（lead agent） |
| executed_at | 2026-11-17 12:50—13:20（Asia/Shanghai） |
| commit_sha | 起点 `ae6d206`；T04 分三次本地提交（日志 `d0c7332`、导出 `20d0ead`、共用 UI/枚举随本记录提交） |
| workspace_state | 后端新增日志/导出/生成器与测试；前端新增日志页、权限组件、rawClient、生成物，修改 AuthContext/路由/布局 |
| environment | Windows；Python 3.13.16；Node 24.14.0；PostgreSQL 本地；测试库 `shengshengruer_test` |
| migration_heads | `0007_admin_audit_events (head)`，T04 零迁移 |
| dependency_versions | 无新增、无升级 |
| result | **PASS** |

## 1 交付清单

### 1.1 后端

| 文件 | 说明 |
| --- | --- |
| `app/core/admin_enums.py` | 枚举与标签唯一来源；`audit.py` 继续导出同名 `EVENT_*` 常量 |
| `app/schemas_admin/logs.py`、`repositories/admin/logs.py`、`services/admin/logs.py`、`api/admin_platform/logs.py` | 登录/操作日志列表与详情、时间窗、DTO 白名单 |
| `app/repositories/admin/exports.py`、`services/admin/exports.py`、`api/admin_platform/exports.py` | 三类 CSV、分批 deadline、限制与事件 |
| `app/api/deps.py` | `require_permissions(*codes)`（缺任一 403，顺序不变） |
| `scripts/generate_admin_constants.py` | 枚举/权限 → TS 常量，支持 `--check` |
| `tests/test_admin_logs_api.py`、`test_admin_exports_api.py`、`test_admin_constants.py` | 7 + 10 + 5 例 |

### 1.2 前端

| 文件 | 说明 |
| --- | --- |
| `api/rawClient.ts` | 原始响应通道（JSON schema / CSV blob），复用 401/403/token 规则 |
| `api/admin/{types,logs,exports}.ts` | 日志 DTO、列表/详情、CSV 下载与错误体解析 |
| `auth/usePermission.ts`、`ui/Can.tsx`、`router/RequirePermission.tsx` | 按 `getInfo.permissions` 显隐与页面守卫 |
| `auth/AuthContext.tsx`、`auth/AuthRecovery.tsx`、`router/RequireAuth.tsx` | `recovery-error`：500/网络保留 token、零权限、可重试；仅 401 清 token |
| `pages/admin/{LoginLogsPage,OperationLogsPage,logs/LogsView}.tsx`、`ui/admin/LogDetailDrawer.tsx` | 两个日志页（筛选/分页/详情/CSV/空错态） |
| `generated/adminConstants.ts` | 生成物入库 |
| `layouts/AdminLayout.tsx`、`router/index.tsx`、`constants/routes.ts` | 菜单按权限过滤、两条日志路由 |
| 测试：`rawClient.test.ts`、`Can.test.tsx`、`AuthContext.recovery.test.tsx`、`LoginLogsPage.test.tsx`、`adminConstants.test.ts` | 19 例 |

## 2 日志（真实输出）

- 列表 `GET /api/v1/admin/logs/login|operation`：默认北京时间 7 天窗口、单端 422、反向 422、>90 天 422、无时区 422、非法枚举/IP 422、详情 404、UUID 非法 422。
- DTO 只含白名单字段；`summary` 读取侧二次过滤；`user_agent_summary` 80 字符；无 jti/token/UA 原文。
- 顺序：无 token 401 → 学生 403 → 管理员 200/422。

## 3 导出（真实输出）

- 三类 CSV：中文表头、UTF-8 BOM、CRLF、`+08:00`、附件头 `no-store`/`nosniff`。
- 公式前缀（`= + - @`、TAB/CR/LF 起始）前置单引号，库值不变。
- 忽略 `page/page_size`；筛选与列表一致；0 行仅表头。
- 5001 行 → 400（`EXPORT_FAILED` `stage=limit_rows`）；4000 行 × 1.5KB 摘要 → 5MiB 上限 400（`limit_bytes`）。
- 15 秒 deadline：替换单调时钟命中 → 500（`stage=timeout`），不截断。
- 成功事件 `EXPORT_COMPLETED`：`export_type/row_count/byte_size` 独立事务；审计失败 → 500 且响应非 CSV（`stage=audit`）。
- 双权限：缺 `admin:export:*` 或缺 `admin:user:read`/`admin:log:read` 均 403。

## 4 枚举与前端

```text
$ python scripts/generate_admin_constants.py --check
管理端常量与后端枚举一致。
$ pytest tests/test_admin_constants.py → 5 passed
$ npm test -- --run → Test Files 23 passed (23) / Tests 148 passed (148)
$ npm run typecheck → 通过
$ npm run build → ✓ built
```

- 生成器改值后 `--check` 返回非零（单测覆盖）；生成物入库。
- 权限组件：`Can` 无权限不渲染；`RequirePermission` 进 403；菜单按权限过滤。
- `AuthContext`：500/网络 → `recovery-error`、token 保留、权限 0；重试成功恢复；401 清 token。

## 5 回归

```text
后端全量 352 passed（T03 330 + 22）
定向 22 passed（日志 7、导出 10、枚举 5）
前端 148 passed（既有 129 + 新增 19），typecheck/build 通过
alembic current → 0007_admin_audit_events (head)
alembic check → No new upgrade operations detected.
```

证据文件：`evidence/T04-{backend-pytest,targeted-pytest,constants-check,frontend-test,frontend-typecheck,frontend-build,alembic-check}.txt`。

## 6 未覆盖项

- 私有 API 文档与 GET 调试、Swagger 本地资源：T06。
- 首页统计与缓存：T05；留存调度：T07；监控/TLS/OAuth：T08；双实例与回退演练：T09。
- 前端导出交互的真实浏览器下载（E2E）留 T09；本轮以单测证明「失败不下载、成功才保存」。
- 用户管理与个人中心页面（`/admin/users`、`/admin/profile`）归属 **T03-FE**，不在 T04 卡片范围内；本卡只交付日志页与共用 UI（其余结论不变）。

## 7 结论

**PASS**。日志查询、三类 CSV、枚举生成与共用 UI 按 §7.3/§11.1—§11.4 实现；后端 352、前端 148 全绿，类型检查与构建通过，零迁移无漂移。
