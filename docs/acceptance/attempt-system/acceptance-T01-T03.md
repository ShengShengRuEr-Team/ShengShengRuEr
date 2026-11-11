# 基础作答系统 T01–T03 独立验收记录（2026-11-10）

> 本记录由独立验收人出具，**未修改任何实现**；开发人回填结论不作为验收依据。
> 代码基线：仓库 `ShengShengRuEr-Team/ShengShengRuEr`，分支 `feature/9-attempt-system`，HEAD `a868fd7`（基于 `develop @ b965a0f`，4 个提交）。
> 依据：《基础作答系统需求文档》v0.21、《基础作答系统开发文档》v0.12（验收时对应 v0.11 + 本记录引用的命名表补列）。

## 1. 验收范围

| 任务卡 | 内容 | 对应提交 |
|---|---|---|
| T01 | 数据模型（attempts / attempt_answers / attempt_rejections）与 Alembic 0005 迁移 | `6070546`、`cabb768` |
| T02 | API-1 请求/响应契约、幂等键校验与统一 msg 常量 | `9fe14cd` |
| T03 | 幂等仓储、四态短路、永久拒绝标记、两把 advisory lock、请求指纹 | `a868fd7` |

## 2. 环境与方法

- 操作系统 Windows x64；Python 3.13.16（`backend/.venv`）；PostgreSQL 18.6 本地服务。
- 临时目录：`D:\pytemp`；普通权限运行，未提权（服务启动除外）。
- 迁移往返使用独立临时库，验证后删除；不触碰开发库 `shengshengruer`。
- 开发人回填、日志、脚本结论一律不采信；验收人自行执行命令与脚本复算。

## 3. 结果汇总

| 验收项 | 结论 | 关键证据 |
|---|---|---|
| T01-A1 单 head | PASS | `alembic heads` → 仅 `0005_attempt_system (head)` |
| T01-A2 空库升级 + 三表列/约束/索引与 §2.3 一致 | PASS | 19 表；逐项 diff `unexplained=0`；命名表漏列项见 §4 |
| T01-A3 downgrade 0004 再 upgrade | PASS | 16 表 ↔ 19 表；attempt 对象全消失/恢复 |
| T01-A4 0001–0004 未改 + 既有测试全绿 | PASS | 迁移 diff 为空；既有 34/34 通过 |
| T01-A5 约束实际生效 | PASS | 唯一冲突、CHECK、FK RESTRICT、CASCADE 均按预期拒绝 |
| T01-A6 `alembic check` | PASS | `No new upgrade operations detected.` |
| T02-A1–A6 契约/严格性/幂等键/响应无泄露 | PASS | 60 条模型级用例；响应字段集合无答案/解析/正文/逐题/内部 ID |
| T03-A1–A7 回放/冲突/拒绝/并发/指纹/锁 | PASS | 真实 advisory lock 等待、同键并发仅 1 条、指纹跨进程复算一致 |
| 全量 pytest | PASS | **140 passed, 1 warning**（既有 34 + 新增 106；0 failed/skipped/error） |
| 开发库状态 | PASS | 仍 `0004_expected_count_source`、16 表、无 `attempt*` 表 |
| 临时库清理 | PASS | `pg_database` 仅剩 `shengshengruer`、`shengshengruer_test` |

## 4. 非阻断项与处理

1. **文档命名表漏列**：§2.3.2/2.3.3/2.3.4 的"约束与索引"表未列 9 个已实现对象（1 UNIQUE、3 CHECK、5 FK）。实现正确，属文档遗漏；已在开发文档 v0.12 补列（E.13）。
2. **`submitted_at` 序列化**：文档示例 `+00:00`，Pydantic 实际输出 `Z`；二者均为 UTC ISO 8601，等价。已在 v0.12 统一说明。
3. **幂等键大小写**：文档未限制大小写，实现接受大写十六进制；已在 v0.12 明确。
4. **环境注记**：验收时标准 `pytest` 命令在 DSH 沙箱内无法原样启动（临时目录在工作区外），验收组仅调整临时路径复现 140 passed；未改源码/测试/断言。开发人本机普通终端已以标准命令复跑 140 passed。
5. **T06 待验**：HTTP 链路的并发/异常顺序（T06-A9/A10）不在 T01–T03 范围，留待 T06 验收。

## 5. 结论

**T01、T02、T03 全部可复现验收标准 PASS，无 FAIL / PARTIAL / BLOCKED，同意进入 PR 评审。**
工作区保持干净，未 push、未合并；合并由项目负责人执行。
