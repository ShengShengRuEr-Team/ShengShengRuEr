# 作答系统验收矩阵（AC-01–AC-50 / B-01–B-16 / R-01–R-08 / E2E 1–20）

> 日期：2026-11-16  
> 代码：`D:\ssre_V1\ShengShengRuEr`，分支 `main@846270b`（含本任务未提交改动）  
> 需求 V1.2 / 开发 V1.1 / 原型图集 V1.1  
> 判定口径：**PASS**＝按步骤可复现且符合预期；**PARTIAL**＝核心逻辑有自动化证据，但缺少规定的真实场景/组合证据（不等同 FAIL，需验收负责人裁定接受或补测）；**FAIL**＝可复现不符；**BLOCKED**＝环境/依赖/签字缺失，无法判定。  
> 证据简称：`pytest`＝`backend/tests`（265 passed）；`U`＝`frontend/src/attempt/*.test.ts`；`C`＝`frontend/src/pages/student/attempt/*.test.tsx`；`P`＝`ListeningPaperPage*.test.tsx`；`E2E`＝真实 Edge 浏览器脚本（11 项）；`API-E2E`＝真实服务脚本（23 项）。

## 1. 功能与异常（AC-01–AC-50）

| 编号 | 结果 | 证据 | 说明 |
| --- | --- | --- | --- |
| AC-01 | PASS | C-01；E2E | 整行点选、清除、方向键、计数；`aria-checked` + 勾选图标 |
| AC-02 | PASS | C-02 | 按篇分组、已答/未答/标记/当前、点击题号回调（跳篇+滚动） |
| AC-03 | PASS | C-01；E2E | 标记/取消标记写草稿、答题卡显示、确认框标记数一致 |
| AC-04 | PASS | E2E | 刷新后答案/标记/当前篇恢复；播放器组件从 0 秒重建 |
| AC-05 | PASS | E2E（多标签 B 刷新）；P | 关闭标签再进入与刷新走同一恢复路径；B 标签重载后只读 |
| AC-06 | PASS | U storage | 键含 userId+examPaperId，A/B 用户互不可见 |
| AC-07 | PASS | U codec/storage | 过期/损坏普通草稿删除不崩溃；损坏信封不被删除 |
| AC-08 | PARTIAL | U payload/codec；页面 stale 分支 | 题目集合不一致不恢复旧答案、显示 stale 提示；缺页面级组合测试 |
| AC-09 | PASS | C-03 | 总/已答/未答/标记、仅一次、取消不提交、全未答强提示 |
| AC-10 | PASS | U payload | 全部 loaded IDs 按详情顺序；已答按题目顺序；大写；无重复 |
| AC-11 | PASS | P「双击确认只发送一次」；pytest 并发/唯一约束 | 提交中确认框按钮禁用 + `inFlightRef`；`fireEvent` 连续两次只发 1 次请求；后端唯一约束兜底 |
| AC-12 | PASS | U submit；API-E2E 幂等回放；pytest | 500/网络保留信封并置 unknown；同键同 payload 返回同一 attempt_code |
| AC-13 | PARTIAL | U errors；client 401 代码；P「登录失效」分支 | 未做真实提交中 401 回跳浏览器场景 |
| AC-14 | PASS | pytest 404；U errors；P「API-1 404 E03」 | 先按 frozenPayload 重建草稿并读回成功，才清旧信封、保留答案；与 API-3 404 分流 |
| AC-15 | PARTIAL | pytest E04；U errors；页面 reload-clear 分支 | 页面换批（E04）后清答案/信封并重载未做真实浏览器场景 |
| AC-16 | PASS | pytest E08；P「E08」 | 写 `source=e08, summary=null, submittedAt=null` 标记 → 只读；随后 API-3 查询补全汇总（source 收敛为 api3） |
| AC-17 | PASS | pytest E09；P「E09 false」 | true 结束；false 清信封回可作答（下次新键）；查询失败保留信封冻结 |
| AC-18 | PASS | E2E；C-05 | 正确数/率/估分/时间/编号；无逐题、无未答数 |
| AC-19 | PASS | E2E；API-E2E | API-3 false 后正常作答 |
| AC-20 | PASS | E2E；API-E2E | API-3 true 只读汇总，不白答 |
| AC-21 | PASS | API-E2E；pytest | 401/403（管理员）/404（不可访问）顺序与不泄露 |
| AC-22 | PASS | API-E2E；pytest | 字段白名单；true latest 非空且与 API-1 完全一致；false null |
| AC-23 | PASS | E2E | 已提交再进入：只读/汇总/播放器/中性导航 |
| AC-24 | PASS | `evidence/` | pytest 265 passed、`npm test` 117 passed、typecheck/build 通过 |
| AC-25 | PASS | 本文档集；README/需求同步 | 旧文案清理（“后续开放/查看听力”移除）、无首页继续卡片；文档在 QA-03 关闭前完成 |
| AC-26 | PASS | E2E `e2e-07-1280.png`、`e2e-08-1024.png` | 1280 右侧 sticky 答题卡；1024 顶部折叠答题卡；两档提交栏均可见 |
| AC-27 | PASS | E2E；API-E2E；pytest | 详情/API-3/页面均无答案/解析/正文；E2E 扫描 DOM 无受保护字段 |
| AC-28 | PASS | C-07；U storage；pytest | 信封不参与 TTL/10 份淘汰；pending 无“重新开始”；强警告清除 |
| AC-29 | PARTIAL | U retention/submit；页面自动重试分支 | 流程 P-03 未确认 → 策略固定 unknown、自动重试关闭；`days/permanent` 仅单测 |
| AC-30 | PASS | P「404 标记」「500 标记」；C-07 | 404 不展示汇总；500/网络展示本机标记并标注“本机保存，仅供参考”；普通可答、pending 冻结 |
| AC-31 | PASS | C-03；pytest `test_a2_partial_and_empty_answers` | 全部未答强提示、允许提交、0% 判分 |
| AC-32 | PASS | C-05；E2E | 估分不可用显示“暂不可用”（含 reason），不显示 0 |
| AC-33 | PARTIAL | 页面 `versionNotice` 代码；U adapters | 已提交换批的版本提示未做真实换批场景 |
| AC-34 | PASS | P「未知 400」；U errors | 未知 400 保留信封、冻结编辑、不自动新键、不出现“提交失败请重新作答” |
| AC-35 | PARTIAL | U rebuild；pytest E04/版本 | pending + 内容变化的 true/false/失败三种页面组合未逐一覆盖 |
| AC-36 | PASS | P「存储不可用」 | 内存信封 + 发送前确认；未确认不发送；无崩溃 |
| AC-37 | PASS | U storage；E2E 多标签 | 普通保存不覆盖/删除信封；B 标签保存不影响 A 信封 |
| AC-38 | PARTIAL | P「storage 事件」「写入前检查」；E2E 多标签 | 已覆盖：B 已保存草稿时 A 成功→B 冻结；事件未处理时写入前检查兜底。未逐一模拟“后台挂起/即将关闭”两态 |
| AC-39 | PASS | U retention | unknown/超期不自动重试；手动同键 + 强警告；不自动新键 |
| AC-40 | PASS | U adapters；P「true 坏汇总」 | 确定已提交但汇总不可用：只读、可重查、与冲突分开 |
| AC-41 | PASS | P「404 + 标记」 | 404 不展示汇总、不提供重开、只读提示 |
| AC-42 | PASS | U storage；P「E08」 | 标记 30 天 TTL；API-3 false 删除；E08 无汇总仍显示已提交 |
| AC-43 | PASS | pytest `test_status_uses_single_window_statement`、`test_status_concurrent_with_submit_is_consistent`；API-E2E | 实测只发 1 条 `FROM attempts` SQL，含 `count(*) OVER` 与 `LIMIT`；并发提交窗口 count/latest 一致 |
| AC-44 | PASS | E2E | 已提交无选中/标记/进度；刷新前后一致 |
| AC-45 | PASS | API-E2E；pytest 模块二 | API-1/3 管理员 403；模块二学生视角按原规则 |
| AC-46 | PASS | U codec/storage；P「信封损坏」 | 坏 JSON/缺 key/非法 payload/未知版本 → `pending-unrecoverable`；仅查询/强警告清除；不自动删/重发 |
| AC-47 | PASS | U adapters；P「矛盾响应」 | 四类矛盾保护性冻结；不清理草稿/信封/标记、不写新事实、不生成新键 |
| AC-48 | PASS | pytest Schema 不变量；U adapters | 前后端均校验 `submitted === (count>0)`、true→count≥1、false→count=0/latest=null、嵌套试卷 ID |
| AC-49 | PASS | U storage/adapters；C-05；P | `submittedAt=null` 合法；页面不显示伪造时间、不回编辑 |
| AC-50 | PASS | U submit；P「API-1 404 E03」 | 只留信封时先重建并读回成功才清信封；不兼容/写入失败保留信封冻结；E04 例外 |

## 2. 后端 API-3 用例（B-01–B-16）

| 编号 | 结果 | 证据（pytest 用例） |
| --- | --- | --- |
| B-01 | PASS | `test_status_missing_token_401` |
| B-02 | PASS | `test_status_admin_403` |
| B-03 | PASS | `test_status_hidden_404`、`test_status_missing_paper_404` |
| B-04 | PASS | `test_status_false_without_submission` |
| B-05 | PASS | `test_status_true_matches_api1_summary`（与 API-1 汇总逐字段相等） |
| B-06 | PASS | `test_status_is_student_scoped`；API-E2E「学生隔离」 |
| B-07 | PASS | `test_status_field_whitelist`；API-E2E 字段白名单/无受保护字段 |
| B-08 | PASS | `test_status_does_not_write`（查询前后三表行数不变） |
| B-09 | PASS | `test_status_offline_then_restore`（下线 404） |
| B-10 | PASS | 同上（恢复 200 且汇总恢复） |
| B-11 | PASS | `test_status_true_matches_api1_summary` |
| B-12 | PASS | `test_status_false_without_submission` |
| B-13 | PASS | `test_status_concurrent_with_submit_is_consistent`；`test_status_uses_single_window_statement` |
| B-14 | PASS | 成功与 404 均断言 `Cache-Control: no-store` |
| B-15 | PASS | `test_status_schema_invariants_rejected`（矛盾组合被 Pydantic 拒绝） |
| B-16 | PASS | 同上（嵌套 `exam_paper_id` 不一致被拒绝） |

## 3. 回归（R-01–R-08）

| 编号 | 结果 | 证据 | 说明 |
| --- | --- | --- | --- |
| R-01 | PASS | pytest 全量（API-1 用例未改动、全绿）；契约文档 | API-1 路径/请求/响应/错误码/顺序/限次不变；仅把私有汇总函数提取为公开 `attempt_summary_from_attempt`（同实现） |
| R-02 | PASS | pytest `test_acceptance`、`test_security_edges` | 模块一登录/鉴权不破 |
| R-03 | PASS | pytest `test_module2_*` | 学生/管理员模块二列表/详情/音频规则不变 |
| R-04 | PARTIAL | pytest 音频 Range；E2E 播放器加载 | 播放/暂停/拖动/翻篇未做人工核听 |
| R-05 | PASS | pytest；E2E 登录；client 代码 | 401 清理/回跳、403 提示 |
| R-06 | PASS | `evidence/frontend-typecheck.txt`、`frontend-build.txt` | `tsc -b`、`vite build` 通过 |
| R-07 | PASS | E2E；API-E2E；pytest | 详情/API-3/页面无受保护字段 |
| R-08 | PASS | `git status`、`alembic/versions/` | 无新增/修改迁移；`alembic upgrade head` 头为基线 `0005_attempt_system` |

## 4. 真实 E2E 场景（1–20）

| # | 结果 | 证据 | 说明 |
| --- | --- | --- | --- |
| 1 | PASS | E2E | 登录→列表→作答→刷新恢复 |
| 2 | PASS | E2E 刷新；E2E 多标签 B 重载 | 关闭标签/刷新后恢复；音频组件重建从 0 开始 |
| 3 | PASS | E2E（标记/确认统计）；C-02（答题卡跳题） | 答题卡点击跳题在组件测试；浏览器侧用“下一篇”翻篇 |
| 4 | PASS | P 双击；pytest 唯一/限次 | 前端单次发送 + 后端只落 1 条 attempt |
| 5 | PASS | E2E | 成功→汇总→刷新已提交 |
| 6 | PARTIAL | API-E2E 学生隔离 | 服务端隔离已验；未开第二浏览器 |
| 7 | PARTIAL | P 登录失效分支；client 代码 | 401 提交中未做真实回跳 |
| 8 | PARTIAL | pytest 404；P E03 重建 | 浏览器未触发真实下线 |
| 9 | PARTIAL | pytest E04；U errors | 浏览器未换批 |
| 10 | PARTIAL | P 404/500 | 真实服务未注入 500；组件测试覆盖 |
| 11 | PASS | API-E2E；pytest | 管理员 API 403；模块二原规则 |
| 12 | PASS | E2E；API-E2E | 无受保护字段 |
| 13 | PARTIAL | C-03；pytest 空答案 | 浏览器未提交空卷 |
| 14 | PARTIAL | U retention | P-03 未确认，自动重试关闭，无法真实触发 |
| 15 | PARTIAL | 页面版本提示代码 | 未真实换批回看 |
| 16 | PASS | U storage；E2E 多标签 | A pending/B 保存，B 不覆盖 A 信封 |
| 17 | PARTIAL | E2E 多标签（待保存冻结）；P（事件未处理兜底） | 后台挂起/即将关闭两态未模拟 |
| 18 | PASS | P 存储不可用 | 确认前不发送、确认后可用内存信封 |
| 19 | PARTIAL | P 404+pending；页面分支 | 真实下线后查询未做 |
| 20 | PARTIAL | U adapters；P 冲突/无时间 | 真实服务注入矛盾响应未做 |

## 5. 核心验收项汇总

核心清单（开发文档 §5.2 / 需求 §11.5）：AC-01–AC-05、AC-11/12、AC-16/17、AC-24、AC-25、AC-34/35/38/40/43/46/47/48/49/50、B-01–B-03/B-13/B-15/B-16、R-01–R-08、UX-01 原型签字。

- 核心项 PASS：AC-01–05、AC-11/12、AC-16/17、AC-24/25、AC-34、AC-40、AC-43、AC-46–50、B-01–03、B-13、B-15/16、R-01–03、R-05–08。
- 核心项 PARTIAL：**AC-35、AC-38**（两项均已有主要证据，但缺文档要求的全部真实组合）。
- 核心项 FAIL/BLOCKED：无。
- 非核心 PARTIAL：AC-08/13/15/29/33、R-04、E2E 6/7/8/9/10/13/14/15/17/19/20。
- UX-01：原型评审结论“通过”；四方签字按用户指示暂不处理 → **PARTIAL（流程留痕未闭环）**。

## 6. 整轮结论

按开发文档 §5.1：整轮通过要求无 FAIL 且**核心验收项无 BLOCKED**；核心项出现 FAIL/BLOCKED 不得判通过。本轮：

- 无 FAIL、无 BLOCKED；
- 核心项 AC-35/AC-38 为 PARTIAL（缺“后台挂起/即将关闭”“pending+内容变化”页面组合证据）；
- UX-01 签字未回填（用户明确暂不处理）。

> **整轮结论：PARTIAL（有条件通过），最终由验收负责人裁定。**  
> 建议：验收负责人对 AC-35/AC-38 的 PARTIAL 书面接受或安排补测；按项目流程补齐 UX-01 签字；P-03 保留期确认后仅修改 `KEY_RETENTION_POLICY` 常量即可放开自动重试。
