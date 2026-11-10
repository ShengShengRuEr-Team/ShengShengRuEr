# 基础作答系统 T04–T09 独立验收记录（2026-11-10）

> 本记录由独立验收人出具，**未修改任何实现**；开发人回填不作为验收依据。
> 代码基线：`ShengShengRuEr-Team/ShengShengRuEr`，分支 `feature/11-attempt-check`，HEAD `f3e21e7`（基于 PR #10 的 T01–T03）。
> 依据：《基础作答系统需求文档》v0.21、《基础作答系统开发文档》v0.13。

## 1. 验收范围与结论

| 任务卡 | 内容 | 结论 |
|---|---|---|
| T04 | 准入判定与内容版本校验 | **PASS**（A1–A10、A2b） |
| T05 | 判分、快照与 249 分练习估分 | **PASS**（A1–A8） |
| T06 | 提交编排与 API-1 | **PASS**（A1–A15；回修后复审通过） |
| T07 | 权限、错误顺序与既有接口回归 | **PASS**（A1–A7） |
| T08 | 自动化测试补全与全量回归 | **PASS**（A1–A10；回修后复审通过） |
| T09 | 端到端验收脚本 | **PARTIAL**（A1/A3/A4/A6/A7/A8 实现完成；A2/A5 与 T10 真实样例 **BLOCKED**） |

## 2. 环境与方法

- Windows x64；Python 3.13.16（`backend/.venv`）；PostgreSQL 18.6。
- 标准 pytest：`TEMP=TMP=D:\pytemp`，普通用户权限；全量 **252 passed**（既有 34 + T01–T09 新增 218）。
- 迁移：单 head `0005_attempt_system`；空库 upgrade → downgrade 0004 → upgrade 通过；`alembic check` 无漂移。
- 开发库 `shengshengruer` 全程未写：`alembic_version=0004_expected_count_source`，16 张表，无 `attempt*` 表。
- 未采信开发回填；T06/T08/T09 经两轮回修与复审。

## 3. 关键验收证据

| 项 | 证据 |
|---|---|
| 准入三条件（当前批次/检查通过/确认可见） | `attempt_content.py` 复用 `student_access`；三状态用例 |
| D-16 版本优先 | 混合身份（旧批次+他卷）→ `version_mismatch` |
| 6a 判空先于 6b | 空 `loaded_question_ids` 在可访问/不可见/不存在三种试卷下均 400 E07 且无永久标记 |
| 判分与估分 | half-up（1/8→13）；249 分权重 7/8/20；24/25 错篇章→235；reason 顺序符合 REV-05 |
| 编排顺序 | 指纹→键锁→四态短路→6a→6b→6b2→6c→6d→判分→单事务 commit；拒绝标记先 commit 再返回 |
| 错误映射 | E03/E04/E05/E06/E07/E08/E09/E14 与 §2.7.1 一致；响应无答案/解析/正文/逐题/内部 ID |
| 日志脱敏 | flush 与 commit 分支 SECRET 注入均不入日志/响应；完整 Idempotency-Key 不落日志 |
| 回归 | 401→403→404 顺序；admin 403 不因目标不存在变 404；既有模块一/二接口交卷前后响应一致 |
| 迁移与开发库 | 见 §2 |

## 4. 非阻断项与后续

1. **T09-A2/A5 与 T10 BLOCKED**：缺受控真实样例（16 表工作簿 + 音频）与真实端到端运行；T09 脚本能力已具备，待 T10 执行后转 PASS。
2. **覆盖表 T09 行状态**：`matrix-coverage-T04-T09.md` §4 中 A3/A4/A5/A7 需标为“实现完成，待 T10 真实执行”；A5 口径为 BLOCKED。
3. **P2 已知限制**：`IntegrityError` 恢复路径会重跑整链并再次尝试插入（唯一约束防重复），与 §2.6.4 伪代码“不盲目再次插入”字面不一致，已登记为已知实现口径，后续按需调整文档或实现。
4. 仓库归档的开发文档副本在本 PR 中同步为 v0.13。
5. M-32/M-41（D-14 需求冲突）保持 BLOCKED；API-2/结果页保持冻结（P1/P6）。

## 5. 结论

T04、T05、T06、T07、T08 全部可复现验收标准 PASS；T09 实现完成但 A2/A5 与 T10 保持 BLOCKED，**不判整体 PASS**。无 FAIL、无红线命中；同意进入 PR2 评审，T10 待真实样例另行验收。
