# 作答系统验收矩阵（AC-01–AC-50 / B-01–B-16 / R-01–R-08 / E2E 1–20）

> 日期：2026-11-17（含 PR #16 二次独立验收整改）  
> 代码：`D:\ssre_V1\ShengShengRuEr`，分支 `feature/attempt-system`（PR #16；基线 `main@846270b`）  
> 需求 V1.2 / 开发 V1.1 / 原型图集 V1.1  
> 判定口径：**PASS**＝按步骤可复现且符合预期；**PARTIAL**＝有自动化证据但缺规定场景（仅用于非报告口径项）；**FAIL**＝可复现不符；**BLOCKED**＝环境/证据/签字缺失，无法判定（核心项证据不足即 BLOCKED，不用 PARTIAL 替代）。  
> 证据简称：`pytest`＝`backend/tests`（265 passed）；`U`＝`frontend/src/attempt/*.test.ts`；`C`＝`frontend/src/pages/student/attempt/*.test.tsx`；`P`＝`ListeningPaperPage*.test.tsx`；`R`＝`ListeningPaperPage.review.test.tsx`（PR16 定向回归 12 项）；`E2E`＝真实 Edge 浏览器脚本（21 项）；`API-E2E`＝真实服务脚本（23 项）。

## 1. 功能与异常（AC-01–AC-50）

| 编号 | 结果 | 证据 | 说明 |
| --- | --- | --- | --- |
| AC-01 | PASS | C-01；E2E | 整行点选、清除、方向键、计数；`aria-checked` + 勾选图标 |
| AC-02 | PASS | C-02 | 按篇分组、已答/未答/标记/当前、点击题号回调（跳篇+滚动） |
| AC-03 | PASS | C-01；E2E | 标记/取消标记写草稿、答题卡显示、确认框标记数一致 |
| AC-04 | PASS | E2E | 刷新后答案/标记/当前篇恢复；播放器组件从 0 秒重建 |
| AC-05 | PASS | 二轮独立报告真实关闭再进入；E2E 多标签 B 重载 | 真实关闭标签后新开标签进入同卷，答案恢复、音频从 0 开始（二轮报告证据） |
| AC-06 | PASS | U storage | 键含 userId+examPaperId，A/B 用户互不可见 |
| AC-07 | PASS | U codec/storage | 过期/损坏普通草稿删除不崩溃；损坏信封不被删除 |
| AC-08 | BLOCKED | U payload/codec；页面 stale 分支 | 题目集合不一致不恢复旧答案，但页面级 stale 组合未完整实测 |
| AC-09 | PASS | C-03 | 总/已答/未答/标记、仅一次、取消不提交、全未答强提示 |
| AC-10 | PASS | U payload | 全部 loaded IDs 按详情顺序；已答按题目顺序；大写；无重复 |
| AC-11 | PASS | P「双击确认只发送一次」；pytest 并发/唯一约束 | 提交中确认框禁用 + `inFlightRef`；后端唯一约束兜底 |
| AC-12 | PASS | U submit；API-E2E 幂等回放；pytest | 500/网络保留信封并置 unknown；同键同 payload 返回同一 attempt_code |
| AC-13 | BLOCKED | U errors；client 401 代码 | 未做真实“提交中 401 → 登录回跳 → API-3 → 同键一次”浏览器场景 |
| AC-14 | PASS | pytest 404；U errors；P「API-1 404 E03」 | 先按 frozenPayload 重建并读回成功，才清旧信封、保留答案 |
| AC-15 | BLOCKED | pytest E04；U errors；页面 reload-clear 分支 | 页面换批（E04）后清答案/信封并重载未做真实浏览器场景 |
| AC-16 | PASS | pytest E08；P「E08」 | 写 `source=e08, summary=null, submittedAt=null` 标记 → 只读；随后查询补全 |
| AC-17 | PASS（整改） | R「F03」；pytest E09；P「E09 false」 | E09 false 先恢复 frozenPayload 到内存+草稿并读回，成功才清信封；恢复失败保留冻结 |
| AC-18 | PASS | E2E；C-05 | 正确数/率/估分/时间/编号；无逐题、无未答数 |
| AC-19 | PASS | E2E；API-E2E | API-3 false 后正常作答 |
| AC-20 | PASS | E2E；API-E2E | API-3 true 只读汇总，不白答 |
| AC-21 | PASS | API-E2E；pytest | 401/403（管理员）/404（不可访问）顺序与不泄露 |
| AC-22 | PASS | API-E2E；pytest | 字段白名单；true latest 非空且与 API-1 完全一致；false null |
| AC-23 | PASS（整改） | E2E；R「F06」 | 已提交再进入：只读/汇总/播放器/中性导航；同题数旧汇总也显示版本提示 |
| AC-24 | PASS | `evidence/` | pytest 265 passed、`npm test` 18 files/129 passed、typecheck/build 通过 |
| AC-25 | PASS（二次整改） | 本文档集、验收交接、整改说明、需求同步 | 已回写 F01–F09 缺陷、证据与重判；旧文案清理；无首页继续卡片 |
| AC-26 | PASS（整改） | E2E-09；`e2e-07-1440/1280`、`e2e-08-1024.png` | 1440/1280/1024×768 实测提交栏 boundingBox 在视口内（y=715,h=53），页面底部留白防遮挡 |
| AC-27 | PASS | E2E；API-E2E；pytest | 详情/API-3/页面均无答案/解析/正文；E2E 扫描 DOM 无受保护字段 |
| AC-28 | PASS | C-07；U storage；pytest | 信封不参与 TTL/10 份淘汰；pending 无“重新开始”；强警告清除 |
| AC-29 | BLOCKED | U retention/submit | P-03 未确认 → 自动重试关闭（行为正确）；启用后的真实自动重试链路未验 |
| AC-30 | PASS | P「404 标记」「500 标记」；C-07 | 404 不展示汇总；500/网络展示本机标记并标注非权威；普通可答、pending 冻结 |
| AC-31 | PASS | C-03；pytest `test_a2_partial_and_empty_answers` | 全部未答强提示、允许提交、0% 判分 |
| AC-32 | PASS | C-05；E2E | 估分不可用显示“暂不可用”（含 reason），不显示 0 |
| AC-33 | PASS（整改） | R「F06」；E2E-14 | 只要存在汇总就展示“汇总对应提交时版本”，不以题数相等推断未变；真实换批仍待补证（见 §6） |
| AC-34 | PASS | P「未知 400」；U errors | 未知 400 保留信封、冻结编辑、不自动新键 |
| AC-35 | **BLOCKED（核心）** | U rebuild；pytest E04/版本 | pending + 内容变化的 true/false/查询失败三种真实组合未完整执行 |
| AC-36 | PASS | P「存储不可用」 | 内存信封 + 发送前确认；未确认不发送；无崩溃 |
| AC-37 | PASS | U storage；E2E 多标签 | 普通保存不覆盖/删除信封；B 标签保存不影响 A 信封 |
| AC-38 | **BLOCKED（核心）** | P「storage 事件」「写入前检查」；E2E-07 | 已覆盖 B 已保存时 A 成功冻结、事件未处理兜底；后台挂起/即将关闭两态缺完整真实证据 |
| AC-39 | PASS | U retention | unknown/超期不自动重试；手动同键 + 强警告；不自动新键 |
| AC-40 | PASS | U adapters；P「true 坏汇总」 | 确定已提交但汇总不可用：只读、可重查、与冲突分开 |
| AC-41 | PASS | P「404 + 标记」 | 404 不展示汇总、不提供重开、只读提示 |
| AC-42 | PASS | U storage；P「E08」 | 标记 30 天 TTL；API-3 false 删除；E08 无汇总仍显示已提交 |
| AC-43 | PASS | pytest 单语句/并发；API-E2E | 实测只发 1 条 `FROM attempts` SQL（含窗口计数与 LIMIT）；并发一致 |
| AC-44 | PASS | E2E | 已提交无选中/标记/进度；刷新前后一致 |
| AC-45 | PASS | API-E2E；pytest 模块二 | API-1/3 管理员 403；模块二学生视角按原规则 |
| AC-46 | PASS（整改） | R「F01」；E2E-10；U codec/storage | 损坏信封 + API-3 malformed/conflict/not-submitted 均优先 `pending-unrecoverable`，不放开编辑 |
| AC-47 | PASS（二次整改） | R「F02」「F08A/F08B」；E2E-11/15/16 | 初次与手动查询的矛盾响应均冻结；一致 false 后按草稿/pending 分别恢复，保留信封与答案 |
| AC-48 | PASS（二次整改） | pytest Schema；U adapters；R「F01b」「F09」 | 前后端校验语义不变量；malformed 首次加载与手动查询统一冻结，服务端确认未提交后解除 |
| AC-49 | PASS | U storage/adapters；C-05；P | `submittedAt=null` 合法；页面不显示伪造时间、不回编辑 |
| AC-50 | PASS | U submit；P「API-1 404 E03」；R「F03」 | 只留信封时先重建并读回成功才清信封；不兼容/写入失败保留冻结；E04 例外 |

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
| B-15 | PASS | `test_status_schema_invariants_rejected` |
| B-16 | PASS | 同上（嵌套 `exam_paper_id` 不一致被拒绝） |

## 3. PR #16 独立验收整改记录（F01–F09）

| 编号 | 问题 | 整改后验证 | 证据 |
| --- | --- | --- | --- |
| F01 | 损坏信封 + malformed 放开编辑 | PASS：进入 `pending-unrecoverable`，无选项/交卷，仅查询/强警告清除 | R「F01」；E2E-10；`e2e-09-corrupt-malformed.png` |
| F02 | 手动查询矛盾仍可编辑/交卷 | PASS：统一冻结，无可交互选项，交卷禁用 | R「F02」「补充：初次加载矛盾」；E2E-11；`e2e-10-manual-query-conflict-frozen.png` |
| F03 | E09 false 丢冻结答案 | PASS：先恢复答案与草稿并读回，成功才清信封；失败保留冻结 | R「F03」；pytest E09 |
| F04 | 重新开始旧 timer 复活 + 无二次确认 | PASS：确认 Modal + 取消 timer；>700ms 后草稿仍空 | R「F04」；E2E-12 |
| F05 | 站内返回丢失最后作答 | PASS：卸载 flush；返回列表再进入恢复选中 | R「F05」；E2E-13 |
| F06 | 同题数换批缺版本提示 | PASS：有汇总即提示“汇总对应提交时版本” | R「F06」；E2E-14；`e2e-11-same-count-version-notice.png` |
| F07 | 提交栏视口内不可见 | PASS：固定底部栏；1440/1280/1024×768 视口内坐标断言通过 | E2E-09；`e2e-07-1440.png`、`e2e-07-1280.png`、`e2e-08-1024.png` |
| F08 | 冲突后一致 false 不能解除冻结（草稿/ pending） | PASS：草稿恢复可编辑；pending 保留信封并解除同键重试禁用；损坏信封仍保护 | R「F08A/F08B」；E2E-15/16；`e2e-12`、`e2e-13` 截图 |
| F09 | 手动查询 malformed 仍可编辑 | PASS：与首次加载统一冻结，交卷禁用，可再查 | R「F09」；E2E-17；`e2e-14-manual-malformed-frozen.png` |

> 整改说明全文：`docs/acceptance/attempt-system/PR16-整改说明-20261116.md`；二次整改：`PR16-二次整改说明-20261117.md`。

## 4. 回归（R-01–R-08）

| 编号 | 结果 | 证据 | 说明 |
| --- | --- | --- | --- |
| R-01 | PASS | pytest 全量；契约文档 | API-1 路径/请求/响应/错误码/顺序/限次不变 |
| R-02 | PASS | pytest `test_acceptance`、`test_security_edges` | 模块一登录/鉴权不破 |
| R-03 | PASS | pytest `test_module2_*` | 学生/管理员模块二规则不变 |
| R-04 | **BLOCKED（核心）** | pytest 音频 Range；E2E 播放器加载 | 缺真实材料人工核听与播放/拖动回归签认 |
| R-05 | PASS | pytest；E2E 登录；client 代码 | 401 清理/回跳、403 提示 |
| R-06 | PASS | `evidence/frontend-typecheck.txt`、`frontend-build.txt` | `tsc -b`、`vite build` 通过 |
| R-07 | PASS | E2E；API-E2E；pytest | 无受保护字段泄露 |
| R-08 | PASS | `git status`、`alembic/versions/` | 无新增/修改迁移；head=`0005_attempt_system` |

## 5. 真实 E2E 场景（1–20）

| # | 结果 | 证据 | 说明 |
| --- | --- | --- | --- |
| 1 | PASS | E2E | 登录→列表→作答→刷新恢复 |
| 2 | PASS | E2E 刷新；E2E-07 B 重载 | 恢复路径；音频组件从 0 重建 |
| 3 | PASS | E2E；C-02 | 标记/确认统计/答题卡跳题（组件） |
| 4 | PASS | P 双击；pytest 唯一/限次 | 前端单次发送 + 后端只落 1 条 |
| 5 | PASS | E2E | 成功→汇总→刷新已提交 |
| 6 | BLOCKED | API-E2E 学生隔离 | 服务端隔离已验；未开第二浏览器 |
| 7 | BLOCKED | P 登录失效分支 | 401 提交中未真实回跳 |
| 8 | BLOCKED | pytest 404；R E03 重建 | 浏览器未触发真实下线 |
| 9 | BLOCKED | pytest E04；U errors | 浏览器未换批 |
| 10 | BLOCKED | P 404/500 | 真实服务未注入 500 |
| 11 | PASS | API-E2E；pytest | 管理员 403；模块二原规则 |
| 12 | PASS | E2E；API-E2E | 无受保护字段 |
| 13 | BLOCKED | C-03；pytest 空答案 | 浏览器未提交空卷 |
| 14 | BLOCKED | U retention | P-03 未知，自动重试关闭，无法真实触发 |
| 15 | BLOCKED | R F06 注入 | 真实换批后回看未做 |
| 16 | PASS | U storage；E2E-07 | A pending/B 保存不覆盖信封 |
| 17 | BLOCKED | E2E-07；P 写入前检查 | 后台挂起/即将关闭两态仍缺 |
| 18 | PASS | P 存储不可用 | 确认前不发送、确认后内存信封 |
| 19 | BLOCKED | P 404+pending | 真实下线后查询未做 |
| 20 | BLOCKED | U adapters；R 冲突/无时间 | 真实服务注入矛盾响应未做（F02 用响应注入验证页面行为，不作为真实换批证据） |

## 6. 核心验收项汇总与整轮结论

核心清单（开发文档 §5.2 / 需求 §11.5）：AC-01–05、AC-11/12、AC-16/17、AC-24、AC-25、AC-34/35/38/40/43/46/47/48/49/50、B-01–B-03/B-13/B-15/B-16、R-01–R-08、UX-01 原型签字。

- 核心项 PASS：AC-01–05、AC-11/12、AC-16/17、AC-24/25、AC-34、AC-40、AC-43、AC-46–50、B-01–03、B-13、B-15/16、R-01–03、R-05–08。
- 核心项 BLOCKED：**AC-35、AC-38、R-04、UX-01**（真实组合/人工核听/签字证据不足）。
- 非核心 BLOCKED：AC-08/13/15/29；E2E 6/7/8/9/10/13/14/15/17/19/20。
- 非核心 PARTIAL：无；核心项 FAIL：无。

> **二次整改后结论：F01–F09 均已修复并有回归证据；AC-05 由二次独立报告补齐。但按需求 §11.5，核心项仍有 BLOCKED（AC-35/AC-38/R-04/UX-01），不得判整轮“通过”。**  
> 下一步：验收人复跑 F08/F09 修复，补齐 AC-35/AC-38、R-04 人工核听、UX-01 签字后重判；F06 的真实管理员换批证据亦需补跑。
