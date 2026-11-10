# 模块二前端（任务二）交付总览

> 一页看清：任务从哪来、做到哪一步、证据在哪、还差什么。
> 更新：2026-11-10 ｜ 分支 `feature/m2-frontend-listening-papers` ｜ 提交 `2486c80`（基于 `develop` `b965a0f`）
>
> **本文用途：进度汇报 + 请示，不是"验收通过申请"。** 当前结论为 PARTIAL / BLOCKED，尚未达到提交验收结论的条件。

## 0. 结论与请示

**功能已按任务二范围实现，并通过两轮独立验收的代码审查；当前唯一硬阻塞是验收环境的后端未搭起**（无 `.env`、无 `psycopg`、5432 无监听、Python 版本不达基线），导致"新卷 → 确认 → 学生可见"的真实链路与 F13 持久化无法执行。前端代码本身可运行、构建通过。

| # | 请您决定 | 选项 | 我的建议 |
| --- | --- | --- | --- |
| 1 | 验收环境由谁负责搭 | A. 后端负责人按手册重建 3.13.16 环境；B. 验收人自建 | **A**：环境属于项目基线，不该压在验收人身上 |
| 2 | 真实样例（原卷/音频）怎么给验收人 | A. 受控资料包离线交付；B. 拷进仓库外受控目录 | **A**：版权原因不入库，保持现状 |
| 3 | 是否先合入 `develop` | A. 严格等真实 E2E 通过再合；B. 先合分支，环境问题另开任务 | **A**：改动依赖后端状态语义，未跑真实链路就合入风险偏高；若排期紧可 B，但需在 PR 标注"未做真实 E2E" |

> 注：本轮只做了任务二的"页面实现"部分；原始任务里的"其他功能（数据处理、作答）原型"已按确认移出，另立一轮。

## 1. 任务原口径

来源：《会议总结与后续工作要求》第五节「第二项任务：补齐模块二前端，设计其他功能的界面原型」。

| 原始要求 | 本轮处理 |
| --- | --- |
| 管理端：试卷列表、试卷详情、答案解析与原文查看、检查结果、确认/取消学生可见 | **已实现**（同一路由内分栏 + 抽屉） |
| 学生端：可见试卷列表、整套听力题目展示、音频播放与暂停 | **已实现**（按篇章分页 + 页级播放器） |
| 所有前端先出原型、随需求文档交施博宇审核 | **已交付原型**（线框稿，随需求 V0.4 送审） |
| 其他功能（数据处理、作答）先出原型图片 | **移出本轮**，另立一轮（决议 D1，用户 2026-11-07 确认） |
| 视觉风格文档暂缓 | 遵循，只做布局与功能 |

> 因此：**本轮完成 ≠ 任务二整体完成**，剩余"其他功能原型"未开始。

## 2. 交付了什么

4 个页面 + 支撑层，未改后端、未改库结构、未新增依赖：

| 端 | 路由 | 关键能力 |
| --- | --- | --- |
| 管理端 | `/admin/listening-papers` | 三状态列、级别/年份筛选（URL 保留）、逐卷补调状态、行级失败重试 |
| 管理端 | `/admin/listening-papers/:id` | 原文/题目左右分栏（共享篇章）、检查摘要+抽屉、确认/取消开放、试听 |
| 学生端 | `/student/listening-papers` | 仅可见卷、"查看听力" |
| 学生端 | `/student/listening-papers/:id` | 按 `passages.length` 分页、播放器页级常驻、题目只读 |

## 3. 文档链路（按流程顺序）

| 环节 | 文件 | 状态 |
| --- | --- | --- |
| 原始需求 | `docs/requirements/module-2/requirements.md`（V1.5） | 基线 |
| 前端需求 + 验收卡 | [frontend-requirements.md](../requirements/module-2/frontend-requirements.md)（V0.4） | 已确认，含 F01–F18 |
| 页面原型 | [frontend-prototype.html](../requirements/module-2/frontend-prototype.html) | 线框示意稿（非视觉标准） |
| 实现与自查 | [frontend-implementation.md](frontend-implementation.md) | 2026-11-08 |
| 交接说明 | [frontend-handoff.md](frontend-handoff.md) | 历史原文 |
| 首验报告 | [frontend-acceptance-20261109.md](frontend-acceptance-20261109.md) | 16 PASS / 1 PARTIAL / 1 FAIL |
| 整改说明 | [frontend-rework-20261109.md](frontend-rework-20261109.md) | 两轮整改（11-09、11-10） |
| 复验报告 | 验收人 2026-11-10 出具（未入库） | 10 PASS / 7 PARTIAL / 1 BLOCKED |
| 环境复验手册 | [frontend-e2e-runbook.md](frontend-e2e-runbook.md) | 新增 |
| 截图证据 | [screenshots/](screenshots/) | 18 张（开发者侧） |

## 4. 原始要求 → 实现 → 验收卡

| 原始要求 | 实现位置 | 验收卡 | 当前 |
| --- | --- | --- | --- |
| 试卷列表（管理员） | `pages/admin/ListeningPaperListPage.tsx` | F03 | PASS |
| 试卷详情/答案/解析/原文 | `pages/admin/ListeningPaperDetailPage.tsx` | F04、F05 | PASS（真实规模待补） |
| 检查结果 | 页内摘要 + `Drawer` | F06 | 首验 PASS；复验 PARTIAL（旧文案）→ **已修** |
| 确认/取消学生可见 | 弹窗 + `POST /visibility` | F07、F08 | F07 逻辑已修并复验认可，真实 E2E 待环境；F08 PASS |
| 学生可见列表 | `pages/student/ListeningPaperListPage.tsx` | F09、F11 | PASS |
| 整卷题目展示 | `pages/student/ListeningPaperPage.tsx` | F12、F15 | PASS（真实规模待补） |
| 音频播放/暂停 | `ui/AudioPlayer.tsx` + `api/audio.ts` | F10、F16 | PASS（12s WAV） |

## 5. 当前结论

- **代码侧**：F07 的不可达闭环已修复并获复验认可；F06 抽屉旧文案已于 2026-11-10 修掉；F14 文档与截图已补（首验 19 张在验收人受控目录，未入库，已在报告顶部说明）。
- **环境侧**：复验机缺 `.env`/`psycopg`/PostgreSQL，`pytest` 34 项全部 setup error，F13 与 F07 真实链路判 **BLOCKED**。手册已给出逐步恢复方法。
- **版本基线**：V1.2 要求 Python 3.13.16 / Starlette 1.7.0；复验机 3.12.10，开发机 3.14.10，**两边都要重建**。

## 6. 还差什么（放行条件）

1. 按手册建 3.13.16 环境，`pytest` 真实 34 passed（不是 setup error）。
2. 跑两条真实链路：新卷确认成功 → 学生可见；确认失败 → 400 → 新失败记录 → 重试。
3. 上述通过后创建目标 `develop` 的 PR（merge commit），附本总览与复验结论。

## 7. 代码与提交

| 提交 | 内容 |
| --- | --- |
| `247328a` | 4 个页面、接口层、播放器（首版实现） |
| `630371e` | 解除确认开放的检查前置；README 重写；需求/原型/报告/截图入库 |
| `c6e1b62` | 回填提交号与环境说明 |
| `850a4e2` | 抽屉旧文案修正；截图补齐与说明；V0.3→V0.4；复验手册 |

均未进入 `develop`，PR 尚未创建；本文所在提交为 `2486c80`。
