# T05 业务首页 · 证据记录

| 字段 | 值 |
| --- | --- |
| ac_id | AC-30（完整）、AC-20（缓存部分：miss/hit/TTL/单项/重启/未启用） |
| requirement_ids | ADM-DASH01、ADM-MON05（缓存部分） |
| executor | 开发实施人（lead agent） |
| executed_at | 2026-11-17 14:05—14:25（Asia/Shanghai） |
| commit_sha | 起点 `0e22cc7`；T05 本地提交（不 push） |
| workspace_state | 后端新增首页汇总/缓存；前端首页改造与路由/菜单守卫；1 处菜单测试按新契约更新 |
| environment | Windows；Python 3.13.16；Node 24.14.0；PostgreSQL 本地；测试库 `shengshengruer_test` |
| migration_heads | `0007_admin_audit_events (head)`，T05 零迁移 |
| dependency_versions | 无新增、无升级 |
| result | **PASS** |

## 1 接口与口径

- `GET /api/v1/admin/dashboard`，权限 `admin:dashboard:read`；401/403/500（不返回部分计数）。
- 响应：`as_of / window_start / window_end / timezone / cache / cards`；`cards` 含 6 项。
- 旧 `GET /api/v1/admin/overview` 完全保留（`{role,message}`，200/401/403 不变）。
- `paper_count`：`count(*) exam_papers`（需求 §10.1 原文，无批次限制；同卷多批次不重复）。
- 待确认/失败：当前唯一 `is_current`+`active` 批次的最新检查与最新可见性；无检查不计、二者互斥。
- 学生计数：student 且非 admin，按用户去重。
- `successful_attempts_7d`：北京时间窗口 `[今天00:00-6天, min(明天00:00, as_of))`，只数 attempts 行。
- 不返回学生身份、逐题答案、正确率、分数、个人结果、attempt 列表。

## 2 一致性与缓存

- 独立 `REPEATABLE READ READ ONLY` 事务（第一条语句即 `SET TRANSACTION ...`），`statement_timeout=5000ms`，单条 CTE SQL。
- 进程内缓存：域 `admin_dashboard_summary`/键 `overview`、每进程 1 项、TTL 15 秒（单调时钟）、实例锁单飞、hits/misses 自启动累加、`instance_id` 每进程 UUID。
- 命中时 `as_of` 保持快照时刻；`cached_at/expires_at/age_seconds` 反映读取时刻。
- 关闭开关：`status=not_configured`、每次实时计算、不伪称命中。

## 3 新增测试（16 例）

| 文件 | 用例 |
| --- | --- |
| `tests/test_admin_dashboard_api.py`（9） | 形状/401/403/旧 overview 兼容；与独立 Python 口径对照；同卷两批次不重复；待确认↔失败互斥（缺失/关闭可见性、最新失败）；混合角色不计学生、停用学生计数；attempts 北京时间边界（早 1 秒/下界/窗口内/未来）；响应无个人字段；dashboard 不刷新活动时间；无当前批次时真实 0 |
| `tests/test_admin_dashboard_cache.py`（7） | 首 miss 后 hit 且 as_of 不变；TTL 16 秒（注入单调时钟）→ miss 重建；最多 1 项；新实例重置计数与 instance_id；关闭 → not_configured；失败不缓存（500 后恢复为 miss）；4 线程单飞只重建 1 次 |

## 4 前端

- `/admin` 首页：6 张汇总卡片、`as_of`/窗口/时区、缓存状态徽标与 TTL/年龄、题库入口、「检查通过待确认」卡片跳既有题库列表。
- 状态：loading、空（0 为真实值）、error（错误 + 重试，不显示 0）、stale（刷新失败保留旧数据并标注 `as_of` 可能过期，不自动循环重试）。
- 路由与菜单：`/admin` 首页与「首页」菜单改为 `RequirePermission(admin:dashboard:read)`。
- 新增前端测试 4 例（`HomePage.test.tsx`）：卡片/时间/缓存渲染、错误不显示 0、stale 保留旧数据、not_configured 文案。
- **既有测试 1 处按契约更新**：`AdminLayout.test.tsx` 的「无权限时菜单」断言——「首页」现随 `admin:dashboard:read` 隐藏（与 §4.2/§11.3 一致），其余断言不变。

## 5 测试与门禁

```text
后端全量：368 passed in 111.60s（352 + 16）
后端定向：16 passed in 9.23s
前端全量：175 passed（171 + 4）
typecheck：通过
build：✓ built
alembic current → 0007_admin_audit_events (head)
alembic check → No new upgrade operations detected.
```

证据：`evidence/T05-{backend-pytest,targeted-pytest,frontend-test,frontend-typecheck,frontend-build,alembic-check}.txt`。

## 6 过程中发现并修复

1. 首页测试初期未清缓存，断言读到旧快照 → 测试改为每次对比前 `reset_dashboard_cache()`。
2. 首页「混合角色」用例给临时学生加了 admin 角色且未清理，导致后续 T03「最后管理员保护」用例把唯一管理员停用、连锁 23 个登录失败。修复：用例结束删除临时用户/角色，并给该保护用例加防御性 `status=active` 恢复；全量恢复 368 通过。

## 7 未覆盖项

- 缓存元数据页 `/admin/monitor/cache`、entries、clear 与 `server.audit_storage_health` 指标属 T08。
- 真实双实例/浏览器 E2E 与 1280/1920 走查属 T09。
- 卡片点击仅跳既有题库列表，不执行检查/开放（按文档）。

## 8 结论

**PASS**。首页汇总、一致快照、真实 TTL 缓存、旧 overview 兼容与前端四态按 §9.5/§10.1 实现；后端 368、前端 175 全绿，零迁移且无漂移。
