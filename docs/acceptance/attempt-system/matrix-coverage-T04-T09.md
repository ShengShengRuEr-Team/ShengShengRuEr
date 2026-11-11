# 作答系统 T04–T09 验收矩阵覆盖表

- 仓库/分支：`ShengShengRuEr-Team/ShengShengRuEr` · `feature/11-attempt-check`
- 基线提交：T09 提交 `953dbf9`（后续 T06/T08/T09 回修另列）
- 编制时间：2026-11-10
- 环境：Windows / Python 3.13.16 / PostgreSQL；pytest 全量使用独立测试库 `shengshengruer_test`
- 说明：本表是**自动化覆盖台账**，不替代验收人签署；`PASS（自动）` 仅代表对应用例在该环境通过；
  `BLOCKED` 表示口径/冻结/数据前置未满足，**不得记为 PASS**。

## 1. T04–T09 开发自测状态（待验收人复核，不代表验收结论）

> 本节由开发人填写，只记录自动化自测状态，**不构成验收结论**；最终判定由验收人按第 6 节回填。

| 任务 | 开发自测状态（待验收） | 说明 |
|---|---|---|
| T04 准入判定与内容版本校验 | 开发自测通过（待验收） | 仓储级 25 条用例；A1–A10/A2b 全绿 |
| T05 判分、快照与 249 分练习估分 | 开发自测通过（待验收） | 表驱动 27 条用例；A1–A8 全绿 |
| T06 提交编排与 API-1 | 回修后待复核（待验收） | 回修项：6a 空 `loaded_question_ids` 前置判空、flush/commit 分支日志注入、完整键不落日志 |
| T07 权限、错误顺序与既有接口回归 | 开发自测通过（待验收） | 8 条回归用例 |
| T08 自动化测试补全与全量回归 | 回修后待复核（待验收） | 回修项：矩阵覆盖表落库、M‑24 HTTP 集成用例、6.3a 自测记录 |
| T09 端到端验收脚本 | 回修后待复核；真实样例仍 BLOCKED（待验收） | 回修项：预期/运行期 BLOCKED 区分、退出码 0/1/2/3、顶层 try/finally、5xx 原键重试、恢复失败定位信息、inject 参数约束 |

## 2. 矩阵覆盖（M 编号 → 用例 → 结果）

> 用例文件前缀：`api` = `backend/tests/test_attempt_api.py`，`reg` = `test_attempt_regression.py`，
> `grading` = `test_attempt_grading.py`，`content` = `test_attempt_content.py`，
> `keys` = `test_attempt_keys.py`，`models` = `test_attempt_models.py`，`schemas` = `test_attempt_schemas.py`，
> `module2` = `test_module2_listening.py` / `test_module2_recheck.py`，`security` = `test_security_edges.py`，
> `acceptance` = `test_acceptance.py`。

| 矩阵号 | 来源 | 用例 | 结果 |
|---|---|---|---|
| M‑01 | V‑01/AS‑01 | `api::test_m01_24_of_25_lecture_wrong_exact_values`（24/25→96/235、breakdown 7/8/10、库内 1 attempt/25 answers） | PASS（自动） |
| M‑02 | V‑02/AS‑02 | `api::test_a2_partial_and_empty_answers`（独立试卷：部分作答、空 answers；分母 25；NULL 可区分） | PASS（自动） |
| M‑03a | V‑03/AS‑03 | `api::test_m03a_reordered_options_grade_in_paper_space`（原卷字母判分 + 库内快照） + `grading::test_a4_*` | PASS（自动） |
| M‑03b | V‑03 回显 | 无 API‑2，本轮不可观测 | **BLOCKED（FZ1/FZ2）** |
| M‑04 | V‑04/BR‑16/16a | `api::test_a1_full_submission`（25/25→100/249）、`api::test_a2_*`（0/25→0）、`api::test_m01_24_of_25_lecture_wrong_exact_values`（24/25→96/235）、`api::test_m04_practice_unavailable_reasons`（1 题/题型缺失/类型数量不符→available=false、value=null、reason） + `grading` 全套 | PASS（自动） |
| M‑05 | V‑06/AS‑06 | `api::test_a3_same_key_replay_returns_same_attempt` | PASS（自动） |
| M‑06 | V‑07a/EX‑09a | `api::test_m06_new_batch_loaded_before_submit`（双批次，按新批提交 200、`import_batch_id`=新批） | PASS（自动） |
| M‑07 | V‑12 读取部分/AS‑12 | 无 API‑2 路由 | **BLOCKED（P1/FZ1）** |
| M‑08 | V‑16/AS‑16 | `reg::test_a2_auth_order_before_resource_lookup`；`api::test_a8_role_and_auth_order` | PASS（自动） |
| M‑09 | V‑17/AS‑17 | `reg::test_a1_api1_role_matrix`、`reg::test_a2_*`（管理员 403 不 404） | PASS（自动） |
| M‑10 | V‑18/AS‑18 | `reg::test_a3_student_detail_unchanged_before_and_after_attempt` | PASS（自动） |
| M‑11 | V‑19a/AS‑19a | `api::test_m11_annotation_state_change_does_not_affect_access` | PASS（自动） |
| M‑12 | V‑20a/AS‑20a | `api::test_m12_records_survive_visibility_cancel`（先成功提交→再取消可见→只读 SQL 断言 attempts/attempt_answers 仍在、未被级联删除） | PASS（自动，SQL 核验） |
| M‑12a | AS‑14/BR‑23 提交侧 | `api::test_m12a_snapshot_does_not_drift`（改题库后 `attempt_answers` 快照逐行不变） | PASS（自动，SQL 核验） |
| M‑13 | V‑01a/D11/BR‑18a | `api::test_a5_same_paper_new_key_is_limited` | PASS（自动）；**用例仅断言 attempt 数，markers==0 未断言（WARN）** |
| M‑14 | V‑R7/BR‑27 | `api::test_m14_submitted_at_is_utc`（响应 ISO 8601 UTC、库内 UTC） | PASS（自动） |
| M‑15 | V‑R6/BR‑26 | 独立临时库 `upgrade head → downgrade 0004 → upgrade head` + `alembic check`（命令证据：见本次验收回执“迁移往返命令输出”；临时库 `shengshengruer_t01_verify` 已删除） | PASS（命令） |
| M‑16 | V‑R1/BR‑11 | `reg::test_a2_auth_order_before_resource_lookup` | PASS（自动） |
| M‑17 | V‑R2/BR‑04/06 | `reg::test_a3_student_detail_unchanged_*`（字段/全文断言） | PASS（自动） |
| M‑18 | V‑R3 | `reg::test_a4_audio_range_and_unavailable`（200/206/404）+ `reg::test_m18_audio_range_out_of_bounds_416`（416） | PASS（自动） |
| M‑19 | V‑R4 | `reg::test_a5_admin_endpoints_permissions` | PASS（自动） |
| M‑20 | V‑R5 | `reg::test_module1_auth_regression` + 既有模块二/安全用例 | PASS（自动） |
| M‑21 | V‑07/AS‑07 | `api::test_a6_invisible_paper_writes_marker_and_blocks_old_key` | PASS（自动） |
| M‑21a | AS‑07/E03 | `api::test_a13_missing_paper_404_with_marker` | PASS（自动） |
| M‑22 | V‑07b/EX‑09b | `api::test_a7_old_batch_writes_version_marker` | PASS（自动） |
| M‑23 | V‑08/AS‑08 | `api::test_a9_*`（4 支）+ `api::test_m34_pre_commit_failure_retry_succeeds` | PASS（自动） |
| M‑23a | R7‑05/2.7.3 | `api::test_a15_*`（flush/rollback/re读）、`api::test_t06_a15_commit_failure_logs_are_safe`（commit）、`reg::test_a7_db_error_keeps_shell_and_logs_are_safe` | PASS（自动） |
| M‑24 | EX‑16/AS‑01 | `api::test_a12_path_range_and_body_types`、`api::test_a12_body_contract_errors`、`api::test_m24_http_validation_matrix`（路径 0/-1/2^63→422；JSON "1"/1.0/true→422；缺 answers→422；`selected_option="E"/"a"`→422；同一 Idempotency-Key 修正后重试→200 且首次 422 不落库） | PASS（自动） |
| M‑25 | EX‑17/5.5a | `api::test_m25_identity_variants`（不存在/重复 loaded→400 E07 无标记）、`api::test_a13_foreign_identity_400_without_marker` | PASS（自动） |
| M‑26 | EX‑18 | `api::test_a12_body_contract_errors`（缺 answers→422） | PASS（自动） |
| M‑27 | EX‑19 | `api::test_m27_duplicate_answer_question_id`（400 E07） | PASS（自动） |
| M‑28 | EX‑20/D‑02 | `api::test_a12_idempotency_key_errors`（缺席/非法→400 E05） | PASS（自动） |
| M‑29 | EX‑12a | `api::test_m29_content_check_not_passed`（404 + access 标记） | PASS（自动） |
| M‑29a | EX‑28/BR‑01 | `api::test_a13_mapping_invalid_404_without_marker` | PASS（自动） |
| M‑29b | EX‑28/BR‑01 | `api::test_a13_audio_missing_404_without_marker` | PASS（自动） |
| M‑29c | EX‑28/REV‑03 | `api::test_m29c_deleted_last_question_api` | PASS（自动） |
| M‑30 | EX‑13a/AS‑19a | `api::test_m11_annotation_state_change_does_not_affect_access` | PASS（自动） |
| M‑31 | V‑22/EX‑24 | `api::test_a10_concurrent_same_key_single_attempt`（两线程同键：均 200、同一 code、1 条） | PASS（自动） |
| M‑32 | V‑21/EX‑23 | 不同键并发“两条独立记录”与 BR‑18a 冲突未决 | **BLOCKED（D‑14）** |
| M‑33 | V‑23/EX‑25 | `api::test_m33_submit_before_visibility_change_succeeds`、`api::test_m33_visibility_change_before_submit_rejects`（Event 钩子固定两顺序） | PASS（自动） |
| M‑34 | EX‑26/AS‑08 | `api::test_m34_pre_commit_failure_retry_succeeds` | PASS（自动） |
| M‑35 | V‑05/AS‑05 | P1 生效后多次作答 | **冻结（P1）→ BLOCKED** |
| M‑36 | E09/BR‑19b | `api::test_a4_key_conflict_and_limit` | PASS（自动） |
| M‑37 | 5.5a | `api::test_m37_subset_loaded_incomplete`（400 E07） | PASS（自动） |
| M‑38 | 5.5a | `api::test_m38_shuffled_loaded_allowed`（200） | PASS（自动） |
| M‑39/M‑40 | V‑E1/V‑E5a | 真实专用样例端到端 | **BLOCKED（T10 未执行）** |
| M‑41 | V‑E4 | 同卷再次作答两条记录 | **BLOCKED（D‑14）** |
| M‑42 | V‑E2/E3/E5b | 结果读取/管理员读取 | **BLOCKED（P1/P6，FZ1）** |
| M‑43 | V‑09–V‑15a | 结果读取相关 | **BLOCKED（P1/P6，FZ1）** |
| M‑44 | V‑15b/BR‑08/T11 | 解析正文检测 | **BLOCKED（T11/FZ4）** |
| M‑45 | V‑19b | 标注审核变化不影响读取（读取侧） | **BLOCKED（P1/FZ1）** |
| M‑46 | V‑20b | 下线期间读结果 404（读取侧） | **BLOCKED（P1/FZ1）** |
| M‑47 | V‑05 完整口径 / V‑E4 多条部分 | P1 生效后的多次作答 | **BLOCKED（P1 + D‑14）** |
| M‑47a | M‑32 / V‑21 / EX‑23 | 不同键并发“两条独立记录”与 BR‑18a 冲突 | **BLOCKED（D‑14 需求冲突未修订）** |
| M‑47b | M‑41 / V‑E4 多条部分 | 同卷再次作答产生两条记录 | **BLOCKED（D‑14 需求冲突未修订）** |
| M‑48 | EX‑27、EX‑29–EX‑32 | 读取侧快照/换批/外部删除/字段缺失 | **BLOCKED（P1/FZ1）** |

## 3. T06‑A14 实现自测（§6.3a，单列，不计矩阵通过率）

| 自测项 | 口径状态 | 命令/实际结果 | 证据 | 决策边界 |
|---|---|---|---|---|
| 同学生同卷不同键并发限次 | D11=A、BR‑18a 默认口径，**D11/D‑14 仍未确认** | `pytest -k "a10 or a14 or m33"` 连续 10 次，10/10 exit=0；单次 `-v`：5 passed | 两独立会话 + 同步钩子：响应 200 与 400 E08、仅 1 条完整 attempt、无标记；负向对照（移除限次锁）出现 2 条 | 仅技术自测；**M‑32/M‑41 仍 BLOCKED**，不得据此宣判 V‑21/V‑E4 通过 |

## 4. T09 脚本覆盖（可自动部分）

| T09 验收 | 脚本行为 | 状态 |
|---|---|---|
| A1 | `--base-url` 必填；缺参数/服务不可达/样例已消耗→exit 2；不自动挑卷 | PASS（脚本实现；本轮局部命令验证） |
| A2 | 真实服务提交 200、契约校验、只读 DB attempts/answers 行数 | 受控测试库已跑通；真实专用样例 **BLOCKED（T10）** |
| A3 | 同键回放同一 code；不同键 E08；库内不新增 | 实现完成，待 T10 真实执行（不判 PASS） |
| A4 | 管理员 403、未认证 401 | 实现完成，待 T10 真实执行（不判 PASS） |
| A5 | 独立样例；已消耗（attempts/markers>0）→exit 2 | **BLOCKED**（实现完成，待 T10 真实样例执行；不得写 PASS） |
| A6 | 每项证据 + 写入资源清单；键掩码 | PASS（实现） |
| A7 | 可见性场景 finally 恢复；恢复失败明确 FAIL；中断注入 | 实现完成，待 T10 真实执行（受控自测仅证明脚本行为，不判 PASS） |
| A8 | 输出永久记录不删除说明；所有退出路径均打印资源清单 | PASS（实现） |
| BLOCKED | V‑E4、V‑E5b、V‑E2/E3、人工判分抽查、T10 真实样例 | **BLOCKED** |

## 5. 本轮回修记录（T06/T08/T09）

1. **T06**：`_first_submit` 在 6b 准入前判空 `loaded_question_ids` → 400 E07（无标记）；
   新增“不可见/不存在 + 空集合”“可访问 + 空集合”用例；A15 日志注入**两条分支均已覆盖**：
   - flush 分支：`api::test_t06_a15_flush_failure_logs_are_safe`（`Session.flush` 抛含 `SECRET_FLUSH_XYZ` 的
     `OperationalError`，断言 500 外壳/无 SECRET/完整键不落日志/0 行/stage+error_type）；
   - commit 分支：`api::test_t06_a15_commit_failure_logs_are_safe`（`Session.commit` 注入 `SECRET_COMMIT_XYZ`）。
2. **T08**：本文件落库（M 编号→用例→结果→BLOCKED）；新增 `test_m24_http_validation_matrix`
   覆盖路径/JSON 类型/缺失 answers/非法字母的 HTTP 422，并验证同一 Idempotency-Key 修正后重试→200；
   M‑12 改由 `test_m12_records_survive_visibility_cancel` 只读 SQL 覆盖；6.3a 自测见第 3 节。
3. **T09**：区分“预期冻结 BLOCKED”（仅 `[EXPECTED-BLOCKED]` 打印、不计数）与“运行期 BLOCKED”
   （exit 3）；正常收尾 exit 0；`--base-url` 必填；顶层 try/finally 保证任何未捕获异常也打印写入资源
   说明；DB 连接异常按前置失败 exit 2；首提交超时/连接断/5xx 均按 §2.6.4 原键重试一次并打印掩码键；
   可见性取消/恢复、拒绝标记与恢复后新键 attempt 计入 WRITES；恢复失败输出 paper_id/原状态/当前遗留
   状态与人工恢复提示；`--inject-*` 必须与 `--check-visibility` 同时提供。

## 6. 复现命令

```powershell
cd backend
python -m pytest -v                      # 全量（测试库 shengshengruer_test）
python -m pytest -v -k "m01 or m03a or m04 or m06 or m11 or m12a or m14"
python -m pytest -v -k "m24 or m25 or m27 or m29 or m33 or m34 or m37 or m38"
python -m pytest -v tests/test_attempt_regression.py
python -m scripts.acceptance_attempt --help   # 退出码/参数说明
```

> 注意：T09 脚本真实运行须由 T10 提供专用可访问试卷/学生并显式传参；`--database-url`
> 仅允许测试库/独立库，库名为 `shengshengruer` 时直接 exit 2。
