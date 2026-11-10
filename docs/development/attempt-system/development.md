# 基础作答系统开发文档（A/C/D 组 · 接口层）

> **文档版本**：v0.12（**v0.11 + 2026-11-10 T01–T03 验收回改**；需求 v0.20、D10/D11、T2/T3 已确认，D-14 已在需求 v0.21 修订；**A/C/D 组 T01–T10 可开工**）　**初编日期**：2026-11-08　**修订日期**：2026-11-10
>
> **当前状态（务必先读）**：① **需求 v0.19（2026-11-08）与 v0.20 编修性补充、D10/D11、T2/T3 已于 2026-11-10 经负责人确认（书面件待补）**；② **T2=attempt-system、T3=3.14.x 已定**；③ **A/C/D 组 T01–T10 可开工**；R 组/API-2/结果页仍冻结至 P1 回写 + P6 满足；T10 与 V-E 系列在验收数据就位前记 BLOCKED。决策记录见附录 E.12。
>
> **版本与审查状态统一（v0.12，2026-11-10）**：本文件为唯一权威版本，覆盖工作区旧 v0.9（2026-11-08），旧版归档为 `development_v0.9_20261108.md`；v0.8 内容依据《v0.7 终版审查报告》修订，**v0.12 本身尚无独立复审结论**，不得宣称 PASS；审查报告引用已改为仓库相对路径说明（待归档，见附录 E.9）。
>
> **本版修订摘要**：在 v0.7 基础上分离 JSON 与路径 ID 校验；按持久化状态恢复未知提交；统一异常级别与验收结论；拆分代码回退/数据库降级；明确异常及异常链脱敏；将端到端脚本明确为有写入流程；新增不同键并发限次实现自测；同步约束命名、舍入边界与 HTTP 验收责任。详见 E.9。**这些是文档设计修订，未实施代码、迁移或运行验收；v0.20 未签认前仍为草案。**
>
> **需求基线**：《基础作答系统需求文档》**v0.21（2026-11-10 负责人确认 v0.20 补充签认与 D-14 修订；书面件待补）**；路径 `docs/requirements/attempt-system/requirements.md`；历史记录见同目录 `review-log.md`。
>
> **代码基线**：仓库 `ShengShengRuEr-Team/ShengShengRuEr` 的 `develop` @ `b965a0f`（2026-11-08 本地实读；未运行测试、迁移或数据库查询）。
>
> **本轮性质**：**仅编写文档，不实施开发**。文中所有“预期结果”“验证命令”“实测输出”均为**待执行的方案**，不是已完成的测试结论；任何 PASS/PARTIAL/FAIL/BLOCKED 只能由验收人按第 6 节模板回填。
>
> **本轮范围**：A/C/D 组（提交、判分、汇总、幂等、边界）。API-2 与结果读取（R 组）因 1.5 例外生效条件未满足 + P6 未满足而**冻结**；前端、结果页、管理端统计不在本轮。
>
> **落盘位置**：计划归档至 `docs/development/attempt-system/development.md`（**未入版本控制**）；T2 确定后迁入仓库并随 PR 提交。当前工作区唯一权威版本为 **v0.10.1**（由 2026-11-10 的 v0.8 内容统一升版并处理 V10-01–V10-03）；旧 v0.9（2026-11-08）归档为 `development_v0.9_20261108.md`，v0.7 被审原文与审查证据另行保留（待归档）。

---

## 0 文档信息与使用方式

### 0.1 本文解决什么

把《基础作答系统需求文档》中本轮可执行的 A/C/D 组需求，翻译成**可直接分工实施**的中文开发文档：

- 能明确“做什么、不做什么、按什么顺序做、每步的代码入口在哪里、怎样算做完”；
- 需求条目、任务编号、验收用例三者可双向追溯（见附录 A）；
- 区分“当前代码已实现的事实”与“本轮要新增的设计”，并把所有未决项显式登记，不假装已拍板。

### 0.2 读者与用法

| 角色 | 用法 |
|---|---|
| 负责人 | 审阅第 1 节范围与第 1.6 节待确认项，给出书面口径；决定 T1/T2/T3 等阻塞项；**不替代验收人签字** |
| 开发人 | 按第 3 节顺序领取第 4 节任务卡；每卡完成后按卡内验收标准自测并在 PR 写证据；**不得自行认定验收通过** |
| 验收人 | 按第 5 节矩阵逐项构造场景，用第 6 节模板回填 PASS/PARTIAL/FAIL/BLOCKED 与证据位置；**不得为同一实现的开发人** |
| 模块二维护人 | 维护题库与可见性；**负责回写模块二 B04.3/B05**；与作答实现的开发人分离 |
| 两名独立验收 / 复核人 | 核对“需求—任务—验收”一致性、是否混淆当前实现与目标设计、是否存在未回填的测试结论 |

> **角色独立性（需求 v0.20 §3.4）**：验收人不得是同一实现的开发人；模块二维护人负责回写 B04.3/B05，且与作答实现的开发人分离；所有角色须以真实身份留痕（签认、验收、PR 记录），**系统不得代填不存在的人员**。

### 0.3 证据等级约定

本文对事实性陈述标注来源等级，**避免把文档记录当成复验结论**：

| 等级 | 含义 | 本文中的典型用法 |
|---|---|---|
| **A｜代码已核对** | 2026-11-08 在 `b965a0f` 上实读文件与行号确认 | 现有能力、代码入口、依赖版本 |
| **B｜文档记录** | 既有材料记载，本次未重跑/未复验 | pytest 历史通过数、本地库 0 行、B16 未完成 |
| **C｜检索核实** | 通过 PyPI/官方文档/Datatracker 等公开页面核对（附 URL），未拉取 GitHub 源码 | 第 2.11 节技术调研的许可证、版本、发布日期 |
| **D｜未核实/待确认** | 无可靠证据或需负责人拍板 | 第 1.6 节待确认项、验收数据是否可得 |

### 0.4 与仓库规范的关系

- 本文沿用 `docs/development/api-conventions.md`：`/api/v1` 前缀、`snake_case` 字段、`{code,msg,data}` 响应外壳、401→403 顺序、学生隐藏资源统一 404。
- 命名沿用 `docs/development/naming-conventions.md`：表名复数 `snake_case`、主键 `id`、外键 `<实体>_id`、时间 `*_at` 且 UTC、布尔 `is_/has_/can_` 前缀、Python `snake_case`、文档 `kebab-case.md`。
- 文档归档沿用 `docs/decisions/common/0003-document-organization.md`：`requirements` 定义预期、`development` 保存方案与任务、`acceptance` 保存记录。
- 流程沿用 `docs/development/development-guide.md`：从最新 `develop` 建任务分支、PR 目标 `develop`、Merge commit、一人开发两人独立验收。

#### AGENTS.md 检索记录（必须如实说明）

按用户要求核对 `AGENTS.md`。2026-11-08 在以下位置检索：

| 检索位置 | 结果 |
|---|---|
| 工作区 `D:\guochuangxiangmu` | 未找到 |
| 代码仓库 `D:\ShengShengRuEr\ShengShengRuEr` | 未找到 |
| 用户目录 `C:\Users\zxy`（深度 2） | 仅见 `C:\Users\zxy\.codex\AGENTS.md`，**文件为 0 字节，无有效规则**；另有无关项目 `C:\Users\zxy\MathModel Projects\Workspace\AGENTS.md` |

**结论**：本机不存在可执行的项目级 `AGENTS.md` 规则。因此本文按仓库既有文档规范、开发流程与现有代码约定编写，**不为满足“遵守 AGENTS.md”而虚构规则**。若负责人另有项目级规则文件，请补充路径后据其复核本文（登记为待确认 D-12）。

---

## 1 需求与基线

### 1.1 依据材料

| # | 材料 | 位置 / 版本 | 本文使用方式 | 等级 |
|---|---|---|---|---|
| 1 | 基础作答系统需求文档 | `docs/requirements/attempt-system/requirements.md` **v0.19（负责人确认，书面件待补）+ v0.20 编修性补充（待负责人确认）** | 需求、规则、验收的唯一基线；v0.20 新增验收/流程约束 | B（已读） |
| 2 | 需求修订与审查记录 | `docs/requirements/attempt-system/review-log.md` | 核对审查项状态与版本沿革 | B（已读） |
| 3 | 模块二需求/开发/验收文档 | 仓库 `docs/requirements/module-2/`、`docs/development/module-2/`、`docs/acceptance/module-2/` | 复用边界、既有接口语义、验收口径 | B（已读关键篇） |
| 4 | 后端与前端代码 | 仓库 `backend/`、`frontend/` @ `b965a0f` | 现有能力、代码入口、约束 | **A** |
| 5 | 迁移与依赖 | `backend/alembic/versions/0001–0004`、`backend/requirements.txt`、`backend/pyproject.toml`、`backend/README.md` | 迁移头、版本、Python/ruff 口径 | **A** |
| 6 | 技术调研 | PyPI / SQLAlchemy 文档 / Alembic 文档 / IETF Datatracker 等公开页面 | 第 2.11 节参考项 | **C**（附 URL） |
| 7 | 本次未做 | 未运行 pytest、未运行端到端脚本、未升级/降级迁移、未查询数据库 | 据此不写任何“实测通过” | — |

### 1.2 已确认需求与执行口径

需求文档 2.5 记录：负责人于 2026-11-08 确认 **v0.19**（v0.18.1 内容 + 签认记录）作为“开发文档与后续开发的依据”，**书面件待补**；**v0.20** 为在此基础上追加的编修性补充（角色独立性、异常分级、禁止做法、证据形式、开发门禁），**待负责人确认**。签认口径（原文要点）：

- D1–D9、R1–R4 按文档现状；D4 按 v0.18（含 **249 分练习估分**，须标注“非官方成绩”）；D10 按 1.5(6) 现行口径**禁止解析引用正文原句**；D11 按 12.2 默认 A（1.5 例外生效条件满足前：**仅汇总 + 同卷限 1 次成功提交**）——**D11 仍待拍板**，2.5 仅将其作为验收草稿口径。
- **版本说明**：v0.19 规则已确认（**书面件待补**）；v0.20 的编修性补充**待负责人确认**。本文已按 v0.20 预同步异常分级、角色独立性、禁止做法、证据形式与门禁约束，并全部标注“待确认”，不宣称 v0.20 已签认。**若 v0.20 未获确认，本文仅作 v0.19 草案，v0.20 新增门禁/分级不生效**；T2/T3 未定前不得开工。
- **尚未满足的前提**：① 1.5 唯一例外（交卷后结果读取）未回写模块二 B04.3/B05；② P6 题库内容治理未满足（D10 未拍板、抽检仅初筛、T11 未定）→ **结果读取本轮不上线**；③ T2 文档路径/编号、T3 Python 版本未定（v0.20 §14.2 要求写开发文档前定，本文按默认值待确认）。
- **据此的执行范围**：本轮开发只做 **A/C/D 组**（提交、判分、汇总、幂等、边界）；API-2、AS-09–15、结果页相关项按冻结处理。

> **口径澄清**：v0.19 已确认 D1–D9、R1–R4（书面件待补）；**D10、D11 仍待拍板**；1.5 例外生效条件未满足。本文把已确认口径作为开发执行依据，但**不据此宣称 D10/D11 或 v0.20 已签认**；凡涉及这些条目的验收结论，仍须在回填模板中注明“规则待签认/待拍板”状态。

本轮开发的执行口径汇总：

| 维度 | 本轮口径 | 依据 |
|---|---|---|
| 作答粒度 | 只做整卷 | D1 |
| 前端 | 不交付页面、路由、播放器；只验收接口层 | D2、9.1、OUT1 |
| 多次作答 | 1.5 例外生效前时**同一学生同一试卷限 1 条成功 attempt**；P1 生效后解除（本轮不实现）。**D11 未拍板，按草稿口径执行，结论待拍板** | D3、D11=A（草稿）、BR-18a |
| 计分 | 服务端唯一权威；整数正确率（四舍五入）；另给 **0–249 练习估分**，两者分开呈现、不得互替 | O2、D4、BR-16/16a/17 |
| 估分可用性 | 题型缺失或非 25 题标准卷 → **不输出估分数值** | BR-16a、7.2 S-9 |
| 部分作答 | 允许；未作答按错计但须与答错区分 | D9、BR-15 |
| 提交幂等 | 同键重试返回同一结论、不新增；重新作答=新键 | R2、BR-19 |
| 拒绝标记 | 仅 AS-07 准入拒绝与 EX-09b 版本不一致作为创建标记的业务原因；参数非法不留标记，服务端故障不另行生成标记；已尝试 COMMIT 的标记是否存在按 2.6.4 查询确认 | BR-20、7.6、R7-02 |
| 快照 | 提交瞬间固化，后续题库修改/换批不回写 | D8、BR-23、7.2 |
| 结果读取 | **冻结**（1.5 例外生效条件未满足 + P6 未满足） | 1.5(4)、4.5 P1/P6、4.6 |
| 数据库 | PostgreSQL；新增表纳入 Alembic，单 head、可 downgrade、不改既有迁移/模块一表 | BR-26、G1 |
| 技术约束 | 不新增第三方依赖、不引入第二套响应外壳/新框架/新 ORM/Redis | OUT11 |

### 1.3 执行边界

#### 1.3.1 本轮做（IN）

| 编号 | 内容 | 落点 |
|---|---|---|
| IN1 | 学生对“学生可访问”试卷提交整卷作答 | API-1、T06 |
| IN2 | 服务端判分并持久化 attempt 与逐题事实 | T05、T06 |
| IN3 | 交卷后读取本人结果 | **本轮不做**（冻结，见 1.3.2） |
| IN4a | 提交异常分支：准入拒绝、内容版本不一致拒绝、幂等、原子性 | T03、T04、T06 |
| IN4b | 读取异常分支 | **本轮不做**（依赖 P1） |
| IN5 | 作答数据落库与迁移 | T01 |

#### 1.3.2 本轮不做（OUT / 冻结）

| 编号 | 不做 | 归属/原因 |
|---|---|---|
| OUT1 | 前端页面、播放器、线框 | 前端轮次；D2 |
| OUT2 | 草稿、断点续答 | D6 |
| OUT3 | 限时、超时强制交卷、回放限制 | D5 |
| OUT4 | 错题本、错因、推荐、DKT | 后续模块 |
| OUT5 | 展示听力正文/原文时间轴 | 明确不做 |
| OUT6 | 管理端统计、单条结果审计 | 后续模块；管理员本轮 403 |
| OUT7 | 历史列表、整卷导出/下载 | 本轮只定义单次读取（且冻结） |
| OUT8 | 单题/分篇练习、按题组交卷 | D1 |
| OUT9 | 管理员代答 | 403（R1/AS-17） |
| OUT10 | 新增逐题分值字段、可配置权重 | 估分按题型占比，不改题库结构 |
| OUT11 | 新依赖、第二套响应外壳、新框架/ORM、Redis | 技术约束 |
| **FZ1** | **API-2 结果读取（含 AS-09–15、AS-19b、AS-20b、V-09–V-15b、V-19b、V-20b、V-E2/E3/E5b 读取部分）** | 1.5 例外生效条件未满足（未书面签认/未回写） + P6 未满足；按 4.6 收缩版冻结，不出任务卡 |
| **FZ2** | **API-1 逐题正误反馈** | D11=A：1.5 例外生效前时仅汇总；逐题事实仍落库（O3），但不返回 |
| **FZ3** | **结果页信息项（9.2）与原型（9.3）** | 依赖 P1；前端轮次另行处理 |
| **FZ4** | **解析不含正文原文的自动检测（T11/V-15b）** | 题库内容治理职责；T11 未定，不得由作答系统实现或放行 |

#### 1.3.3 既有系统边界（不得改动）

1. **模块一**：`users / roles / user_roles / token_revocations` 4 张表、登录/退出/当前用户/管理员概览接口、鉴权顺序均不改。
2. **模块二 6 个接口**：路径、方法、权限、响应字段与语义均不改；学生接口继续在服务端剔除答案、解析、听力正文；不新增“已交卷则返回答案”分支。
3. **模块二表**：不新增“已作答”字段，不改既有 11 张表结构；作答数据只落新表。
4. **迁移**：`0001–0004` 一字不改；新迁移以 `0004_expected_count_source` 为父、单 head、`downgrade()` 可回退。
5. **可见性联动**：交卷不改变任何可见性/检查/批次状态；不作级联删除。

#### 1.3.4 开发门禁（需求 v0.20 §14.2）

| 项 | 门禁 | 本文状态 |
|---|---|---|
| A/C/D 组（提交、判分、汇总、幂等、边界） | D1–D9、R1–R4、D4 已确认；v0.20 已于 2026-11-10 确认；T2/T3 已定 | **可开工**（T10/V-E 待验收数据） |
| R 组 / API-2 / 结果页 | P1 回写 B04.3/B05 + P6 满足前 **不开发** | 已冻结（FZ1/FZ3） |
| D10 / D11 | 只影响解析口径与 P1 未生效时反馈/限次，**不阻塞 A/C/D** | **已签认**：D10 维持禁止；D11=A（仅汇总+同卷 1 次） |
| T2（路径/编号） | **写开发文档前须定**；本文暂存 `docs/development/attempt-system/` | **已定**：中性 `attempt-system`，编号后续统一 |
| T3（Python 版本） | **写开发文档前须定**；本文按仓库 3.14.x | **已定**：3.14.x 开发+验收，迁移 3.13.16 另立 |
| v0.20 编修性补充 | 负责人确认后生效 | **已确认（2026-11-10）** |

> **门禁结论（统一口径，2026-11-10 更新）**：v0.20 已由负责人确认，T2/T3 已定 → **A/C/D 组 T01–T10 可开工**。R 组/API-2/结果页仍冻结至 P1 回写 B04.3/B05 与 P6 满足；T10 与 V-E 系列在验收数据（可访问试卷、16 表工作簿、音频）就位前记 **BLOCKED**，不得伪造数据。决策与签认记录见附录 E.12。

#### 1.3.5 最小可交付路径（建议，待负责人确认）

按 3.1/3.2 的依赖关系，**T06（API-1）依赖 T03、T04、T05，不存在“跳过中间卡”的捷径**。人力不足时建议按以下阶段交付，每阶段结束即可验收对应矩阵行；**本节只影响领取顺序，不改变任务卡内容、依赖关系与验收矩阵。**

| 阶段 | 卡 | 可验收内容 |
|---|---|---|
| M1 数据与契约 | T01 → T02 | 迁移可升级/回退；请求/响应模型单测 |
| M2 核心服务（可并行） | T03、T04、T05 | 幂等与永久标记、准入/版本校验、判分/249 估分单测 |
| M3 编排与边界 | T06 → T07 | API-1 主链路；权限顺序与既有接口回归 |
| M4 测试与端到端 | T08 → T09 → T10 | 全量回归、验收脚本、真实数据验收 |

> 若只能先做一小块：M1 + T05 可独立交付“判分与 249 估分”纯逻辑（不依赖 API-1），但**不得据此宣称 A/C/D 组完成**；T06 仍需等待 T03/T04/T05 全部完成。

### 1.4 当前实现（代码已核对 @ `b965a0f`）

#### 1.4.1 已有能力

| 能力 | 状态 | 依据（文件:行号） | 对开发的含义 |
|---|---|---|---|
| 登录、JWT、账号状态、撤销 | 已具备 | `backend/app/api/deps.py:67`（`get_current_user`） | API-1 直接 `Depends(get_current_user)`，不新建鉴权 |
| 管理员鉴权 | 已具备 | `backend/app/api/deps.py:99`（`require_admin`） | 401 由前者抛出、403 由后者抛出，顺序已正确 |
| 统一响应与异常 | 已具备 | `backend/app/core/errors.py:8,47`；`backend/app/main.py:33–70` | 复用 `ok()`/`AppError`，不建第二套外壳；422 不回显请求值 |
| 路由挂载 | 已具备 | `backend/app/main.py:73–76` | 新 router 以 `/api/v1` 前缀挂载 |
| 学生可访问判定（三条件） | 已具备 | `backend/app/repositories/listening.py:71–87`（`student_access`）；`:34–41`（当前批次） | 作答准入直接调用，不复制条件 |
| 整卷详情组装 | 已具备 | `backend/app/repositories/listening.py:175–217` | 复用其题目/选项读取思路；不在接口层写死题目 |
| 选项按原卷映射重排 | 已具备 | 同上 `:138–153`（`_options_for`） | 判分/快照必须复用同一映射逻辑 |
| 题库答案→原卷答案换算 | 已具备 | 同上 `:156–172`（`_paper_correct_option`） | 判分只比较“原卷字母”，禁止直接比较题库字母 |
| 学生详情字段裁剪 | 已具备 | `backend/app/schemas_listening.py:29–59`；`repositories/listening.py:175–217` | 学生接口无答案/解析/正文；API-1 同样不得泄露 |
| 学生接口（3 个） | 已具备 | `backend/app/api/listening_papers.py:42,52,65` | 回归基线 |
| 管理员接口（3 个） | 已具备 | `backend/app/api/admin_listening_papers.py:36,50,88` | 回归基线；管理员本轮对 API-1 返回 403 |
| 最低内容检查 | 已具备 | `backend/app/services/content_check.py:28–160` | 作答准入以判定结果为准，不重做内容检查 |
| 可见性/取消可见+审计 | 已具备 | `backend/app/services/visibility.py:41,73`（`confirm_visible`/`cancel_visible` 定义行） | 管理员操作既有接口，作答系统只读判定 |
| 模块二 11 张表 | 已具备 | `backend/app/db/models_listening.py` | 只读复用，不新增列 |
| Alembic 迁移链 | 已具备，单 head | `0004_expected_count_source`（父 `0003` → `0002` → `0001`） | 新迁移 `0005` 以 `0004` 为父 |
| 后端测试夹具 | 已具备 | `backend/tests/conftest.py:53–97`（独立测试库+迁移+种子）、`:107`（登录） | 新测试沿用，不改建库逻辑 |
| 现有测试文件 | 已具备（文档记录：29 个测试函数，参数化后 34 例） | `test_acceptance.py`(6)、`test_module2_listening.py`(12)、`test_module2_recheck.py`(6 函数/11 例)、`test_security_edges.py`(5) | 本轮须全绿回归；**本次未运行，数字为静态函数计数** |
| 端到端脚本模式 | 已具备 | `backend/scripts/acceptance.py`、`acceptance_module2.py`（httpx、逐项 PASS/FAIL、退出码） | 新增 `acceptance_attempt.py` 沿用同一风格 |

#### 1.4.2 明确未实现

| 事项 | 证据 | 结论 |
|---|---|---|
| 作答数据表 | `backend/app/db/` 无 attempt 模型；迁移仅到 `0004` | **未实现**（G1） |
| 判分能力 | 代码中无判分/提交路由；在 **backend 代码**中检索 `attempt`、`作答`、`判分` 无命中 | **未实现**（G2） |
| 交卷后结果读取 | 无对应路由；模块二学生接口仍只返回可见字段 | **未实现且本轮冻结**（G3/FZ1） |
| 结果页 | `frontend/src/router/index.tsx` 仅 `/login`、`/admin`、`/student`、`/403` 四个页面，无模块二/作答代码 | **未实现且本轮不做**（G4） |
| 学生可访问的样例数据 | 需求 4.5 P2 记录“本地开发库 module-2 11 张表 0 行（2026-11-08 只读查询）” | **文档记录（B）**，本次未复验；影响端到端验收（T10） |

#### 1.4.3 版本与环境事实

| 项 | 值 | 来源 |
|---|---|---|
| 后端 Python | 3.14.2（README 记录；ruff `target-version="py314"`） | `backend/README.md:9`、`backend/pyproject.toml` |
| 依赖（精确锁定） | fastapi 0.143.0、SQLAlchemy 2.1.4、alembic 1.20.0、pydantic 2.14.1、psycopg[binary] 3.3.6、PyJWT 2.15.1、bcrypt 5.0.0、pytest 9.2.0、httpx 0.28.1 等 | `backend/requirements.txt`（A） |
| 数据库 | PostgreSQL 18.6（开发/测试两套库，测试库 `shengshengruer_test` 由夹具创建） | `docs/development/module-2/design.md` §11.3–11.4（B），`tests/conftest.py`（A） |
| 时区 | 连接串 `-c timezone=UTC`；时间列 `DateTime(timezone=True)` | `backend/app/db/base.py:26–32`（A） |
| 目标版本差异 | V1.2 目标为 Python 3.13.16；仓库当前 3.14.x | 需求 P3a/P3b、T3（待确认） |

### 1.5 缺口与对应任务

| 缺口 | 需求描述 | 本文任务 | 本轮处理 |
|---|---|---|---|
| G1 | 无作答数据；落 PostgreSQL 并纳入 Alembic | T01 | 新建 3 张表并迁移 |
| G2 | 无“接收整卷作答→判分→落库”能力 | T03–T06 | 新增 API-1 + 判分服务 |
| G3 | 无交卷后受保护内容读取 | — | **冻结（FZ1）**，待 P1/P6 |
| G4 | 无结果页 | — | **冻结（FZ3）**，前端轮次 |
| G5 | 字母空间风险：判分与回显须同空间换算 | T05 | 复用映射函数，单一换算点 |
| G6 | 解析可能为空（`explanation_text` NOT NULL 但可为空串） | T05 | 快照按原值保存空串，不占位 |
| G7 | 批次版本化：结果按提交时快照固化 | T01、T05 | 快照列 + `import_batch_id` |
| **L-G8** | 幂等短路顺序（BR-19d）与拒绝标记（BR-20）未实现 | T03、T06 | 标记表 + 固定判定顺序（本地编号，避免与需求审查历史 G8 混淆） |
| **L-G9** | 错误码/请求体/键形式等契约细节未定 | T02 | 第 2.4/2.7 节定稿；争议项登记 1.6 |
| **L-G10** | 验收数据与账号不具备（P2） | T10 | 从受控证据包导入；不具备时标 BLOCKED |

### 1.6 待确认项与“默认执行口径”

> **状态更新（2026-11-10）**：本表建议口径已经负责人确认（D-01/02/03/04/05/06/07/08/09/10/12/13/14/15/16/17/18/19/20/21），D-14 已由需求 v0.21 修订关闭；表内"待签认/待拍板"字样保留为历史描述，实际以附录 E.12 为准。

> 原则：未决项不妨碍文档评审和方案准备；实际开工仍受 1.3.4 门禁约束。**默认口径必须显式、可回退并标注“待确认”**；默认值被否决时按“影响”列回改文档与后续实现，不静默改语义。

| 编号 | 事项 | 来源 | 本轮默认口径 | 影响 | 确认人 |
|---|---|---|---|---|---|
| D-01 | “内容版本不一致”“同卷限次”“同键不同内容”用什么 HTTP 状态码 | 需求 §8.4/§8.5“409/429/413 本轮不定义” | **建议统一用 400 + 明确中文 `msg`**；不引入 409 | API 契约、脚本断言；若改 409 须回写需求 §8.5 与本文 2.7 | 负责人（待签认） |
| D-02 | 幂等键传递位置与格式 | U7/T7 | **建议**：请求头 `Idempotency-Key`，值必须是 **UUIDv4 规范字符串**（36 字符，`8-4-4-4-12` 十六进制）；不接受任意 8–64 字符。待签认（T7 授权范围内） | 契约、EX-20 可构造性 | 负责人/开发人 |
| D-03 | attempt 对外标识 | BR-22 vs DC-9 | 对外用 `attempt_code`（UUID），**不暴露数据库主键**；内部 `id` 仅库内使用 | 契约、结果寻址 | 负责人/开发人 |
| D-04 | attempt 对试卷/批次/学生外键的删除策略 | 7.7、DC-7 | 学生/试卷/批次均 `ON DELETE RESTRICT`；逐题快照不设题目外键 | 未来“删除试卷/批次”须先处理 attempt | 负责人 |
| D-05 | 同时具备 admin+student 角色的账号 | BR-09/BR-10 | **`is_admin` 为真即 403**；纯 student 才允许 | 边缘账号行为 | 负责人 |
| D-06 | 文档路径与编号（T2） | U1/T2、v0.20 §14.2 | 暂存 `docs/development/attempt-system/`，任务编号 `T01–T10`（与模块二 T01–T09 不冲突的本地编号）；**v0.20 要求写开发文档前定，现为默认值待确认** | 入仓位置、PR 引用 | 负责人（待确认） |
| D-07 | 结果读取（API-2）启用时点 | P1、P6、v0.20 §14.2 | **D1–D9/R1–R4/D4 已确认（书面件待补）；D10/D11 待拍板**；1.5 例外生效条件未满足 → **本轮不实现、不出卡**；P1 三要件 + P6 满足后另开轮次 | 范围与验收矩阵冻结项 | 负责人 |
| D-08 | D10（解析引用正文）与 D11（逐题反馈/限次）最终拍板 | 需求 2.4/12.2、v0.20 §14.2 | **D1–D9/R1–R4/D4 已确认（书面件待补）；D10/D11 仍待拍板**。本文建议 D10=B、D11=A 仅作草稿；改 B 须回改 2.4.2、2.6.3、BR-18a 与相关矩阵 | 判分反馈范围、V-15b、限次 | 负责人 |
| D-09 | T11 解析检测规则是否入内容检查 | 需求 13 T11 | **不在作答系统实现**；由题库内容治理负责，未定前 V-15b 标 BLOCKED | 内容治理排期 | 负责人 |
| D-10 | Python 版本（P3b） | U3/T3、v0.20 §14.2 | **建议本轮固定仓库 3.14.x 复验（P3a），不迁移 3.13.16**；**v0.20 要求写开发文档前定，现为默认值待确认** | 验收环境记录 | 负责人（待确认） |
| D-11 | 可访问试卷与账号来源 | P2/T4 | 从受控 16 表工作簿 + 音频导入；**不得伪造数据**；无数据则 T10 与 V-E 系列 BLOCKED | 端到端可执行性 | 验收人 |
| D-12 | 是否存在项目级 `AGENTS.md`/等效规则 | 用户要求 | 按 0.4 检索结论执行；若有请补路径 | 全文规范依据 | 负责人 |
| D-13 | “空卷也不得为空”的准确含义 | AS-01/AS-02、5.5a | 按“**答题集合为空时，整卷题目集合仍不得为空**”理解；`answers` 缺失=422，`answers=[]`=合法空卷 | T02、V-02、M-02 | 负责人 |
| D-14 | V-21“不同键并发→两条独立记录”/V-E4 与 BR-18a“1.5 例外生效前限 1 次”冲突 | 11.4/10.4 vs BR-18a/D11 | **建议修订需求**：给 V-21/EX-23 加“P1 生效后”限定；V-E4 拆成“当前限次拒绝”与“P1 后两条记录”两行。修订前 M-32/M-41 标 **BLOCKED**，不得按默认口径判 PASS/PARTIAL | M-32、M-41、V-21/V-E4 判定 | 负责人 |
| D-15 | 判定链中准入、身份分类与版本校验的先后 | BR-19d、AS-07、5.5a | **建议**：结构校验 → 准入 → 身份/版本 → 限次；准入优先：试卷不可访问一律 404+access 标记（含不存在/旧批次/非法身份请求）；仅在可访问后区分 E04/E07 | T04/T06、M-21/M-25/M-29；若改为身份优先需回改顺序与用例 | 负责人（待签认） |
| D-16 | 身份分类的优先级（混合身份集合） | 5.5a、EX-09b | **建议**：可访问时任一旧批次身份 → E04（400+version 标记）优先；否则任一他卷/不存在 → E07（400，无标记）；否则当前集合不完整/真子集 → E07；全部当前 → 通过。依据 EX-09b“任一身份属旧批次→版本不一致” | T04、M-22/M-25/M-37/M-38 | 负责人（待签认） |
| D-17 | 永久拒绝标记的容量与清理 | 7.6、BR-20、M-09 | 本轮接受“按键一行、永久保留、无限流”的风险，登记在 2.9；清理/限流须另开需求（不引入 429） | 长期运营与容量 | 负责人 |
| D-18 | 同键但请求体不可解析时的重试语义 | BR-19a/19d | 回放以“请求可解析”为前提：body/schema 非法 → 422，不查幂等记录；可解析的同键请求才进入短路 | T03/T06、EX-22 边界 | 开发人（T7 授权） |
| D-19 | 249 估分在“恰好 .5”附近的取整边界 | BR-16a、2.5.4 | 按 `floor(raw+0.5)`（非负数 half-up）；若负责人认为应改为其他规则，须回改 2.5.4、T05/T08 与示例 | T05、M-04 | 负责人 |
| D-20 | EX-28 数据异常（映射/题目/音频）是否等同 AS-07 写永久标记 | EX-28、AS-07、BR-01 | **建议：数据异常按 404 处理但不写永久标记**（记录日志；修复后同键可重试）；仅 `student_access` 不可访问时写 `paper_not_accessible` 标记。待负责人签认；若否决则回改 2.1.1/2.6.2/2.7.2/T06-A13/M-29a/M-29b/M-29c | T04/T06、M-29a/M-29b/M-29c | 负责人（待签认） |
| D-21 | 框架无法保证“401 先于 body 校验”时的裁定 | AS-16、BR-11、T06-A12 | **建议不设 422 例外**：鉴权必须前置（路由级依赖/中间件）；若确认框架不可控，须负责人书面裁定，**不得默认接受 422** | T06-A12、V-R1 | 负责人（待签认） |

> 需求文档 §12.2 的 U1–U7、§13 的 T1–T11 中，未在上表展开的项（如 U4/U5 结果页音频与“再答一次”、U6 删除记录、T5 B16 补做、T6 标注状态可构造性、T10 验收人数）不影响本轮 A/C/D 开发；在验收矩阵中按冻结/`BLOCKED` 处理。

### 1.7 需求、任务、验收的对应原则

1. **一条需求至少落一个任务，一条任务至少对一条验收**；无法落到任务的需求，必须标“冻结/不适用”并写明原因（见 1.3.2）。
2. **验收不拿“整体跑通”替代逐项判定**（需求 11.1）；每个矩阵行独立给出 PASS/PARTIAL/FAIL/BLOCKED。
3. **不把现有实现写成目标设计**：第 1.4 节只写已核对事实；第 2 节的设计若与现状不同，明确写“新增/改动”。
4. **不预填测试结果**：本文第 6 节模板初始为空；任何 PASS 都必须附命令、输出、版本与证据位置。

---

## 2 开发方案

### 2.1 目标流程

#### 2.1.1 提交与判分主流程（API-1）

```text
[学生] POST /api/v1/listening-papers/{exam_paper_id}/attempts
  Header: Authorization: Bearer <token>
  Header: Idempotency-Key: <UUIDv4>
  Body:   { loaded_question_ids: [...], answers: [{question_id, selected_option}] }
        │
        ▼
1 认证（get_current_user）──────── 失败 → 401
        │
        ▼
2 角色（学生；管理员→403）
        │
        ▼
3 解析并规范化请求（schema + Header 格式）── 失败 → 422/400（不落库、不留标记）
        │
        ▼
4 计算 request_fingerprint（v1 规范化串的 SHA-256）
        │
        ▼
5 键识别：先取 (student_id, attempt_key) 维度 advisory xact lock，再查
   ├─ 已有成功 attempt：
   │    ├─ 指纹相同 → 直接返回原结果（BR-19a；不再做内容/准入核对）
   │    └─ 指纹不同 → 400 键冲突（BR-19b；不落库、不留标记）
   ├─ 已有永久拒绝标记 → 返回同一拒绝结论（BR-20；不重新核对）
   └─ 无记录 → 进入首次提交
        │
        ▼
6 首次提交业务校验（顺序固定）
   6.1 结构/语义校验（重复、answers⊆loaded、loaded 非空、字母）→ 400 E07，不落库、不留标记
   6.2 准入判定 student_access（提交时点）→ 不可访问：提交 access 标记 → 404
       （**准入优先**：不再区分身份/版本）
   6.2b 数据/音频完整性校验（仅在可访问后；EX-28）→ 404，**不写永久标记**（D-20 建议口径），
       记录数据异常；修复后同键可重试
   6.3 可访问时的身份与集合校验（5.5a，纯读；优先级见 D-16）：
       任一“本卷旧批次”身份 → 提交 version 标记 → 400 E04“内容已更新”（优先）；
       否则任一“他卷/不存在”身份 → 400 E07，不落库、不留标记；
       否则全部当前批次但集合不完整/真子集 → 400 E07，不落库、不留标记
   6.4 同卷限次（1.5 例外生效前）→ 已有成功 attempt：400 E08“仅允许提交一次”，不落库、不留标记
        │
        ▼
7 判分与快照（纯函数，逐题遍历当前批次整卷）
   · 选项按本套映射组装 → 原卷字母空间
   · 正确答案换算为原卷字母
   · 逐题 is_correct；selected=null 表示未作答且计错
   · 汇总正确题数/整数正确率/练习估分（不可用则 null）
        │
        ▼
8 单事务写入 attempts + attempt_answers → COMMIT
   ├─ 并发同键唯一冲突 → 回滚后重读，按 BR-19a 返回同一结果
   └─ 提交前其他异常 → 回滚并安全记录 → 500（无半成品）；COMMIT 结果未知 → 500，
      保持原键重试，按持久化记录恢复；不承诺 0 行（见 2.6.4）
        │
        ▼
[学生] 200 { attempt_code, question_count, correct_count, correct_rate,
              practice_score{...} }
```

#### 2.1.2 结果读取（API-2）：本轮冻结，不设计

API-2 不在本轮范围，本文**不为它设计路径、字段、状态码或查询逻辑**。唯一需要记录的是生效条件（1.5(4)、P1 三要件、P6 满足）与冻结登记（4.11 FZ1）；解冻后另开轮次、另写开发文档与验收矩阵，不在本文扩展。

> 本节不再保留“查询时准入如何实现”的草案，以避免把冻结项写成既成设计。

### 2.2 模块职责与文件变更面

#### 2.2.1 新增文件（建议命名，遵循仓库规范）

| 文件 | 职责 | 任务 |
|---|---|---|
| `backend/app/db/models_attempt.py` | 3 张 ORM 模型：`Attempt`、`AttemptAnswer`、`AttemptRejection` | T01 |
| `backend/alembic/versions/0005_attempt_system.py` | 建 3 表 + 索引/约束；`downgrade()` 逆序删除 | T01 |
| `backend/app/schemas_attempts.py` | API-1 请求/响应模型与字段约束（422/400 的路由映射由 T06） | T02 |
| `backend/app/repositories/attempt_keys.py` | 幂等键/拒绝标记/限次计数/两把 advisory lock/请求指纹 | T03 |
| `backend/app/repositories/attempt_content.py` | 当前批次整卷读取、严格映射校验、身份分类、答案校验 | T04 |
| `backend/app/services/grading.py` | 纯判分：字母空间换算、逐题事实、正确率、249 估分；无数据库依赖 | T05 |
| `backend/app/services/attempts.py` | 提交编排、事务恢复、响应组装；异常安全记录及转换，避免原始数据库错误进入全局日志 | T06 |
| `backend/app/api/attempts.py` | API-1 路由；`require_student` 依赖；Header 解析 | T06、T07 |
| `backend/tests/test_attempt_grading.py` | 判分/估分/舍入/空解析/重排题纯函数用例 | T05、T08 |
| `backend/tests/test_attempt_api.py` | API-1 正常、异常、权限、幂等、限次、原子性用例 | T06、T08 |
| `backend/tests/test_attempt_regression.py` | 模块一/模块二回归与顺序断言 | T07、T08 |
| `backend/scripts/acceptance_attempt.py` | 真实服务 + 真实库端到端脚本（逐项 PASS/FAIL、退出码） | T09 |

#### 2.2.2 允许的最小改动（不改既有语义）

| 文件 | 改动 | 理由 | 回归要求 |
|---|---|---|---|
| `backend/app/api/deps.py` | 新增 `require_student`（先 401 后 403；`is_admin` 优先拒绝） | 复用鉴权体系，不在路由内手写角色判断 | 既有鉴权用例全绿 |
| `backend/app/repositories/listening.py` | 新增严格版 `paper_letter_for(question, presentation)` / `paper_options_for(...)`（映射缺失、键/值非 A–D 排列、反查不到 → 抛 `PaperUnavailable`）；模块二既有 `_options_for`/`_paper_correct_option` 保留原兜底行为供既有接口使用，不作语义修改 | 避免作答侧复用“静默兜底”导致跨字母空间错判；旧接口回归不变 | 模块二既有用例全绿（12+11） |
| `backend/app/main.py` | 挂载 `attempts.router`；现有异常外壳保持不变 | 作答服务在异常边界先脱敏并转换 `AppError`，不得将带 SQL 参数的异常交给全局原始日志处理 | 启动/OpenAPI 正常，T06-A15/T07-A7 验证最终日志 |
| `backend/tests/conftest.py` | 仅在必要时新增夹具（如“已确认可见试卷”构造辅助）；**不改建库/迁移/种子逻辑** | 复用既有测试环境 | 全部既有用例全绿 |

> **禁止**：在 `listening_papers.py` 增加“已交卷返回答案”分支；在模块二模型加“是否已作答”；修改 `0001–0004`；在接口层写死题目或答案；用内存/JSON 冒充数据库结果。

#### 2.2.3 调用关系与依赖方向

```text
api/attempts.py
  ├─ api/deps.py（CurrentUser / require_student / get_db）
  ├─ schemas_attempts.py（请求/响应）
  └─ services/attempts.py（编排）
        ├─ repositories/attempt_keys.py（键、标记、限次、锁）
        ├─ repositories/attempt_content.py（整卷、映射、身份、答案）
        │     └─ repositories/listening.py（student_access / get_current_batch）
        └─ services/grading.py（纯函数，不触库）
```

依赖方向单向：`api → services → repositories → db`；`grading` 被 `services/attempts` 调用但自身不反向依赖。禁止 `repositories` 调用 `api`，禁止 `grading` 直接查库（便于单测）。
### 2.3 数据契约

#### 2.3.1 总原则

1. 只新增表，不改既有表；新表继承 `backend/app/db/base.py:19` 的 `Base` 与 `NAMING_CONVENTION`（`db/base.py:10–16`）。
2. 主键 `id BIGINT` 自增；时间列 `TIMESTAMPTZ`（`DateTime(timezone=True)`）+ UTC；布尔用 `is_` 前缀；表名复数 `snake_case`。
3. `attempt` 提交后**只读**：不设 `updated_at`，应用层不提供 UPDATE/DELETE。
4. 快照自足：逐题事实保存题干、选项、答案、解析、题型，读取时不依赖题库当前值（BR-23、7.2）。
5. 不向学生暴露数据库主键与内部状态（DC-9）：对外只用 `attempt_code` 与原卷题号。
6. **成功与拒绝的引用完整性不同**：`attempts` 是对已存在试卷的正式记录，保留对 `users/exam_papers/import_batches` 的 `RESTRICT` 外键；`attempt_rejections.exam_paper_id` 只作追溯、不设外键，确保“试卷不存在”的准入拒绝也能落标记。

#### 2.3.2 表 `attempts`（一次成功提交一行）

| 列 | 类型 | 空 | 默认 | 约束/说明 |
|---|---|---|---|---|
| `id` | `BIGINT` | 否 | 自增 | 主键；**内部使用**，不返回 |
| `attempt_code` | `VARCHAR(36)` | 否 | — | `UNIQUE`；`uuid4()` 字符串；**对外唯一标识**（BR-22） |
| `student_id` | `BIGINT` | 否 | — | `FK users(id) ON DELETE RESTRICT`（DC-7：不因账号删除级联删记录） |
| `exam_paper_id` | `BIGINT` | 否 | — | `FK exam_papers(id) ON DELETE RESTRICT`（不因试卷删除级联删记录） |
| `import_batch_id` | `BIGINT` | 否 | — | `FK import_batches(id) ON DELETE RESTRICT`；**提交时批次标识**，仅追溯，不参与准入 |
| `attempt_key` | `VARCHAR(64)` | 否 | — | 幂等键原文；与 `student_id` 组成唯一键 |
| `request_fingerprint` | `VARCHAR(64)` | 否 | — | 规范化请求的 SHA-256 hex；用于 BR-19a/19b |
| `submitted_at` | `TIMESTAMPTZ` | 否 | `now()` | 提交时间，UTC（BR-27） |
| `question_count` | `INTEGER` | 否 | — | 提交时整卷题数；`CHECK (question_count > 0)` |
| `correct_count` | `INTEGER` | 否 | — | `CHECK (correct_count BETWEEN 0 AND question_count)` |
| `correct_rate` | `SMALLINT` | 否 | — | 整数百分比；`CHECK (correct_rate BETWEEN 0 AND 100)`（BR-16/R4） |
| `practice_score` | `SMALLINT` | 是 | — | 0–249；不可用时为 `NULL`；`CHECK (practice_score IS NULL OR practice_score BETWEEN 0 AND 249)`（BR-16a） |
| `score_breakdown` | `JSONB` | 否 | — | 题型分组快照、规则版本、可用性与原因；**始终写入**（不可用时 `available=false`、`groups` 可为空，但 `reason/rule` 必须保留），回放不重新计算（7.2 S-9） |

约束与索引（显式命名，便于迁移回退）：

| 名称 | 类型 | 定义 | 用途 |
|---|---|---|---|
| `uq_attempts_student_attempt_key` | UNIQUE | `(student_id, attempt_key)` | DC-3：同一学生同键至多一条成功 |
| `ck_attempts_question_count_positive` | CHECK | `question_count > 0` | 防止空卷绕过内容检查 |
| `ck_attempts_correct_count_range` | CHECK | `correct_count BETWEEN 0 AND question_count` | 汇总一致性 |
| `ck_attempts_correct_rate_range` | CHECK | `correct_rate BETWEEN 0 AND 100` | R4 |
| `ck_attempts_practice_score_range` | CHECK | `practice_score IS NULL OR practice_score BETWEEN 0 AND 249` | BR-16a |
| `ix_attempts_student_paper` | INDEX | `(student_id, exam_paper_id)` | BR-18a 限次计数 |
| `ix_attempts_paper` | INDEX | `(exam_paper_id)` | 审计/追溯 |
| `ix_attempts_submitted_at` | INDEX | `(submitted_at)` | 按时间排查 |
| `uq_attempts_attempt_code` | UNIQUE | `(attempt_code)` | 对外唯一标识 |
| `fk_attempts_student_id_users` | FK | `student_id → users(id) ON DELETE RESTRICT` | 不因账号删除级联删记录 |
| `fk_attempts_exam_paper_id_exam_papers` | FK | `exam_paper_id → exam_papers(id) ON DELETE RESTRICT` | 不因试卷删除级联删记录 |
| `fk_attempts_import_batch_id_import_batches` | FK | `import_batch_id → import_batches(id) ON DELETE RESTRICT` | 批次仅追溯 |

> **约束命名口径（重要）**：上表“名称”是**数据库侧全名**。模型侧 `CheckConstraint(name=...)` 只写**短名**（如 `question_count_positive`），由 `NAMING_CONVENTION` 的 `ck_%(table_name)s_%(constraint_name)s` 生成全名；迁移侧用 `op.f("ck_attempts_question_count_positive")` 写全名。若模型误传全名，会生成 `ck_attempts_ck_attempts_...` 双层前缀，导致 `alembic check` 漂移。**UNIQUE/INDEX 不套用 CHECK 的短名规则**：本仓库 `uq` 模板不使用 `constraint_name`；显式 `UniqueConstraint(name=...)`、`Index(name=...)` 使用表格列出的数据库最终全名，迁移侧保持相同名称。仅在确认模板会生成同一最终名时才省略显式名称；参照 `models_listening.py` 并用 T01-A6 核对。
>
> **时间口径**：`submitted_at` 由应用侧显式写入 `datetime.now(timezone.utc)`（快照时点确定、响应无需回查），DB `server_default=now()` 仅作兜底；测试断言存储值与响应均为 UTC。

> **为什么不用数据库自增 `id` 对外**：DC-9 要求不新增向学生暴露的主键；同时 `attempt_code` 可避免枚举。日志与追溯使用 `attempt_code`，内部关联使用 `id`。

#### 2.3.3 表 `attempt_answers`（逐题事实 + 判分快照）

| 列 | 类型 | 空 | 默认 | 约束/说明 |
|---|---|---|---|---|
| `id` | `BIGINT` | 否 | 自增 | 主键 |
| `attempt_id` | `BIGINT` | 否 | — | `FK attempts(id) ON DELETE CASCADE`（仅同一聚合内允许级联；应用不删 attempt） |
| `question_no` | `INTEGER` | 否 | — | 提交时**原卷题号**；`CHECK (question_no > 0)`；S-2 |
| `question_id` | `BIGINT` | 否 | — | 题库题目身份（仅追溯/换批检测）；`CHECK (question_id > 0)`；**不设外键**，避免题库清理影响快照 |
| `passage_type` | `VARCHAR(32)` | 否 | `''` | 提交时篇章类型快照；用于估分与 S-9 |
| `question_text` | `TEXT` | 否 | — | S-3 题干快照 |
| `option_a`…`option_d` | `TEXT` ×4 | 否 | — | S-4：按**原卷 A–D 顺序**的选项文本快照 |
| `correct_option` | `VARCHAR(1)` | 否 | — | 提交时**原卷字母**；`CHECK (correct_option IN ('A','B','C','D'))`；S-5 |
| `selected_option` | `VARCHAR(1)` | 是 | — | 学生所选**原卷字母**；`NULL`=未作答；`CHECK (selected_option IS NULL OR selected_option IN ('A','B','C','D'))`；S-7 |
| `is_correct` | `BOOLEAN` | 否 | — | 服务端判定；未作答一律 `FALSE`；S-7 |
| `explanation_text` | `TEXT` | 否 | — | S-6；允许空串（G6/BR-25），不做占位 |

约束与索引：

| 名称 | 类型 | 定义 | 用途 |
|---|---|---|---|
| `uq_attempt_answers_attempt_question_no` | UNIQUE | `(attempt_id, question_no)` | 题号不重复 |
| `uq_attempt_answers_attempt_question_id` | UNIQUE | `(attempt_id, question_id)` | 同一题不重复作答（EX-19 的库内兜底） |
| `ck_attempt_answers_correctness` | CHECK | `is_correct = (selected_option IS NOT NULL AND selected_option = correct_option)` | 判分一致性，防止“有记录但结论矛盾” |
| `ck_attempt_answers_question_id_positive` | CHECK | `question_id > 0` | 题目身份合法 |
| `ck_attempt_answers_question_no_positive` | CHECK | `question_no > 0` | 原卷题号合法 |
| `ix_attempt_answers_attempt` | INDEX | `(attempt_id)` | 按 attempt 读取 |
| `ck_attempt_answers_correct_option_domain` | CHECK | `correct_option IN ('A','B','C','D')` | 原卷字母域 |
| `ck_attempt_answers_selected_option_domain` | CHECK | `selected_option IS NULL OR selected_option IN ('A','B','C','D')` | 允许 NULL=未作答 |
| `fk_attempt_answers_attempt_id_attempts` | FK | `attempt_id → attempts(id) ON DELETE CASCADE` | 仅同一聚合内级联 |

> **字母空间**：`correct_option` 与 `selected_option` 必须都在**本套原卷字母空间**。题库字母只用于换算中间值，不落库、不返回、不参与比较（BR-13/14、AS-03）。

#### 2.3.4 表 `attempt_rejections`（永久幂等拒绝标记）

| 列 | 类型 | 空 | 默认 | 约束/说明 |
|---|---|---|---|---|
| `id` | `BIGINT` | 否 | 自增 | 主键 |
| `student_id` | `BIGINT` | 否 | — | `FK users(id) ON DELETE RESTRICT` |
| `exam_paper_id` | `BIGINT` | 否 | — | **不设外键**：仅保存提交目标标识用于追溯；原因是“不存在的试卷 × 不可访问”也须能写永久标记，若设外键会因目标行不存在而写不进标记 |
| `attempt_key` | `VARCHAR(64)` | 否 | — | 被拒绝的键 |
| `request_fingerprint` | `VARCHAR(64)` | 否 | — | 首次拒绝时的请求指纹 |
| `rejection_kind` | `VARCHAR(32)` | 否 | — | `CHECK (rejection_kind IN ('paper_not_accessible','content_version_mismatch'))` |
| `detail` | `JSONB` | 是 | — | 内部定位信息（如不一致的题目身份），**不返回学生** |
| `created_at` | `TIMESTAMPTZ` | 否 | `now()` | 拒绝时间，UTC |

约束：`UNIQUE (student_id, attempt_key)`（`uq_attempt_rejections_student_attempt_key`）。

其余显式命名：`ck_attempt_rejections_rejection_kind_domain`（CHECK，`rejection_kind IN ('paper_not_accessible','content_version_mismatch')`）、`fk_attempt_rejections_student_id_users`（FK，`student_id → users(id) ON DELETE RESTRICT`）。

口径：

- 该表**不是作答记录**，不计入 attempt 数，不参与正确率/估分，不改变既有作答记录（7.6、7.8 第 3 条）。
- 仅 AS-07 与 EX-09b 作为写标记的业务原因；参数非法、格式错误不写，服务端故障不另行创建标记。若创建标记的 COMMIT 确认丢失，标记可能已持久化，不能承诺“不存在”，按 2.6.4 同键恢复（BR-20、R7-02）。
- 永久保留，本轮不清理；若将来清理须保证旧键不可复用（7.6）。
- 同键重试**短路返回同一拒绝结论**，不再做内容核对与准入判定（BR-19d）；回放状态码由 `rejection_kind` 固定映射：`paper_not_accessible→404`、`content_version_mismatch→400`。
- `request_fingerprint` **仅作审计/排查**，不参与回放判定（回放只按 `(student_id, key)`）；不要求未来新增拒绝类型时依赖历史指纹。
- **跨表互斥的保障层级**：数据库无法对 `attempts` 与 `attempt_rejections` 建跨表唯一约束；互斥由应用层“键级 advisory lock + 短路顺序 + 各自唯一约束”保证。直接 SQL、绕过服务的写入不在保障范围；测试须加“同键两表不同时存在”的 SQL 断言，运维发现双行按数据缺陷处理。
- **无外键的副作用**：`exam_paper_id` 允许不存在的值（为 AS-07“按不存在处理”留标记），因此不能用外键校验标记目标；仅接受已认证学生对可解析请求写入，每键一行，容量风险见 D-17/2.9。

#### 2.3.5 数据关系与保留

```text
users(id) ──┐
exam_papers(id) ──┤        attempts (1) ──< attempt_answers (N)
import_batches(id) ──┘            │
                                  └── (逻辑关联) attempt_rejections：同 student+key 的拒绝事实，独立存储
```

- `attempt` 与 `attempt_answers` 为同一聚合：一次事务写入，条数恒等于 `question_count`（DC-2）。
- 不级联删除：不随试卷下线、换批次、内容检查变化删除（DC-7）；不写模块二既有表（DC-8）。
- 本轮不提供删除能力；清理策略不在本轮（7.6）。
- 不记录可见性/检查/标注状态：准入在每次提交时重算（7.1 “不写入”项）。
- **DC-2 的保障层级**：逐题条数=题数由应用层单事务写入 + T06/T08 测试保障，**不设数据库延迟约束/触发器**（本轮不引入额外 DDL 复杂度）；任何“条数不等”视为实现 FAIL。
- **未来删除风险（D-04/L-04）**：`attempts` 对 `users/exam_papers/import_batches` 使用 `RESTRICT`，当前代码没有删除用户/试卷/活跃批次的能力（`import_module2.py` 只清理非 active 草稿），风险低；若将来新增删除能力，必须先处理相关 attempt，并在迁移/运维说明中写明“有作答记录的父行不可直接删除”。

### 2.4 接口契约

#### 2.4.1 通用约定

| 项 | 约定 |
|---|---|
| 前缀 | `/api/v1` |
| 认证 | `Authorization: Bearer <access_token>`（复用模块一登录） |
| 响应外壳 | 沿用 `app/core/errors.py`：成功 `{code:200,msg,data}`；失败 `{code:<HTTP 状态>,msg,data:null}` |
| 字段命名 | `snake_case`；时间 ISO 8601（UTC） |
| 角色 | API-1 仅学生；管理员 403；未认证 401 |
| 本套字母 | 请求/响应中的选项字母一律为**本套原卷展示字母**；调用方无需换算 |
| 幂等键 | 请求头 `Idempotency-Key`；值必须是 **UUIDv4 规范字符串**（36 字符，`8-4-4-4-12` 十六进制），不接受任意 8–64 字符 |
| 分页 | 无（本轮无列表接口） |
| 版本兼容 | 新增接口，不改变既有接口；API-2 未实现（冻结） |
| 宽松度 | 请求体**多余字段忽略**（Pydantic 默认）；选项字母**严格大写**，小写 422；不做 413 请求体上限语义（由部署层/代理限制） |
| 回放标识 | 同键回放与首次成功返回**同一结构**，本轮**刻意不加**“replay”标识（不改变既有外壳）；如后续需要可观测量，另加响应头并版本化契约 |

#### 2.4.2 API-1：提交整卷作答

| 项 | 内容 |
|---|---|
| 编号 | API-1（需求 §8.1） |
| 方法/路径 | `POST /api/v1/listening-papers/{exam_paper_id}/attempts` |
| 角色 | 仅学生；`is_admin` 为真 → 403 |
| 前置 | 已登录；**提交时**试卷满足“学生可访问”；`loaded_question_ids` 与提交时当前批次整卷集合一致 |
| 请求头 | `Authorization`、`Content-Type: application/json`、`Idempotency-Key` |
| 成功 | 200；服务端判分并持久化；返回标识、题数、正确题数、正确率、练习估分（逐题正误本轮不返回，D11=A） |
| 失败 | 401/403/404/400/422/500；语义见 2.7 |
| 原子性 | 失败无半成品；同键重试不新增（BR-21、BR-19c） |

**请求体**（JSON）：

| 字段 | 类型 | 必填 | 约束/说明 |
|---|---|---|---|
| `loaded_question_ids` | `array[strict int]` | 是 | 页面加载时整卷**全部**题目身份（`question_id`）；字段必须存在；**不得为空**（服务层判空→400 E07）；`answers` 可为空数组（EX-14/AS-02）；元素 `>0`、`≤2^63-1`，不得重复；**禁止字符串/浮点被静默转 int** |
| `answers` | `array[object]` | 是 | **字段必须存在**，可为空数组；为空表示全部未作答（EX-14/AS-02） |
| `answers[].question_id` | `strict int` | 是 | 必须属于 `loaded_question_ids` 且属于当前批次；`>0`、`≤2^63-1` |
| `answers[].selected_option` | `string` | 是 | 仅 `A`/`B`/`C`/`D`，**原卷字母**；格式不符由 schema 层返回 422 |

> **口径说明（需确认）**：AS-01 的“空卷也不得为空”按“**答题集合为空时，整卷题目集合仍不得为空**”理解；`answers` 整体缺失属格式错误（422），显式 `[]` 才是合法空卷。此理解登记为 D-13，若负责人另有解释需回改 T02 与矩阵 V-02。

**请求示例**（25 题省略为示意，非合法 JSON）：

```json
{
  "loaded_question_ids": [101, 102, 103, "…共 25 个"],
  "answers": [
    {"question_id": 101, "selected_option": "B"},
    {"question_id": 103, "selected_option": "A"}
  ]
}
```

**成功响应**（200）：

```json
{
  "code": 200,
  "msg": "提交成功",
  "data": {
    "attempt_code": "0f5c2a1e-9d4b-4f6a-9c77-2b1e8a3d5c40",
    "exam_paper_id": 1,
    "submitted_at": "2026-11-08T06:30:00Z",
    "question_count": 25,
    "correct_count": 24,
    "correct_rate": 96,
    "practice_score": {
      "available": true,
      "value": 235,
      "max": 249,
      "label": "练习估分，非官方成绩",
      "reason": null
    }
  }
}
```

| 响应字段 | 类型 | 说明 |
|---|---|---|
| `attempt_code` | string(UUID) | 对外唯一标识（BR-22）；后续结果读取（冻结）以此为寻址键 |
| `exam_paper_id` | int | 本次试卷 |
| `submitted_at` | string | UTC ISO 8601 |

> **序列化口径（T01–T03 验收回改）**：Pydantic v2 实际输出以 `Z` 结尾（如 `2026-11-08T06:30:00Z`）；`+00:00` 同样属合法 UTC ISO 8601，两者等价，验收不因此判差异。
| `question_count` | int | 提交时整卷题数（分母） |
| `correct_count` | int | 正确题数 |
| `correct_rate` | int | 0–100 整数百分比，四舍五入（R4、BR-16） |
| `practice_score.available` | bool | 是否可输出练习估分 |
| `practice_score.value` | int/null | 0–249；`available=false` 时为 `null` |
| `practice_score.max` | int | 固定 249 |
| `practice_score.label` | string | 固定“练习估分，非官方成绩” |
| `practice_score.reason` | string/null | 不可用原因：`not_standard_25`/`question_type_missing`/`type_count_mismatch`/`unknown_type` |

> **不返回**：逐题正误、逐题所选字母、答案、解析、听力正文、批次/状态、数据库主键、内部题目身份列表。逐题事实仍落库，供 O3 只读 SQL 追溯；不因“不返回”而不落库。D11=A 下“仅汇总”即不返回逐题项，本文**不新增** `feedback_scope` 等需求未要求的字段。
>
> **ID 类型契约（R7-01，取代 v0.7 的路径/JSON 统一 strict 方案）**：请求体 `loaded_question_ids[]`、`answers[].question_id` 使用 `JsonId = Annotated[int, Field(strict=True, gt=0, le=2**63-1)]`，拒绝 JSON 字符串、浮点、布尔、非正数及越界值（422）。普通 URL 路径参数使用 `PathId = Annotated[int, Path(gt=0, le=2**63-1)]`，允许 FastAPI/Pydantic 将路径数字文本转换为整数；合法 `/listening-papers/1/attempts` 必须通过参数解析。路径本轮沿用锁定版本的正常整数转换行为，不额外增加十进制文本格式限制；范围校验仍为正数且不超过 BIGINT 上限。`JsonId` 定义在 schema，`PathId` 定义在 API 路由，由 T06 验证 HTTP 行为。
>
> **实现示例（依赖均已在仓库中，未实现）**：
> `schemas_attempts.py`：`JsonId = Annotated[int, Field(strict=True, gt=0, le=2**63-1)]`；
> `api/attempts.py`：`PathId = Annotated[int, Path(gt=0, le=2**63-1)]`，其中 `Path` 来自 FastAPI；两处使用 `typing.Annotated`。T02 只验请求体模型；T06 必须在 FastAPI 0.143.0 / Pydantic 2.14.1 下同时验证合法路径、非法范围和请求体严格性。
>
> **估分不可用的表达**：`practice_score.available=false` 时 `value=null`，接口**不输出分数数值**（不是 0 分）；`reason` 仅用于机器区分不可用原因；前端应隐藏估分区而非显示 0。

#### 2.4.3 结果读取（API-2）：冻结，不设计契约

API-2 本轮**不实现、不出任务卡、不设计路径/字段/状态码**。解冻条件见 4.11 FZ1；解冻后另开轮次，另写契约与验收矩阵。任何“草案”都不应出现在本版，以避免冻结项被误当作实现依据。

#### 2.4.4 与模块二既有接口的兼容

- API-1 是新增路径，不改变既有 6 个接口的路径/方法/权限/响应/语义。
- 学生详情与音频的返回字段集合在交卷前后**完全一致**；不新增“已交卷”分支（AS-18、V-R2）。
- 作答系统只读模块二表；不写入可见性/检查/批次状态（DC-8、AS-18）。
- OpenAPI 文档新增一个 path；既有 schema 不变。

#### 2.4.5 权限矩阵（本轮）

| 操作 / 资源 | 未登录 | 学生 | 管理员 | 说明 |
|---|---|---|---|---|
| API-1 提交作答 | 401 | 允许（仅学生可访问试卷） | **403** | 401→403→404；管理员不进入 404 |
| API-2 读取结果 | — | — | — | **冻结（FZ1）**；不在本文设计契约 |
| 既有试卷列表/详情/音频 | 401 | 允许（仅可访问） | 允许 | 语义不变 |
| 既有管理员 3 接口 | 401 | 403 | 允许 | 语义不变 |
| 管理端统计/结果审计 | — | — | — | 本轮不做（OUT6） |

### 2.5 判分与练习估分算法

#### 2.5.1 输入与单一数据源

判分只使用**提交时**当前批次的以下数据（**批次边界固定**：以 6b 返回的 `batch` 为唯一来源，后续 6c 身份校验、第 7 步判分、`attempts.import_batch_id` 全部使用同一 `batch_id`，不再重新查询“当前批次”；题/映射/篇章均按该 `batch_id` 过滤读取。批次内容写入后不再变化。注意：PG 默认 READ COMMITTED 下同一事务的多条 SELECT 可能看到不同快照，因此**不宣称事务级一致性**；准入/可见性按每条语句时点判定，与 EX-25“按服务端处理时点”一致。如需更强隔离，可在 6b 对 `import_batches` 行 `FOR SHARE` 或使用 REPEATABLE READ，但本轮不默认引入）：

| 数据 | 来源 | 用途 |
|---|---|---|
| 当前批次 | `repositories/listening.py:34`（`get_current_batch`，结果在 6b 固定并贯穿全流程） | 题号/题目/映射/题型的版本边界 |
| 整卷题目与映射 | `questions` + `presentations`（按 `batch_id`） | 逐题身份、原卷题号、正确答案换算 |
| 选项文本 | `questions.option_a..d` + `presentation.option_letter_mapping` | 按原卷 A–D 顺序组装快照 |
| 题型 | `passages.passage_type` | 估分分组 |
| 解析 | `questions.explanation_text`（NOT NULL，可为空串） | 快照；本轮不返回 |

#### 2.5.2 字母空间换算（BR-13/14、AS-03）

对每题执行且只执行一次：

```text
题库答案字母 base_letter = question.correct_option
映射 mapping = presentation.option_letter_mapping（必须存在且为 A–D 排列；缺失/非法不得按恒等兜底，由 T04 严格校验按“不可访问”处理）
原卷答案字母 paper_letter = 反查 mapping 中值为 base_letter 的键（A–D）
展示选项 = [mapping['A'], mapping['B'], mapping['C'], mapping['D']] 对应的题库选项文本
判分：is_correct = (selected_option == paper_letter)
```

**禁止**：`selected_option == question.correct_option`；把题库字母写入 `attempt_answers.correct_option`；在响应中混用两套字母。映射非法/缺失时**不得判分**：按“数据异常”处理——404 E14，**不写永久标记**（D-20 建议口径，记录数据异常日志），不写 attempt；修复后同键可重试；不得跨空间判分或返回空壳。

**严格校验**：作答侧**不得直接复用**模块二 `_paper_correct_option` 的“映射非法时原样返回题库字母”兜底。T04 组装判分输入时一次性校验整卷：`paper.expected_question_count` 及其来源非空；`len(questions) == expected_question_count`；`len(presentations) == len(questions)` 且每题恰有一个有效映射；原卷题号完整覆盖 `1..expected_question_count`；每题 `presentation` 的映射键/值均为 A–D 排列、能由题库答案反查到唯一原卷字母。任一失败 → `PaperUnavailable` → 服务层返回 404 E14，**不写永久标记**（D-20 建议口径），**不判分、不写 attempt**。模块二既有调用点保持原行为，避免改变既有接口语义。

实现要求：只读复用 `backend/app/repositories/listening.py:138–172` 的映射逻辑，但由 T04 的**严格版包装**（`paper_letter_for`/`paper_options_for`）调用，不在判分服务中重写、也不直接使用带静默兜底的旧函数（见 2.2.2）；`grading.py` 接收已换算好的 `correct_paper_letter` 与选项文本。

#### 2.5.3 正确率（R4、BR-16）

- 分母 = 提交时整卷题数；未作答**计入分母并计错**（BR-15）。
- 结果 = 整数百分比，四舍五入（半入），**不带百分号、不是 0.96**。
- 用整数运算，禁止浮点与 `round()`（Python `round()` 是 banker's rounding，`round(2.5)==2`；需求只要求常规四舍五入）：

```text
correct_rate = (2 * correct_count * 100 + question_count) // (2 * question_count)   # 非负数的 half-up
```

| 输入 | 期望 |
|---|---|
| 24/25 | 96 |
| 25/25 | 100 |
| 0/25 | 0 |
| 1/3 | 33 |
| 2/3 | 67 |
| 1/8（12.5%） | 13；用于区分 half-up 与内置 `round(12.5)==12` |

#### 2.5.4 249 分练习估分（D4、BR-16a）

**题型与占比（官方听力题型，题库以篇章类型分组）**：

| 篇章类型（`passages.passage_type`） | 题量 | 权重 | 折算分（249 × 权重/35） |
|---|---|---|---|
| 短篇新闻 | 7 | 7 | 49.8 |
| 长对话 | 8 | 8 | ≈56.914 |
| 听力篇章 | 10 | 20 | ≈142.286 |
| 合计 | 25 | 35 | 249 |

**公式（精确有理数，最后一步 half-up 取整）**：

```text
raw = Σ_{g∈三组} (correct_g / total_g) × (weight_g / 35) × 249
practice_score = floor(raw + 0.5)        # 非负数；用 Fraction 精确计算，禁止 float
```

实现建议：`fractions.Fraction`（标准库，无新依赖）累加，再用整数 `(num*2 + den) // (2*den)` 实现 half-up；或直接用 `Decimal` + `ROUND_HALF_UP`。两种方式都必须在单测中固定断言。

**可用性判定（全部满足才输出估分）**：

| 条件 | 不满足时的 `reason` |
|---|---|
| 整卷题数 = 25 | `not_standard_25` |
| 恰好存在三类：短篇新闻=7、长对话=8、听力篇章=10 | `type_count_mismatch` |
| 每题都能取到非空 `passage_type` 且属于上述三类 | `question_type_missing` / `unknown_type` |
| 三组 `correct_g ≤ total_g` 且总正确数 = Σcorrect | 数据一致性失败 → 500（不输出错误估分） |

> **reason 判定顺序（固定，REV-05）**：`not_standard_25 → question_type_missing → unknown_type → type_count_mismatch`。先判“能否分组”（题数、缺失、未知类型），最后才判“分组数量是否符合 7/8/10”；避免把缺类型的试卷误报为 `type_count_mismatch`。题型名称必须来自题库受控枚举（现有 `passage_type` 可能含讲话/报道/讲座/其他，见 `docs/development/module-2/schema-alignment.md`）；未知类型**不得猜测归类**，按 `unknown_type` 处理并记录日志。

**示例（自检用，非实测）**：

| 场景 | 计算 | 期望 |
|---|---|---|
| 全对 | 7/7×49.8 + 8/8×56.914 + 10/10×142.286 = 249 | 249 |
| 全错 | 0 | 0 |
| 新闻 7/7、长对话 8/8、篇章 9/10 | 49.8 + 56.914 + 128.057 = 234.771 → half-up | 235 |
| 新闻 5/7、长对话 6/8、篇章 8/10 | 35.571 + 42.686 + 113.829 = 192.086 | 192 |

**展示与命名**：接口名 `practice_score`；标签固定“练习估分，非官方成绩”；与 `correct_rate` 分开呈现、不得互替（BR-17）；不按百分制归一，不宣称官方等值。

**快照 `score_breakdown` 结构（建议）**：

```json
{
  "rule": "cet-listening-249-v1",
  "total": 249,
  "groups": [
    {"passage_type": "短篇新闻", "question_count": 7, "correct_count": 7, "weight": 7},
    {"passage_type": "长对话", "question_count": 8, "correct_count": 8, "weight": 8},
    {"passage_type": "听力篇章", "question_count": 10, "correct_count": 9, "weight": 20}
  ],
  "available": true,
  "reason": null
}
```

不可用时 `available=false`，`groups` 保留已分组统计（可为空数组），`reason` 记录原因，**`score_breakdown` 仍必须写入**（列 NOT NULL），`practice_score` 为 `NULL`；不生成“0 分”冒充。响应中的 `practice_score.reason/available` 一律从该列派生，同键回放不重新计算，保证 S-9 快照与 E13 回放一致。

#### 2.5.5 空解析与未作答

- 解析为空串/仅空白：快照原样保存，空串仍为空串，空白字符串不自动 trim 或归一成空串；`NULL` 不作为来源（G6、BR-25）；本轮不返回，不写占位文案。
- 未作答：`selected_option = NULL`、`is_correct = false`；汇总中可按 `selected_option IS NULL` 区分“未作答”与“答错”（BR-15），逐题区分在本轮不返回（D11=A），库内可查（O3）。

### 2.6 幂等、并发与原子性

#### 2.6.1 幂等键与请求指纹

- **作用域**：`(student_id, attempt_key)`；不同学生使用相同键互不影响（避免跨用户串用）。
- **键合法性**：请求头缺失/非 UUIDv4/超长 → 400（EX-20；D-02）；不进入业务处理、不落库、不留标记。
- **键大小写**：十六进制大小写均接受（实现接受大写 A–F）；判定仍以“36 字符 8-4-4-4-12、版本位 4、变体位 8/9/a/b”为准，文档不额外限制大小写。
- **请求指纹**：对以下规范化串取 SHA-256（hex，64 字符）：

```text
v1|<exam_paper_id>|<loaded ids 升序逗号连接>|<answers 按 question_id 升序，"qid:letter" 逗号连接>
```

  - 只用于判断“同键是否同内容/同试卷”，不参与判分；
  - 规范化在 schema 校验通过后执行；参数非法请求只返回 400，不写指纹/标记；
  - 键本身不放入指纹（调用方生成，允许重试时保持键不变）。
  - **指纹边界**：只覆盖 `paper_id + 题目身份集合 + 作答字母`，能检测换批与内容不同的重试；**不检测**“同批次内原位修改题干/选项/答案/映射”（需求只要求按批次快照，当前口径可接受；增强需另开版本指纹机制）。

#### 2.6.2 判定顺序（BR-19d，固定）

| 步骤 | 判定 | 结果 | 是否落库/标记 |
|---|---|---|---|
| 1 | 认证 | 失败 → 401 | 否 |
| 2 | 角色（学生；admin→403） | 失败 → 403 | 否 |
| 3 | Header/请求体 schema | 失败 → 400/422 | 否 |
| 4 | 计算指纹 | — | 否 |
| 4.5 | **同键串行化**：`pg_advisory_xact_lock(1, lock_objid("attempt-key:{student_id}:{key}"))` | — | 否（仅锁） |
| 5a | 已有成功 attempt，指纹相同 | 200 返回原结果（BR-19a） | 否（不新增） |
| 5b | 已有成功 attempt，指纹不同 | 400 键冲突（BR-19b） | 否 |
| 5c | 已有永久拒绝标记 | 按 kind 返回原拒绝结论（BR-20） | 否 |
| 6a | 结构/语义校验（重复、`answers⊆loaded`、`loaded` 非空、字母） | 失败 → 400 E07（不写标记） | 否 |
| 6b | 准入 `student_access`（提交时点） | 失败 → 404 + `paper_not_accessible` 标记 | **是（标记）** |
| 6b2 | 数据/音频完整性（仅可访问后；EX-28，D-20 建议口径） | 失败 → 404，**不写永久标记**，记录数据异常；修复后同键可重试 | 否 |
| 6c | 身份分类（纯读，5.5a；仅可访问且完整性通过时；优先级 D-16） | **任一旧批次 → 400 E04 + `content_version_mismatch` 标记（优先）**；否则任一他卷/不存在 → 400 E07（不写标记）；否则集合不完整/真子集 → 400 E07（不写标记） | 版本时**是（标记）** |
| 6d | 同卷限次（1.5 例外生效前） | 已有成功 → 400 E08 | 否 |
| 7 | 判分 + 快照 + 单事务写入 | 成功 200 | 是（attempt + answers） |

> **顺序不可交换**：
> - 短路（5a/5c）必须先于内容核对、准入与身份分类，否则“成功后下线再同键重试”会变成 404 而非原结果（BR-19a/AS-07 回归）。
> - **结构校验（6a）→ 准入（6b）→ 数据/音频完整性（6b2）→ 身份/版本（6c）→ 限次（6d）**：准入先于身份分类，保证“提交到不可访问试卷”一律按 AS-07 处理（含加载后下线、换批后新批不可见、试卷不存在），不因请求体内容不同而改变 404 语义（D-15）；数据异常按 D-20 建议**只 404 不写永久标记**，避免运营故障把键永久作废；身份分类只在可访问且完整性通过后区分 E04/E07，且**版本判断先于集合完整性**，避免 EX-09b 退化为 E07。
> - 框架层口径：① 第 3 步 schema 解析/键格式校验由 FastAPI/Pydantic 在进入服务层前完成，不计入 BR-19d 的业务顺序；② 同键但 body 已损坏的重试会得到 422 而非回放，回放以“请求可解析”为前提（D-18）。

> **锁键算法（REV-06，必须固定）**：
> `lock_objid(text) = int.from_bytes(sha256(text.encode("utf-8")).digest()[:4], "big", signed=True)`；
> 键锁文本 `attempt-key:{student_id}:{attempt_key}`（classid=1）；限次锁文本 `attempt-limit:{student_id}:{exam_paper_id}`（classid=2）。
> **禁止**使用 Python 内置 `hash()`（进程随机化、不可复现）或数据库 `hashtext()`（随版本/实现变化）。同一文本在任何进程/实例必须得到同一 int32；碰撞只导致额外串行，不影响正确性。
>
> 该顺序把“结构校验 / 准入 / 数据完整性 / 身份分类 / 版本与集合 / 限次”的优先级统一为一条可实现链；任何实现偏离均须回改本表与 T04/T06 用例。

**状态映射（需求 7.3）**：

| 需求状态 | 本文表示 | 说明 |
|---|---|---|
| 无记录（未提交） | `attempts` 无行 ∧ `attempt_rejections` 无行 | 草稿不落库（D6） |
| 已提交 | `attempts` 1 行 + `attempt_answers` N 行 | 终态、只读；无修改/删除接口 |
| 幂等标记 | `attempt_rejections` 1 行 | 不是 attempt，不计入作答记录；同键返回同一拒绝 |
| “未交卷 attempt”对象 | 不存在 | `attempt_code` 仅在成功提交后产生；API-2 冻结，不存在“查未交卷记录”语义 |

#### 2.6.3 并发矩阵

| 场景 | 并发对象 | 期望 | 实现手段 |
|---|---|---|---|
| EX-21 双击提交 | 同键、同内容 | 至多 1 条 attempt；两次同一 200 结果 | 键级 advisory xact lock 串行化；`UNIQUE(student_id, attempt_key)` 最终防线 |
| EX-22 响应丢失重试 | 同键、同内容 | 返回同一 `attempt_code` 与结论 | 5a 短路 |
| EX-23 不同键并发（P1 生效后） | 不同键 | 2 条独立 attempt | 各自事务；无共享唯一键 |
| EX-24 同键并发 | 同键 | 不得两条成功；后到者在键锁内重读 → 5a 回放同一结果 | 键锁 + 唯一约束 + 重读 |
| V-21 不同键并发（1.5 例外生效前） | 不同键 | D-14 冲突仍未解决，M-32 继续 **BLOCKED，不判 PASS/PARTIAL**；默认限次实现另由 T06-A14 自测 | 学生+试卷维度 advisory lock 串行化计数和写入；门禁解除后可记录默认策略技术自测，不能代替 D11/D-14 确认 |
| V-23/EX-25 提交与下线并发 | 提交 vs 可见性变更 | 按服务端处理时点：准入检查时仍可访问→成功；检查前已不可访问→拒绝 | 准入判定在事务内、写入前；PG 默认 READ COMMITTED，按语句时点判定；两种顺序分别断言 |
| 同键“成功 vs 拒绝”竞态（极端） | 同一 `(student,key)` | 不得同时存在成功 attempt 与永久标记；优先返回成功原结果 | 键级 advisory xact lock 串行化 5a/5c/首次写入；成功表与标记表仍各带唯一约束 |

**BR-18a 的并发防护**（本轮必须实现，否则两个不同键可同时绕过“限 1 次”）：

```text
# 锁命名空间（两参数版，避免键锁与限次锁碰撞）：
#   classid=1：键锁 objid=lock_objid("attempt-key:{student_id}:{attempt_key}")
#   classid=2：限次锁 objid=lock_objid("attempt-limit:{student_id}:{exam_paper_id}")
# lock_objid = int.from_bytes(sha256(text.encode("utf-8")).digest()[:4], "big", signed=True)
# 禁止 Python hash() 或数据库 hashtext()；固定获取顺序：先键锁，后限次锁。

# 6d：在 6b/6b2/6c 通过后、限次计数前，同一事务内：
SELECT pg_advisory_xact_lock(2, :limit_objid);
# 然后 SELECT count(*) FROM attempts WHERE student_id=... AND exam_paper_id=...
# 仍为 0 → 判分并写入；否则 400 E08
```

- 使用 `pg_advisory_xact_lock`（事务结束自动释放），不需要新表/Redis；PostgreSQL 专有，符合本项目 BR-26 的 PG 约束。
- 锁键碰撞只会导致额外串行，不影响正确性。
- P1 生效后把 `ATTEMPT_LIMIT_PER_PAPER` 置为 `None` 并移除该锁；改动须随需求回写（D-08/D-11）。
- **不允许**“先查后插”而无锁：两个请求都查到 0 条会写出 2 条成功记录，违反当前默认 BR-18a。
- **R7-07 独立实现自测**：T06-A14 使用两个独立数据库会话、同学生同卷、两个不同键与同步钩子，在无故障条件下断言仅一条 attempt、完整逐题、两个响应分别为 200 和 E08、无永久拒绝标记。测试须确实覆盖两个请求竞争限次检查，并能识别去掉限次锁后的竞态。该记录填写 6.3a，不计入矩阵通过率；M-32/M-41 仍按 D-14 BLOCKED，D11/D-14 确认后再映射正式验收。

#### 2.6.4 事务与异常恢复

1. **拒绝标记提交后再返回拒绝**：6b/6c 只写当前拒绝标记，不写 attempt；必须确认 `commit()` 成功，再抛既有 `not_found()/bad_request()`。提交前写入失败回滚并返回安全 500；COMMIT 期间连接中断/确认丢失时，标记可能存在，也可能不存在，不能直接承诺原拒绝结论永久生效。
2. **同键互斥贯穿首次处理**：在查成功/拒绝记录前获取键级事务锁；成功与拒绝各自唯一约束仍保留。事务结束后锁释放；异常后若在服务内重新读取，须先结束失效事务，再在新事务中重新取得键锁。不得把读取错误当作“无记录”。
3. **异常先安全转换**：数据库执行、提交、rollback 和重读均受 2.7.3 脱敏规则约束。原始 `DBAPIError/StatementError`、驱动 DETAIL 和异常链不得进入全局 `logger.exception`。保留既有 `AppError` 外壳，500 文案固定。

**提交失败语义（R7-02）**：

| 情形 | 数据库可能状态 | 应用处置 | 验收可断言 |
|---|---|---|---|
| 提交前失败（构造/flush 等，尚未发送 COMMIT） | 本次写入未提交 | rollback；按既有业务错误或安全 500 返回 | 独立夹具内本次 attempt/answers/标记均不留半成品 |
| attempt COMMIT 结果未知 | 成功记录可能已持久化 | 返回安全 500 或发生连接中断；保持原键重试，按下表解析持久化状态 | 不承诺 0 行或重试必成功；同键最终至多一条成功记录 |
| 已提交但响应丢失 | 成功记录已持久化 | 同键同内容在认证后走 5a 回放 | 同一结果、不新增；不因后续下线重新判定 |
| 拒绝标记 COMMIT 结果未知 | 拒绝标记可能存在，也可能不存在 | 保持原键重试，只有查到标记才走 5c | 只有已持久化标记才保证同一拒绝；无标记时可按当前状态重新判定 |

**同键恢复判定表（数据库查询成功且持有键锁）**：

| 查到的持久化状态 | 处理 |
|---|---|
| 存在成功 attempt | 指纹相同回放原结果；不同返回 E09 |
| 无成功、存在永久拒绝标记 | 按标记 kind 回放拒绝，不重做内容/准入 |
| 两表均无记录 | 按首次提交流程重新执行当前校验，可能成功，也可能返回 400/404 等拒绝；不承诺维持上次未提交的判断 |
| 读取失败或仍无法确认 | 返回安全 500；不能按无记录继续写入，调用方保留原键重试 |

**处理骨架（设计伪代码；异常格式及链处理按 2.7.3）**：

```text
认证与 schema 通过 → 在同一事务内取键锁 → resolve_existing
已有成功/标记：按固定短路表返回
无记录：结构→准入→完整性→身份/版本→限次锁与计数→判分
拒绝需留标记：只 add/flush 标记 → commit 确认成功 → 抛安全业务 AppError
提交成功：add attempt → flush → add 全部 answers → 唯一一次 commit → 组装响应
IntegrityError：结束失败事务 → 新事务取键锁 → 重读两表并解析已有结果；
                无记录时按明确的冲突类型映射安全错误，不盲目再次插入
其他数据库/未预期异常：尽力结束失败事务 → 安全字段日志（无参数、无原始异常链）
                     → raise AppError(500, "服务器内部错误") from None
```

- 成功 attempt 与全部逐题在一个事务写入；拒绝请求只提交标记，不与成功记录分段提交。
- `flush()` 不构成提交；rollback 本身失败时只记录安全状态，不能掩盖 COMMIT 未知状态或把它解释成 0 行。
- 必须分别覆盖提交前故障、COMMIT 中断、提交成功但响应丢失；未知提交还要覆盖“实际提交”和“实际未提交”两支，以及未提交后试卷状态变化。
- 例如：成功 COMMIT 未完成且试卷随后下线，同键重新判定可返回 404；拒绝标记 COMMIT 未完成且试卷恢复可访问，同键重新判定可成功。只有持久化事实提供回放保证。

### 2.7 异常处理与错误语义

#### 2.7.0 异常分级与责任角色（对齐需求 v0.20 §10.0）

| 级别 | 含义 | 处置 | 对验收的影响 |
|---|---|---|---|
| **BLOCKER（阻断）** | 若实际行为偏离预期，将违反红线、权限、准入或数据完整性 | 按已确认预期处理请求；发现缺陷时停止放行并记录 | 正确拒绝/处理记 PASS；实际缺陷记 FAIL，命中 5.5 红线则整体 FAIL |
| **REVIEW（需判断）** | 预期仍取决于负责人决策（如 D10、D11、P6） | 未确认时记录阻塞；确认后按真实决策更新判据 | 未确认记 BLOCKED；确认后按预期判 PASS/FAIL；不以 PARTIAL 代替未决规则 |
| **WARN（提示）** | 缺陷风险或提示程度较低，但不豁免必需判据 | 记录提示和影响，必需校验仍照常执行 | 符合预期记 PASS；不符合必需判据记 FAIL；不能仅因级别为 WARN 放行 |

| EX 分组 | 默认级别 | 责任角色 |
|---|---|---|
| EX-01–06 权限 | BLOCKER | 开发人 |
| EX-07–13 状态 | BLOCKER（准入类）/ REVIEW（换批判定） | 开发人 / 负责人 |
| EX-14–20 输入 | WARN（格式类） | 开发人 |
| EX-21–26 并发与重试 | BLOCKER（重复成功记录）/ WARN（明确失败） | 开发人 |
| EX-27–32 数据 | REVIEW | 验收人 / 负责人 |

> 矩阵中每行已带“级别/责任角色”列，具体取值以上表默认值为基线；若某行同时含多个 EX 场景，按**较高**级别（BLOCKER > REVIEW > WARN）记录，并在备注说明。
>
> **级别 ≠ 测试结果（REV-08）**：级别描述的是“该异常发生时要求的处置与风险”，不是该场景的验收结论。**正确拒绝非法请求记 PASS**（例如管理员提交被 403、非法输入被 422）；`REVIEW` 在口径未确定前只能记 **BLOCKED**，口径确认后按确认预期判 PASS/FAIL；`WARN` 表示可留痕通过，但**不豁免**输入校验、鉴权、准入等必需判据。验收人不得因“场景级别低”而把未实现或错误行为记 PASS。

#### 2.7.1 状态码与 `msg` 映射（本轮定稿，D-01）

| # | 场景 | HTTP | `msg`（建议原文） | 标记 | attempt | 关联 |
|---|---|---|---|---|---|---|
| E01 | 无 token / token 失效 / 账号停用 | 401 | 未登录或登录已失效 | — | 否 | AS-16、EX-01/02/06 |
| E02 | 管理员调 API-1（`is_admin`） | 403 | 没有访问该接口的权限：需要学生角色 | — | 否 | AS-17、EX-03 |
| E03 | 学生提交时试卷不可访问/不存在 | 404 | 资源不存在 | `paper_not_accessible` | 否 | AS-07、EX-07/08 |
| E04 | 内容版本不一致（加载后换批） | 400 | 内容已更新，请重新作答 | `content_version_mismatch` | 否 | EX-09b、S8c |
| E05 | 缺 `Idempotency-Key` / 非 UUIDv4 / 超长 | 400 | 缺少或非法的提交键 Idempotency-Key | — | 否 | EX-20、D-02 |
| E06 | 请求体 schema 错误（缺字段、类型错、字母非 A–D） | 422 | 请求参数校验失败（全局固定文案，不回显） | — | 否 | EX-16、EX-18 |
| E07 | 语义参数非法（题目不属于本卷/重复/整卷集合不完整/答案为集合外） | 400 | 提交内容不合法：<具体原因> | — | 否 | AS-01、EX-17/19、5.5a |
| E08 | 同卷限次（1.5 例外生效前，已有成功） | 400 | 本轮同一试卷仅允许提交一次 | — | 否 | D11、BR-18a、V-01a |
| E09 | 同键不同内容/不同试卷（已有成功） | 400 | 提交键已用于其他提交，请使用新键 | — | 否 | BR-19b |
| E10 | 同键已有永久拒绝 | 400/404（按 kind：不可访问 404；版本不一致 400） | 与首次拒绝相同的 `msg` | 否（复用） | 否 | BR-20 |
| E11 | 服务端内部错误（DB 不可用、未预期异常、COMMIT 结果未知） | 500 | 服务器内部错误 | 不因故障新建；此前 COMMIT 的标记可能已存在 | 提交前失败无本次记录；COMMIT 未知可能已持久化，按 2.6.4 同键确认 | AS-08、EX-26、R7-02 |
| E12 | 成功 | 200 | 提交成功 | — | 是 | AS-01 |
| E13 | 同键同内容成功重试 | 200 | 提交成功（返回原结果） | — | 否（不新增） | BR-19a、AS-06 |
| E14 | 提交时数据/音频完整性异常（EX-28；D-20 建议口径） | 404 | 资源不存在 | **不写永久标记**（记录日志；修复后同键可重试） | 否 | EX-28、BR-01、D-20 |

> **为什么不用 409**：需求 §8.5 明确“409/429/413 本轮不定义”。为不越权扩展需求，E04/E08/E09 统一用既有 400 通道并以 `msg` 区分；IETF draft 的 422/409 语义仅在对照中记录（2.11）。若负责人批准改用 409，须同步修改需求 §8.5、本表、API 契约与验收脚本断言（D-01）。

#### 2.7.2 边界细则

> 下列判定除特别说明外，均指“结构校验通过 **且试卷可访问**”后的场景；试卷不可访问时一律 404 E03 + access 标记（准入优先，D-15），不再区分身份/版本。

| 情形 | 处理 |
|---|---|
| `loaded_question_ids` 缺失/空 | 缺失 → 422；显式空数组 → 400（整卷集合不得为空） |
| `answers` 字段缺失 | 422（格式错误，不按空卷） |
| `answers = []` | 允许（空卷提交，0%，全部未作答） |
| `answers` 含 `loaded_question_ids` 之外的题 | 400；不落库、不留标记 |
| 同一 `question_id` 在 `answers` 重复 | 400（EX-19） |
| `question_id` 属于其他试卷/不存在 | 400（参数非法；5.5a） |
| `question_id` 属于本卷旧批次（任一） | E04（版本不一致；**优先于他卷/不存在/集合不完整**，D-16） |
| `loaded_question_ids` 是当前批次的真子集 | 400（整卷集合不完整；不判分） |
| `loaded_question_ids` 全部属于当前批次但顺序不同 | 允许（集合语义） |
| 选择字母小写 `a` | 422（契约只接受大写 A–D；如需宽松需另行定义） |
| 试卷可访问但题目/映射/音频异常（数据不一致） | 按“试卷不可访问”处理：404 E14，**不写永久标记**（D-20 建议口径）；记录数据异常、不判分、不写 attempt；修复后同键可重试 |
| 解析为空 | 正常；快照空串（本轮不返回） |
| 试卷未绑定音频/音频缺失 | 内容检查在确认可见时拦截；若确认后音频被删除/不可读，提交时完整性检查按不可访问处理：404 E14，**不写永久标记**（M-29b，D-20 建议口径），不写 attempt；修复后同键可重试 |

> **5.5a 的“题号”映射**：需求 5.5a 用“题号不存在”描述题目身份异常；本实现以学生详情已返回的 `question_id` 作为题目身份，因此“题号不存在”对应“`question_id` 不属于本卷当前批次”。原卷题号（`question_no`）只用于展示、快照与判分，不单独作为提交身份，避免换批后题号复用造成误判。

#### 2.7.3 错误处理原则

1. 复用既有 `AppError` 和 `{code,msg,data}` 外壳，不新增全局响应格式。业务拒绝继续走现有处理器；作答服务对未预期异常先安全转换，再交给外壳。
2. 422 文案固定且不回显请求值；400 仅含安全业务原因，不包含答案、解析、正文、完整键或数据库诊断文本。
3. 任何结果都不得出现半条聚合；COMMIT 结果未知不等于未提交，按 2.6.4 恢复，E11 与测试不能无条件断言 0 行。
4. **认证先于 body 校验**：未登录/失效 token 仍先 401；管理员先 403。已认证且角色通过后，JSON 类型错误和路径范围错误才 422。若默认依赖顺序不能保证非法 JSON 的 401 优先，须按 T06-A12 做鉴权前置并复验；D-21 不允许默认接受 422。键格式仅在请求可解析时按 E05 处理。
5. **日志白名单**：允许已知的 `attempt_code/student_id/exam_paper_id`、指纹前 8 位、提交阶段、异常类名、白名单 SQLSTATE/约束标识、rollback 是否失败，以及文件/函数/行号组成的栈帧位置。不存在的字段可省略；不记录请求体、SQL 参数、原始 SQL/异常文本、驱动 DETAIL、局部变量、带数据值的源码片段、所选/正确答案、解析、正文或完整键。
6. **数据库错误不得穿透到原始异常日志（R7-05）**：`services/attempts.py` 必须覆盖执行、flush、commit、rollback 和重读异常。只调用安全字段记录器；不得将原始 `exc` 作为日志格式化参数，不使用会输出原始异常链的 `logger.exception`/`exc_info=True`。记录安全栈帧后，使用 `raise AppError(500, "服务器内部错误") from None` 转换；其它未预期异常同样处理。已安全的业务 `AppError` 保留原 400/404/500 等语义。
7. `hide_parameters=True` 只能辅助隐藏参数列表，不能代替驱动消息和异常链脱敏。本轮优先在新增作答服务边界完成隔离，保持 `db/base.py` 与既有全局 HTTP 契约不变；不得仅设置参数隐藏后宣称全部日志安全。
8. **验收落点**：T06-A15/T07-A7/T08-A9、M-23a 捕获服务层及全局最终日志，注入含虚构答案、解析、正文、完整键、驱动 DETAIL 的错误；所有测试标记均不得出现，同时安全定位信息仍存在。仅验证 HTTP 响应字段不构成日志验证。

### 2.8 兼容、回退与发布

#### 2.8.1 数据库迁移

- 新迁移 `backend/alembic/versions/0005_attempt_system.py`，`revision="0005_attempt_system"`，`down_revision="0004_expected_count_source"`。
- 仅 `create_table` + `create_index` + 约束；**不 ALTER 任何既有表**，不写数据迁移。
- `downgrade()` 逆序 `drop_table`（先 `attempt_answers`、`attempt_rejections`，再 `attempts`）；索引随表删除。
- `env.py` 需新增 `from app.db import models_attempt  # noqa: F401`（`backend/alembic/env.py:9–11` 的现有注册模式），否则手写迁移可跑但模型元数据不完整、后续 autogenerate 会漂移。
- 验收：`alembic heads` 单 head；`upgrade head` → `downgrade 0004` → `upgrade head` 往返；旧迁移哈希/内容未变；模块一 4 表未动（V-R6）。

#### 2.8.2 应用兼容

- API-1 为新增 path，旧客户端不受影响；既有 6 个接口响应不变（V-R2/R3/R4）。
- API-2 冻结：本轮不提供该路由，本文也**不定义**其路径或 404 业务语义；前端轮次与解冻后的结果读取另行设计（FZ1）。
- 新代码不读取/写入模块二既有表结构以外的数据；回退旧版本代码时，新表可保留不用（不影响旧功能）。
- 不新增配置项；限次常量在代码中定义（`ATTEMPT_LIMIT_PER_PAPER = 1`），P1 生效后改为 `None` 属需求变更，不是环境开关。

#### 2.8.3 回退步骤（R7-04，分两条路径）

| 路径 | 操作 | 迁移版本与验证 |
|---|---|---|
| **默认：只回退应用代码** | 停止后端；回退到前一应用版本；**旧应用不执行任何 Alembic 迁移**；保留 3 张新表和全部数据，**不执行 downgrade** | 用**保留 0005 迁移脚本的新版本 Alembic 目录**执行 `alembic current`，或直接只读查询 `alembic_version` 表，应为 `0005_attempt_system`；**不得用不含 0005 的旧镜像执行 Alembic**（会报 “Can't locate revision”）；旧应用和既有模块一/二功能可运行；有数据的环境不执行会清空数据的测试夹具 |
| 明确要求数据库也回退 | 先停服；**导出 `attempts/attempt_answers/attempt_rejections`，记录文件名/哈希/行数，校验可读取并取得书面授权**；再回退应用并执行 `alembic downgrade 0004_expected_count_source` | `alembic current` 为 `0004_expected_count_source`；3 张新表被删除，旧表保留；在隔离库/副本核验迁移及回归 |

执行步骤：

1. 记录当前代码、迁移版本、目标回退路径及数据清单；存在作答表时用 `pg_dump -t attempts -t attempt_answers -t attempt_rejections` 或受控只读 SQL 导出，**记录导出文件名、SHA-256、各表行数**，并校验导出可读取。首次上线前尚无这些表时，按上线前完整备份方案执行，不将不存在的表作为必须导出项。
2. 停止后端服务，避免新旧版本混跑；选择上表对应路径操作。**默认路径只回退代码，不执行任何 Alembic 迁移；数据库降级路径必须先完成导出与书面授权。**
3. 按该路径验证应用启动、既有 API 和迁移版本：路径 A 用保留 0005 的 Alembic 目录或只读查 `alembic_version`；路径 B 确认 current 为 0004。全量测试/迁移往返仅在隔离库或副本运行，不在保留真实数据的回退库上运行破坏性夹具。
4. 恢复服务，记录回退原因、时间、路径、实际迁移版本、数据导出文件/哈希/行数及恢复状态。

数据库 downgrade 会删除成功记录和永久拒绝标记；既有“书面确认后方可执行”的要求保留。只恢复代码不撤销已经持久化的提交/拒绝事实，旧键语义须在后续重新上线时继续保持。

#### 2.8.4 P1/P6 与范围变更

- **v0.20 §14.2 门禁（统一口径）**：v0.20 未确认，门禁尚未正式生效；但按项目保守规则，**T2/T3 未定 → T01–T10 暂缓开工（BLOCKED）**。T2/T3 确定且 v0.20 确认后解除；若负责人不采纳 v0.20，按 v0.19 另行确认开工条件。R 组/API-2/结果页在 P1 回写 + P6 满足前不开发。
- P1 生效（结果读取）需要：负责人书面结论 + 回写模块二 B04.3/B05 + 记入需求 1.4/2.4，三要件齐备后另开任务卡（API-2、R 组验收），不在本文范围。
- P6 满足前即使 P1 生效条件齐备，结果读取仍不上线（4.5 P6）。
- D11 由 A 改 B（允许重复提交）时，需回改：限次常量、BR-18a、V-01a、S3/AS-05/V-05 的“P1 生效后”限定、D1–D6 的限次表述；本文对应改动点：T06 的 6d、错误表 E08、矩阵 V-01a/V-05。

### 2.9 安全、隐私与内容边界

| 风险 | 控制 | 验收关联 |
|---|---|---|
| 交卷前泄露答案/解析/正文 | 复用既有学生接口裁剪；新增 API 只接收作答、不返回受保护内容 | BR-04、AS-18、V-R2 |
| 交卷后越权读结果 | 本轮无 API-2；冻结，不在本文设计 | FZ1、AS-09–15（冻结） |
| 管理员代答/读结果 | `is_admin` 优先 403；不提供管理员结果接口 | R1、AS-13/17、E02 |
| 未认证返回 404/403 | 依赖链先 401；测试覆盖“目标不存在仍 401” | AS-16、EX-06、V-R1 |
| 跨用户幂等键串用 | 唯一键含 `student_id`；指纹含试卷；键不跨用户共享 | DC-3、2.6.1 |
| 幂等键注入/超长 | 正则白名单 + 长度上限 + SQL 绑定参数 | D-02、2.6.1 |
| 内部 ID/状态泄露 | 响应只含 `attempt_code` + 原卷题号；不返回 DB 主键、batch/状态 | DC-9 |
| 日志泄露答案/解析/正文/完整键 | 2.7.3 安全字段记录及异常转换；过滤参数、驱动 DETAIL 和异常链；不将原始数据库异常交给全局 logger | T06-A15/T07-A7/T08-A9、M-23a |
| 重放/重复计分 | 同键短路、限次锁和唯一约束；未知提交按持久化记录恢复 | BR-19/18a、T06-A14、2.6.4 |
| 限流/暴力提交 | 本轮无 429（需求未定义）；登记为风险，后续按需引入 | 2.12、14.3 |
| 拒绝标记无界增长（M-09） | 每个 `(student,key)` 至多一行；本轮永久保留、不限流；接受风险（D-17），运营侧监控表增长，清理/限流另开需求 | BR-20、7.6 |
| 拒绝标记可被任意 `paper_id` 制造 | 标记表无试卷外键，已认证学生可用任意合法键对不存在/不可访问试卷制造标记；仅能按 `(student,key)` 去重、不能按 paper 限流。**监控每学生标记数/表增长；如负责人要求限制，改为“仅对存在但不可访问的试卷写标记，不存在/格式错误不写”并回改 AS-07 口径** | BR-20、2.3.4、D-17 |

### 2.10 测试与验收策略

| 层级 | 范围 | 手段 | 是否允许 Mock |
|---|---|---|---|
| L1 纯函数 | 字母换算、正确率、249 估分、空解析、未作答 | `pytest` + 直接调用 `grading.py`（无 DB） | 允许（纯输入） |
| L2 集成 | 迁移、唯一约束、标记、限次、事务回滚 | 真实 PostgreSQL 测试库（`tests/conftest.py` 夹具）；`TestClient` 打 API | **不允许**用 Mock 替代 DB |
| L3 接口验收 | 正常/异常/权限/幂等/并发/回归 | `pytest` 场景化用例；失败注入用 `monkeypatch` 仅替换“故障点” | 仅故障注入 |
| L4 端到端 | 真实服务 + 真实库 + 真实样例 | `scripts/acceptance_attempt.py`（httpx，`trust_env=False`），逐项 PASS/FAIL + 退出码 | 不允许 |

**命令（均在 `backend` 目录；Python 用实际环境解释器）**：

```powershell
# 迁移与单 head
python -m alembic heads
python -m alembic upgrade head
python -m alembic downgrade 0004_expected_count_source
python -m alembic upgrade head

# 测试（全量；新用例暂放 test_attempt_*.py）
python -m pytest -v

# 仅作答相关
python -m pytest -v tests/test_attempt_grading.py tests/test_attempt_api.py tests/test_attempt_regression.py

# 端到端（需先完成 T10 数据准备并启动服务）
python -m scripts.acceptance_attempt --base-url http://127.0.0.1:8000 --paper-id <专用验收试卷ID> --student-user <专用验收学生> --admin-user <验收管理员>
```

**准入/准出**：

- 进入 T06 编码前：T01–T05 的验收项 PASS（或经书面接受的 PARTIAL/BLOCKED）。
- 合并前：既有用例全部通过 + 新增用例覆盖矩阵 A/C/D 行 + 迁移往返成功 + 既有模块二学生接口字段回归。
- 不把“pytest 全绿”当端到端验收：V-E 系列必须有真实库/样例证据（需求 11.1“证据”）。

### 2.11 关键技术调研与 GitHub 参考

> **调研边界（如实说明）**：2026-11-08 通过 PyPI 项目页/JSON、SQLAlchemy 与 Alembic 官方文档、IETF Datatracker、python.org、postgresql.org 核对；**本环境无法直接访问 github.com / api.github.com**，因此 GitHub 仓库与文件链接标注“链接供核对，本环境未直接抓取”。许可证与版本以 PyPI/官方页为准；未能逐字核实的条目在 2.11.9 列出。本仓库实际锁定版本以 `backend/requirements.txt` 为准，调研只为“可借鉴/适配/局限”，**不构成升级建议**（OUT11）。

#### 2.11.1 FastAPI（MIT，参考版本 0.162.2 / 锁定 0.143.0）

| 项 | 内容 |
|---|---|
| 仓库 / 文档 | https://github.com/fastapi/fastapi ；https://fastapi.tiangolo.com |
| 许可证/维护 | MIT；PyPI 最新 0.162.2（2026-11-07），Python ≥3.10（C：PyPI 项目页） |
| 关键参考 | 依赖注入：https://fastapi.tiangolo.com/tutorial/dependencies/（C）；Header 参数：https://fastapi.tiangolo.com/tutorial/header-params/（C）；异常处理：https://fastapi.tiangolo.com/tutorial/handling-errors/（C） |
| 可借鉴 | `Depends` 组合鉴权/DB/配置；`Header` 声明 `Idempotency-Key`；全局异常处理器统一外壳；`response_model=ApiResponse[T]` 固定成功结构 |
| 适配 | 复用 `deps.py:67–106` 与 `main.py:33–70`；新增 `require_student` 依赖；API-1 路由单独文件挂载；不引入 APIRouter 之外的新机制 |
| 局限 | 全局 422 处理器隐藏字段级错误（既有安全取舍）；依赖写法的 Ruff B008 已忽略；测试替换依赖用 `app.dependency_overrides`（本项目未用，新增测试不必引入） |

#### 2.11.2 SQLAlchemy 2.1（MIT，参考 2.1.8 / 锁定 2.1.4）

| 项 | 内容 |
|---|---|
| 仓库 / 文档 | https://github.com/sqlalchemy/sqlalchemy ；https://docs.sqlalchemy.org/en/21/ |
| 许可证/维护 | MIT；PyPI 最新 2.1.8（2026-11-04），Python ≥3.11（C：PyPI 项目页） |
| 关键参考 | 事务：https://docs.sqlalchemy.org/en/21/orm/session_transaction.html（C，已读正文）；Session：https://docs.sqlalchemy.org/en/21/orm/session_basics.html（C）；唯一约束：https://docs.sqlalchemy.org/en/21/core/constraints.html#unique-constraint（C）；`IntegrityError`：https://docs.sqlalchemy.org/en/21/core/exceptions.html#sqlalchemy.exc.IntegrityError（C） |
| 可借鉴 | `select()` 风格；`with Session.begin()`/显式 commit 的单事务边界；`UniqueConstraint`/`Index` 组合；`IntegrityError` 后必须 rollback 再重读；`expire_on_commit=False` 便于提交后读取对象 |
| 适配 | 复用 `db/base.py` 的 `sessionmaker`（:33–39）与 `get_db`（:42–49）；新仓储层沿用 `db.scalar/select`；不新建 engine |
| 局限 | 部分唯一索引需 PostgreSQL 方言；`IntegrityError` 后会话失效，必须回滚；锁定版本与最新有 patch 差，升级不在本轮 |

#### 2.11.3 Alembic（MIT，参考 1.20.1 / 锁定 1.20.0）

| 项 | 内容 |
|---|---|
| 仓库 / 文档 | https://github.com/sqlalchemy/alembic ；https://alembic.sqlalchemy.org/en/latest/ |
| 许可证/维护 | MIT；PyPI 最新 1.20.1（2026-10-22），Python ≥3.10（C：PyPI 项目页） |
| 关键参考 | 分支与多 head：https://alembic.sqlalchemy.org/en/latest/branches.html（C，已读正文）；命令：https://alembic.sqlalchemy.org/en/latest/api/commands.html（C）；操作：https://alembic.sqlalchemy.org/en/latest/ops.html（C） |
| 可借鉴 | `revision`/`down_revision` 单链；`alembic heads` 作为 CI 检查；`downgrade` 成对实现；迁移 docstring 记录“为什么” |
| 适配 | 现有 `0001→0004` 即单链样例；新增 `0005` 以 `0004` 为父；`env.py:9–11` 追加 `models_attempt` 导入；不改既有迁移 |
| 局限 | 本项目手写迁移（未用 autogenerate），模型与迁移一致性靠 review；`downgrade` 会丢作答数据，需先备份 |

#### 2.11.4 Pydantic v2（MIT，参考 2.14.3 / 锁定 2.14.1）

| 项 | 内容 |
|---|---|
| 仓库 / 文档 | https://github.com/pydantic/pydantic ；https://docs.pydantic.dev/latest/ |
| 许可证/维护 | MIT（C：PyPI 页面与官方 LICENSE 链接；许可证正文本次未逐字抓取）；最新 2.14.3（2026-11-04），Python ≥3.10（C：PyPI 项目页） |
| 关键参考 | 模型：https://docs.pydantic.dev/latest/concepts/models/（C）；字段约束：https://docs.pydantic.dev/latest/concepts/fields/（C）；字符串模式：https://docs.pydantic.dev/latest/concepts/string_patterns/（C） |
| 可借鉴 | `BaseModel` 定义请求/响应；`Field(pattern=...)` 限定字母/键格式；`list[int]` + `min_length`；校验失败由 FastAPI 统一 422 |
| 适配 | 学生/管理员请求-响应分离模式沿用 `schemas_listening.py`；新增 `schemas_attempts.py`，不把业务规则塞进 schema（如“整卷集合完整”在服务层） |
| 局限 | `pattern` 只校验格式；422 全局文案不回显；Pydantic v1/v2 不兼容，参考必须 v2 |

#### 2.11.5 PostgreSQL（PostgreSQL License，18.6）

| 项 | 内容 |
|---|---|
| 官网 / 源码镜像 | https://www.postgresql.org/ ；https://github.com/postgres/postgres（链接供核对，未直接抓取） |
| 许可证/维护 | PostgreSQL License（SPDX: `PostgreSQL`，BSD/MIT 类宽松许可）；当前 minor 18.6（C：https://www.postgresql.org/about/licence/ 与 https://www.postgresql.org/support/versioning/；18.6 具体发布日期未核实） |
| 关键参考 | 部分索引：https://www.postgresql.org/docs/current/indexes-partial.html（C）；`INSERT ... ON CONFLICT`：https://www.postgresql.org/docs/current/sql-insert.html（C）；隔离级别：https://www.postgresql.org/docs/current/transaction-iso.html（C）；JSONB：https://www.postgresql.org/docs/current/datatype-json.html（C）；advisory lock：https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS（C） |
| 可借鉴 | 唯一约束/部分唯一索引做最终闸门；`pg_advisory_xact_lock` 串行化“限次计数+写入”；JSONB 存快照分组；事务 DDL 支持回退 |
| 适配 | 仅新增表/索引；不引入扩展；`attempt_rejections` 唯一键实现永久标记；限次锁只在 BR-18a 生效期使用 |
| 局限 | 部分索引与 advisory lock 为 PG 专有（本项目已固定 PG，符合边界）；`ON CONFLICT` 不能处理业务冲突；JSONB 高频查询需 GIN（本轮无查询需求，不建） |

#### 2.11.6 IETF Idempotency-Key（draft-08，未成为 RFC）

| 项 | 内容 |
|---|---|
| 规范 / 仓库 | https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/08/ （C，已读正文）；https://github.com/ietf-wg-httpapi/idempotency（Datatracker 链接；本环境未抓取） |
| 状态/日期 | Active Internet-Draft（httpapi WG，WG Document，I-D Exists），2026-10-22 更新，2027-04-25 过期（C：Datatracker） |
| 关键语义 | 缺 header → 400；同键不同 payload → 422；原请求处理中重试 → 409；可用指纹（整包/部分校验和、摘要）判断同请求；建议组合键（key + 客户端属性）防串用；资源须发布过期策略（C：draft §2.2–2.7、§5） |
| 可借鉴 | 复合作用域 `(student_id, key)`；`request_fingerprint` 列；首次成功后回放同一响应；并发用唯一约束/占位行而非“先查后插”；键格式白名单 |
| 适配 | **不新增依赖**（OUT11）；把 draft 语义映射到本项目既有错误码：缺键→400、键冲突→400（D-01）、并发→唯一约束+重读；不实现 409/422 的 HTTP 语义，因为需求未定义 409 且 422 已被全局校验占用；不实现过期清理（本轮永久保留） |
| 局限 | Internet-Draft 非 RFC，语义可能变化；规范对并发只给 SHOULD；参考库 `fastapi-idempotency-key` 仅 0.1.x、Beta、单维护者（PyPI 元数据：0.1.1，2026-10-03，MIT），且引入依赖违反 OUT11，故**只借鉴不采用** |

#### 2.11.7 CPython `decimal` / `round`（PSF-2.0，Python 3.14.2）

| 项 | 内容 |
|---|---|
| 仓库 / 文档 | https://github.com/python/cpython（链接供核对，未抓取）；https://docs.python.org/3/library/decimal.html（C，已读正文）；https://docs.python.org/3/library/functions.html#round（C，页面未逐字读到该节） |
| 许可证/维护 | PSF-2.0（C：https://docs.python.org/3/license.html）；本仓库 3.14.2（README），本次最新 3.15.2（2026-10-25，C：python.org） |
| 关键结论 | `decimal` 默认上下文 `ROUND_HALF_EVEN`，支持显式 `ROUND_HALF_UP` 与 `quantize`（C：官方文档正文）；内置 `round()` 为 banker's rounding（`round(2.5)==2`），与“四舍五入”业务语义不同（C：官方文档常识 + Python issue 检索，未逐字抓原文） |
| 可借鉴 | 业务计算用 `Fraction`/`Decimal` 精确值；不用 float；只在最终一步做 half-up 取整；正确率用整数公式 |
| 适配 | `grading.py` 内部用 `fractions.Fraction`（标准库）或 `Decimal(ROUND_HALF_UP)`；数据库列用 `SMALLINT`/`INTEGER`，不用 `FLOAT`；接口输出整数 |
| 局限 | `Decimal` 与 float 混算会抛错；JSON 无 Decimal 原生类型；`ROUND_HALF_UP` 是业务选择，需在本文固定并测试 |

#### 2.11.8 pytest / httpx（MIT / BSD-3-Clause）

| 项 | 内容 |
|---|---|
| 仓库 | https://github.com/pytest-dev/pytest ；https://github.com/encode/httpx（链接供核对，未抓取） |
| 许可证/维护 | pytest MIT，9.2.0（2026-10-27）＝锁定版本；httpx BSD-3-Clause，0.28.1（2024-12-06）＝锁定版本（C：PyPI 项目页） |
| 可借鉴 | session 级夹具一次性建库/迁移/种子、function 级 `client`；`parametrize` 覆盖异常分支；`httpx.Client(trust_env=False)` 避免代理假失败；脚本内 `_check` 汇总并返回退出码 |
| 适配 | 新测试沿用 `tests/conftest.py`；新增 `scripts/acceptance_attempt.py` 沿用 `acceptance_module2.py` 结构；失败注入用 `monkeypatch` 仅替换故障点 |
| 局限 | 测试库需 `CREATE DATABASE` 权限；session 级共享数据需注意用例顺序；httpx 稳定版较旧（0.28.1），升级需评估（本轮不升级） |

#### 2.11.9 未核实/证据不足清单（不得在验收中当作已证实）

1. **GitHub 仓库与关键代码文件**：本环境无法打开 github.com；仓库 URL 与目录级链接仅供核对，**未逐文件抓取源码**。因此本文不写具体 GitHub 行号，只写仓库/文档链接与官方文档结论。
2. **Pydantic 许可证正文**：PyPI 页面在 License 段被截断，MIT 依据 PyPI 徽章与官方 LICENSE 链接（C）。
3. **CPython `round()` 官方段落**：`functions.html` 抓取被截断，ties-to-even 依据官方文档常识与 issue 检索（C）。
4. **PostgreSQL 18.6 具体发布日期**：versioning 页确认 current minor 18.6，日期未核实（C）。
5. **IETF 仓库代码许可证**：GitHub 不可达，未核实（D）；规范文档版权按 IETF Trust/BCP 78，代码组件需 Revised BSD（C：文档 Copyright Notice）。
6. **`fastapi-idempotency-key` 维护结论**：仅 PyPI JSON 元数据（0.1.1、2026-10-03、MIT、Beta、单维护者），未评估其代码质量（D）。
7. **测试用例数**：29 个测试函数/参数化 34 例为静态统计（无 venv，未运行 `pytest --collect-only`）；实际收集数可能有差异。

#### 2.11.10 关键代码位置（仓库链接，供核对；本环境未抓取）

> 以下为**仓库文件级链接**，用于开发时定位可借鉴实现；路径可能随上游分支演进，打开前以仓库默认分支为准。本文未在本环境读取这些文件，因此不就其行号/内容作断言。

| 组件 | 关键代码/目录链接 | 与本项目的关系 |
|---|---|---|
| FastAPI | https://github.com/fastapi/fastapi/blob/master/fastapi/dependencies/utils.py ；https://github.com/fastapi/fastapi/blob/master/fastapi/routing.py | 依赖注入解析、路由/异常处理；对应 deps/异常外壳复用 |
| SQLAlchemy | https://github.com/sqlalchemy/sqlalchemy/blob/main/lib/sqlalchemy/orm/session.py ；https://github.com/sqlalchemy/sqlalchemy/blob/main/lib/sqlalchemy/sql/schema.py | Session 事务边界、Unique/Check 约束定义 |
| Alembic | https://github.com/sqlalchemy/alembic/blob/main/alembic/operations/ops.py ；https://github.com/sqlalchemy/alembic/blob/main/alembic/command.py | `create_table`/`drop_table` 与 upgrade/downgrade 命令 |
| Pydantic | https://github.com/pydantic/pydantic/blob/main/pydantic/main.py | `BaseModel` 校验入口 |
| CPython | https://github.com/python/cpython/blob/main/Lib/_pydecimal.py ；https://github.com/python/cpython/blob/main/Python/bltinmodule.c | Decimal 舍入实现参考、内置 `round()` 实现 |
| pytest | https://github.com/pytest-dev/pytest/blob/main/src/_pytest/fixtures.py | fixture 生命周期（测试夹具参考） |
| httpx | https://github.com/encode/httpx/blob/main/httpx/_client.py | 同步 Client/超时/`trust_env` 行为 |
| IETF | https://github.com/ietf-wg-httpapi/idempotency | draft 源码与讨论（规范正文以 Datatracker 为准） |

### 2.12 未采纳方案与理由

| 方案 | 为什么不采纳 | 保留的替代 |
|---|---|---|
| 引入 `fastapi-idempotency-key` 等库 | OUT11 禁止新依赖；库为 0.1.x/Beta/单维护者 | 用唯一约束 + 指纹 + 短路段自研，逻辑量小 |
| Redis 存幂等键/分布式锁 | 项目一期明确不引入 Redis；PG 唯一约束 + advisory lock 足够 | PostgreSQL 事务内锁 |
| 用 409/422 精确复刻 IETF 语义 | 需求 §8.5“409/429/413 本轮不定义”；422 已被全局校验占用 | 400 + 明确 `msg`；D-01 待确认 |
| 结果以整份 JSON 存一列 | 无法满足 O3“逐题事实可用只读 SQL 追溯”；无法逐题校验 | 规范化 `attempt_answers` + 汇总列 |
| 提交时只存题目 ID，读取时回查题库 | 违反 D8/BR-23 快照不漂移；换批/改答案会变 | 提交时冗余快照文本 |
| 读取时重新判分 | 违反判分快照与“结果不漂移”；阅卷标准变化会改历史结论 | 只读持久化结论 |
| 直接返回数据库自增 id 作为 attempt 标识 | 违反 DC-9（不暴露主键）；可枚举 | `attempt_code` UUID |
| attempt 外键全部 CASCADE | 违反 DC-7（不随试卷/批次删除） | RESTRICT；逐题仅对 attempt 内部 CASCADE |
| 前端判分/前端隐藏答案 | 违反 O2“服务端唯一权威”；隐藏不构成权限 | 服务端判分；学生接口裁剪 |
| 本轮顺带实现 API-2 | P1/P6 未满足；属于范围扩张 | 冻结并登记（FZ1） |
| 用 `round()` 或 float 算正确率/估分 | banker's rounding 与浮点误差，验收会出现 95 vs 96 的争议 | 整数公式 / Fraction / Decimal half-up |

---

## 3 任务总表

### 3.1 编号、优先级与实施顺序

| 编号 | 任务 | 对应需求 | 优先级 | 依赖 | 顺序 | 写作用域（建议） |
|---|---|---|---|---|---|---|
| T01 | 数据模型与 `0005` 迁移 | G1、G7、BR-26、DC-2/6/7/8、7.1–7.3 | P0 | 无 | 1 | `backend/app/db/models_attempt.py`、`backend/alembic/versions/0005_attempt_system.py`、`backend/alembic/env.py` |
| T02 | 请求/响应契约与 schema | AS-01/02、EX-16/18/19/20、BR-19、8.4 | P0 | T01 | 2 | `backend/app/schemas_attempts.py`（模型层） |
| T03 | 幂等仓储、短路与拒绝标记 | L-G8、BR-19a–d/20、AS-06/07、7.3 | P0 | T01、T02 | 3 | `backend/app/repositories/attempt_keys.py` |
| T04 | 准入判定与内容版本校验 | AS-07、AS-19a、5.5a、7.4、EX-07/08/09a/09b/12a/13a/28 | P0 | T01、T02 | 3 | `backend/app/repositories/attempt_content.py`、`backend/app/repositories/listening.py`（新增严格包装，不改旧函数） |
| T05 | 判分、快照与练习估分 | AS-01–04、BR-13–17、7.2、D4 | P0 | T02（可与 T03/T04 并行） | 3 | `backend/app/services/grading.py`、`backend/tests/test_attempt_grading.py` |
| T06 | 提交编排与 API-1 | IN1/IN2、AS-01/05/06/08、BR-18/18a/21/22、API-1 | P0 | T03、T04、T05 | 4 | `backend/app/services/attempts.py`、`backend/app/api/attempts.py`、`backend/app/api/deps.py`、`backend/app/main.py` |
| T07 | 权限、错误顺序与既有接口回归 | AS-16/17/18、BR-09–12、V-R1–R4 | P1 | T06 | 5 | `backend/tests/test_attempt_regression.py`、必要时 `deps.py` 注释 |
| T08 | 自动化测试补全与全量回归 | V-01–V-08、V-16–V-23、V-R1–R7 | P1 | T06、T07 | 6 | `backend/tests/test_attempt_api.py`、`test_attempt_regression.py` |
| T09 | 端到端验收脚本 | V-E1、V-E5a、V-E4 可自动部分、11.6 | P1 | T06 | 6 | `backend/scripts/acceptance_attempt.py` |
| T10 | 验收数据准备与真实验收执行 | P2、V-E 系列、11.9(4) | P2 | T09 脚本可用 + 数据可用 | 7 | 受控材料目录（不进 Git）、`docs/acceptance/attempt-system/`（建议） |

> 优先级说明：P0 = 本轮核心闭环，缺一不可；P1 = 合并前必须完成（测试/回归/脚本）；P2 = 依赖外部数据与负责人确认，无法满足时按 BLOCKED 处理并记录，不伪造。

### 3.2 关键依赖图

```text
T01 数据模型/迁移
 └─> T02 契约/schema
      ├─> T03 幂等/标记
      ├─> T04 准入/版本
      └─> T05 判分/快照（纯函数）
            └─> T06 编排/API-1
                 ├─> T07 权限/回归
                 ├─> T08 测试补全
                 └─> T09 端到端脚本
                       └─> T10 真实数据验收（外部依赖）
```

T03/T04/T05 可并行开发，但 T06 必须等三者接口稳定；T07/T08/T09 可并行，共享同一版 T06 契约。

### 3.3 任务与冻结项边界

- 本表不含 API-2、R 组、结果页、前端：它们不是“低优先级任务”，而是**本轮范围外冻结项**（见 4.11）。
- 不把“T11 解析检测”列为任务：它属于题库内容治理，不是作答系统职责（1.3.2 FZ4）。
- 每张任务卡的“明确不做”用于防止顺手扩张；评审时以该列为准。

---

## 4 逐张任务卡

> **通用约定**
> - 每张卡完成后，开发人先在本地按“可复现验收标准”自测，把命令与实际输出写进 PR；**不得只写“已实现/已检查”**。
> - 判定用 `PASS / PARTIAL / FAIL / BLOCKED`：满足全部判据=PASS；主功能可用但存在已登记的未覆盖项=PARTIAL；判据不满足=FAIL；前置环境/数据/签认缺失=BLOCKED。
> - 失败处理是**必填项**：出现 FAIL 时按卡内步骤定位，不得删改验收断言或降低判据来“变绿”。
> - 分支命名 `feature/<Issue 编号>-attempt-tXX-<说明>`；文档改动 `docs/<编号>-attempt-dev-doc`；PR 目标 `develop`，标题 `type(scope): 说明`。

### 4.1 T01 数据模型与 Alembic 迁移

| 项 | 内容 |
|---|---|
| 对应需求 | G1、G7、BR-26、DC-2/DC-6/DC-7/DC-8、7.1–7.3；验收 V-R6（迁移） |
| 依赖 | 无 |
| 优先级/顺序 | P0 / 1 |
| 目标 | 在不改既有表与迁移的前提下，新增 `attempts`、`attempt_answers`、`attempt_rejections` 三张表，单 head、可升级可回退。 |
| 输入与代码入口 | `backend/app/db/base.py:10–22`（Base/命名约定）；`backend/app/db/models_listening.py`（既有模型风格）；`backend/app/db/models.py:24–47`（users 类型）；`backend/alembic/versions/0004_expected_count_source.py:15–16`（父迁移）；`backend/alembic/env.py:9–11`（模型注册）；本文 2.3 |
| GitHub 参考 | 2.11.3 Alembic（单链、`heads`、`downgrade`）；2.11.2 SQLAlchemy（`UniqueConstraint`/`Index`/`CheckConstraint`）；2.11.5 PostgreSQL（约束/JSONB） |
| 实施步骤 | 1) 新建 `models_attempt.py`，按 2.3.2–2.3.4 定义 3 个模型与全部约束/索引（显式名称）；<br>2) 在 `alembic/env.py` 增加 `models_attempt` 的 `noqa` 导入；<br>3) 新建 `0005_attempt_system.py`：`revision="0005_attempt_system"`、`down_revision="0004_expected_count_source"`，`upgrade()` 按依赖顺序建表/索引，`downgrade()` 逆序删表；<br>4) 手写迁移后与模型逐列核对（类型、空值、默认值、约束名）；<br>5) 在空测试库与已有开发库副本分别执行升级/降级；<br>6) 记录 `alembic heads`、`history`、表/索引清单到 PR。 |
| 交付物 | `models_attempt.py`；`0005_attempt_system.py`；`env.py` 一行注册；迁移说明（升级/降级命令、预期输出、数据影响）。 |
| 可复现验收标准 | **T01-A1** `python -m alembic heads` 输出且仅输出 `0005_attempt_system (head)` → PASS；多 head=FAIL。<br>**T01-A2** 空库 `python -m alembic upgrade head` 成功，`attempts/attempt_answers/attempt_rejections` 三表存在，列/约束/索引与 2.3 一致（用 `information_schema` 或 `\d+` 核对）→ PASS。<br>**T01-A3** `python -m alembic downgrade 0004_expected_count_source` 后三表与索引全部消失，模块二 11 表仍在；再 `upgrade head` 成功 → PASS。<br>**T01-A4** `git diff --stat` 显示 `0001–0004` 未改；实际运行 `pytest -v`，既有用例全部通过（**不预设 29/34 等静态计数**；以实际收集数为准，若环境不可用标 BLOCKED 并转 T08）→ PASS/BLOCKED。<br>**T01-A5** 抽查约束生效：同学生同键插两条 → 唯一冲突；`is_correct` 与 `selected/correct` 矛盾 → CHECK 拒绝 → PASS。<br>**T01-A6** `python -m alembic check` 无待生成变更（模型 metadata 与迁移一致；若该命令不适用于手写迁移，改为 `alembic revision --autogenerate` 生成的 diff 为空并删除临时文件）→ PASS。 |
| 失败处理 | 迁移中途失败：PostgreSQL DDL 事务会回滚，先 `alembic current` 确认；禁止改 `0004` 或手工改库“绕过”。多 head：修正 `down_revision` 或按 Alembic 文档合并，不得用 `stamp` 掩盖。约束名冲突：按命名约定改名后重建迁移。既有测试失败：先回退到 T01 分支起点复跑，区分“迁移导致”与“环境导致”；记录 BLOCKED 原因。 |
| 明确不做 | 不改模块一/二表；不建 API-2/结果表之外的表；不写数据回填；不引入扩展（如 pgcrypto）。 |

### 4.2 T02 请求/响应契约与 schema

| 项 | 内容 |
|---|---|
| 对应需求 | AS-01/AS-02、EX-16/18/19/20、BR-19、8.4；本文 2.4/2.7 |
| 依赖 | T01 |
| 优先级/顺序 | P0 / 2 |
| 目标 | 固化 API-1 的**请求/响应模型与字段级约束**（模型层），为 T04/T06 提供稳定输入输出；不在本卡实现路由、HTTP 状态码或 OpenAPI path。 |
| 输入与代码入口 | `backend/app/schemas.py:6–9`（`ApiResponse[T]`）；`backend/app/schemas_listening.py:29–59,138–140`（既有模型与 `Field(pattern)` 风格）；`backend/app/main.py:42–50`（422 固定文案）；本文 2.4.1–2.4.2、2.7.1 |
| GitHub 参考 | 2.11.1 FastAPI（response_model 结构参考）；2.11.4 Pydantic v2（`Field`/`pattern`/必填字段） |
| 实施步骤 | 1) `schemas_attempts.py` 定义严格 ID 类型 `JsonId = Annotated[int, Field(strict=True, gt=0, le=2**63-1)]`；`AttemptAnswerIn`（`question_id: JsonId`、`selected_option: Literal["A","B","C","D"]` 或 pattern）、`AttemptSubmitIn`（`loaded_question_ids: list[JsonId]` **必填、不加 `min_length`**，由服务层判空→400；`answers: list[AttemptAnswerIn]` **必填**允许空数组）；路径 `exam_paper_id` 由 T06 定义 `PathId`，**不复用 JSON strict 类型**；本卡不引入路径解析；<br>2) 定义 `PracticeScoreData`、`AttemptSubmitData` 与响应模型 `ApiResponse[AttemptSubmitData]`；<br>3) 定义幂等键校验纯函数 `validate_idempotency_key(value) -> bool`（**UUIDv4 规范字符串**，36 字符、版本位 `4`、变体位 `8/9/a/b`；供 T06 路由调用），不在本卡解析 Header；<br>4) 统一错误 `msg` 常量（E03–E09）供服务层复用；<br>5) 只写模型级单测（直接构造/解析模型），**不写 HTTP/路由断言**；路由、Header、OpenAPI 与状态码由 T06 负责。 |
| 交付物 | `schemas_attempts.py`；`msg` 常量；`validate_idempotency_key` 纯函数；模型级单测；契约字段清单（供 T06 组装）。 |
| 可复现验收标准 | **T02-A1** 合法请求字典 → 模型解析成功，字段与 2.4.2 一致 → PASS。<br>**T02-A2** `answers` 缺失 → 模型 `ValidationError`；`answers=[]` → 解析成功 → PASS（HTTP 422 由 T06 验）。<br>**T02-A3** `selected_option="E"`/`"a"`、`question_id=0` → 模型 `ValidationError`；`question_id="1"`/`1.0`/`true`/超 `2^63-1` → 必须 `ValidationError`（strict，不静默转换）→ PASS。<br>**T02-A4** `loaded_question_ids=[]` 可通过模型（判空属服务层，**T06-A12 验 400 E07**）；元素为 `"1"`/`1.0`/`true`/越界 → `ValidationError` → PASS。<br>**T02-A5** `validate_idempotency_key` 对缺失/非 UUIDv4/版本位非法/超长返回 False，合法 UUIDv4（36 字符）返回 True → PASS（Header→400 由 T06-A12 验）。<br>**T02-A6** 响应模型字段集合不含答案/解析/正文/逐题正误/内部 ID → PASS。 |
| 失败处理 | 若模型约束与需求冲突（如 EX-20 期望 422），不私自改需求；登记 D-01/D-02/T7 请负责人裁定，暂按本文执行并在 PR 标“口径待确认”。若模型改动破坏既有 schema，回退并拆分模型，不复用/修改既有 `ApiResponse`。 |
| 明确不做 | 不实现路由/Header 解析/OpenAPI path/HTTP 状态码（T06）；不把“整卷集合完整/版本一致/限次”等业务规则放进 schema；不新增全局异常处理器；不改既有 422 文案。 |

### 4.3 T03 幂等仓储、短路与拒绝标记

| 项 | 内容 |
|---|---|
| 对应需求 | L-G8、BR-19a–d、BR-20、AS-06/07、7.3、7.6；EX-20–EX-26 |
| 依赖 | T01、T02 |
| 优先级/顺序 | P0 / 3 |
| 目标 | 提供“按 `(student_id, attempt_key)` 查成功/拒绝、写永久标记、限次计数、两把事务锁、请求指纹”的数据访问能力，并保证短路先于内容/准入核对。 |
| 输入与代码入口 | `backend/app/db/models_attempt.py`（T01）；`backend/app/db/base.py:42–49`（会话）；`backend/app/repositories/listening.py:30–65`（查询风格）；`backend/app/core/errors.py:39–48`；本文 2.6；**文件：`repositories/attempt_keys.py`（与 T04 的 `attempt_content.py` 分离，避免并行写同一文件）** |
| GitHub 参考 | 2.11.2 SQLAlchemy（`select`/`IntegrityError`/事务）；2.11.5 PostgreSQL（唯一约束、`ON CONFLICT`、advisory lock）；2.11.6 IETF draft（指纹/复合键/并发语义） |
| 实施步骤 | 1) 实现 `get_attempt_by_key`、`get_rejection_by_key`、`count_success_attempts`、`insert_rejection`、`insert_attempt_with_answers`（只 add/flush，不 commit）；<br>2) 实现 `build_request_fingerprint`：按 2.6.1 规范化串取 SHA-256；输入为已通过 schema 的模型；<br>3) 实现 `resolve_existing(db, student_id, key, fingerprint)` 返回四种结果：`REPLAY_SUCCESS`/`KEY_CONFLICT`/`REJECTED`/`NONE`；<br>4) 标记写入处理唯一冲突：已存在则读取并返回同一结论；不存在则插入（同一事务）；<br>5) 实现 `lock_attempt_key`（classid=1）与 `lock_student_paper`（classid=2）两个 `pg_advisory_xact_lock` 包装；`objid = int.from_bytes(sha256(text.encode("utf-8")).digest()[:4], "big", signed=True)`，**禁止 Python `hash()`/数据库 `hashtext()`**；供 T06 按 2.6.2 顺序使用；<br>6) 标记写入处理“先提交再抛异常”：或由服务层调用 `db.commit()` 后 raise，仓储层不得把标记与后续业务回滚绑死；`commit` 结果未知按 2.6.4 处理；<br>7) 并发/冲突路径写集成测试（T08 补全，本卡至少 3 个）；加“不同进程/实例对同一文本得到同一 objid”的单测； |
| 交付物 | 仓储函数；指纹函数；短路结果类型（Enum/常量）；标记写入逻辑；2–3 个集成测试；PR 记录“同键并发只产生 1 条”的实际输出。 |
| 可复现验收标准 | **T03-A1** 同键同内容首次写入后调用 `resolve_existing` → `REPLAY_SUCCESS`，返回原 `attempt_code` → PASS。<br>**T03-A2** 同键不同指纹 → `KEY_CONFLICT`，不新增记录、不留标记 → PASS。<br>**T03-A3** 不存在的键 → `NONE` → PASS。<br>**T03-A4** 写 `paper_not_accessible` 标记后同键重试 → `REJECTED`，标记数不增、无 attempt → PASS。<br>**T03-A5** 两并发事务同键写入 → 数据库仅 1 条 attempt；失败方回滚后重读得到同一结果 → PASS。<br>**T03-A6** 指纹规范化：答案顺序不同但内容相同 → 同指纹；内容/试卷不同 → 不同指纹 → PASS。<br>**T03-A7** 锁键算法：同一 `attempt-key`/`attempt-limit` 文本在两个独立进程得到同一 int32 且与 `sha256[:4]` 大端有符号公式一致；不使用 `hash()`/`hashtext()` → PASS。 |
| 失败处理 | 若唯一约束未生效：先查迁移是否创建，补迁移而非应用层“先查后插”。标记写入冲突无法区分：检查是否同事务内混用 stale session，回滚后重读。并发测试偶发失败：用 `threading.Barrier` 固定时序，不用 `sleep` 掩盖；仍失败则标 FAIL 并排查隔离级别。 |
| 明确不做 | 不做过期清理；不做 Redis/分布式锁；不在仓储层 commit；不把“键冲突”写成永久标记。 |

### 4.4 T04 准入判定与内容版本校验

| 项 | 内容 |
|---|---|
| 对应需求 | AS-07、AS-19a、5.5a、7.4、EX-07/08/09a/09b/12a/13a/28；BR-01/02（提交侧） |
| 依赖 | T01、T02 |
| 优先级/顺序 | P0 / 3 |
| 目标 | 在提交时点复用模块二“学生可访问”判定（**准入优先**）；在可访问后把“加载时整卷题目身份集合”与当前批次逐项比对，正确区分“旧批次”（`version_mismatch`）与“参数非法”（`invalid_identity`/`incomplete`），并按 5.5a 固定分类优先级（D-16）。本卡只返回结构化判定，不写标记、不返回 HTTP。 |
| 输入与代码入口 | `backend/app/repositories/listening.py:71–87`（`student_access`）、`:34–41`（当前批次）、`:138–172`（映射换算）；`backend/app/db/models_listening.py:261–343`（Question/Presentation）；`backend/app/core/config.py:78–81`（音频目录属性）；本文 2.4.2、2.6.2、5.5a；**文件：`repositories/attempt_content.py`（与 T03 的 `attempt_keys.py` 分离）** |
| GitHub 参考 | 2.11.2 SQLAlchemy（`select`/join）；2.11.1 FastAPI（依赖复用）；2.11.5 PostgreSQL（只读事务一致性） |
| 实施步骤 | 1) `check_submit_access(db, paper_id)`：调用 `student_access`，返回 `(visible, paper, batch)`；**这是提交链的第一步业务判定（6b），不可与身份分类交换**；<br>1b) `check_paper_integrity(db, paper, batch, settings)`：通过 `db` 读取该 `batch_id` 下的 `questions`/`presentations` 与 `audio_files`（`paper.playback_audio_id`），检查：`expected_question_count` 及来源非空；`len(questions)==expected_question_count`；`len(presentations)==len(questions)` 且每题恰有一个映射；题号覆盖 `1..expected_question_count`（**N 必须取自 `paper.expected_question_count`，不得用剩余题数**）；映射 A–D 排列；**提交时音频存在且可读**（`audio_files.storage_key` → `audio_storage_path`；先 `is_file()`，再 `os.access(path, os.R_OK)` 或显式打开读取一小段作可读性校验）；失败返回 `PaperUnavailable(reason)`，由 T06 统一映射为 404（**数据异常不写永久标记**，D-20 建议口径）；<br>2) `load_current_paper_questions(db, paper_id, batch_id)`：**必须传入 6b 返回的 `batch_id`**（不再自行取“当前批次”，避免换批窗口）；按该批次取 `questions` + `presentations` + `passages.passage_type`，按 `question_no` 升序返回；<br>3) `classify_loaded_ids(db, paper_id, current_ids, loaded_ids)`：按 D-16 优先级分类：**任一旧批次 → `version_mismatch`（优先）**；否则任一他卷/不存在 → `invalid_identity`；否则真子集/不等 → `incomplete`；否则 `ok`；<br>4) `validate_answers(loaded_ids, current_ids, answers)`：重复、越界、答案含集合外 ID；<br>5) 将“旧批次身份”判定所需查询封装为只读函数（questions→presentations→exam_paper_id）；<br>6) 编写仓储级测试：可访问/不可访问（含不存在的 paper）、音频缺失、换批前后、子集、他卷、重复、混合身份、**删除末尾整题及映射但历史检查通过**。**不写 HTTP/标记断言**（由 T06-A13 覆盖）。 |
| 交付物 | 整卷读取函数；严格映射/音频完整性函数；身份分类函数；答案校验函数；准入复用函数；仓储级测试；一页“判定表实现对照”（5.5a 逐行）。 |
| 可复现验收标准 | **T04-A1** 可访问试卷 + 完整 loaded set + 合法 answers → 返回 `ok` 与固定 `batch_id`（交给 T06）→ PASS。<br>**T04-A2** 取消可见后调用 → `visible=False`（仓储级；404+标记由 T06-A6 验）→ PASS。<br>**T04-A2b** 不存在的 `exam_paper_id` → `visible=False`（T06-A13 验 404+标记）→ PASS。<br>**T04-A3** 可访问试卷、用旧批次题目身份 → 返回 `version_mismatch`（T06-A13 验 400 E04+标记）→ PASS。<br>**T04-A4** **可访问**试卷、提交他卷/不存在题目身份 → 返回 `invalid_identity`（T06-A13 验 400 E07 无标记）→ PASS。<br>**T04-A5** loaded set 为当前批次真子集 → `incomplete`；完全一致但乱序 → `ok` → PASS。<br>**T04-A6** 重复 `question_id`、答案含集合外 ID → 返回参数错误（T06 验 400 无记录无标记）→ PASS。<br>**T04-A7** 换批发生在加载前（看到新批）→ 按新批 `ok`（T06 落库）→ PASS。<br>**T04-A8** 混合身份（旧批次 + 他卷）→ 按 D-16 **优先返回 `version_mismatch`**（T06 写 version 标记）→ PASS。<br>**T04-A9** 提交时音频文件缺失/存在但不可读（`is_file()`/`os.access` 或打开校验失败）→ 返回 `PaperUnavailable(audio_unavailable)`（T06-A13 验 404 **不写永久标记**、无 attempt；修复后同键可重试）→ PASS。<br>**T04-A10** 原卷应有 25 题，删除第 25 题及其映射、保留历史检查通过记录 → `check_paper_integrity` 必须返回 `PaperUnavailable`（题量/题号覆盖不一致），T06-A13 验 404 E14、无 attempt；**不得把剩余 24 题当整卷** → PASS。 |
| 失败处理 | 若无法区分旧批次与他卷（题目 ID 跨批次复用）：先停，核对 `import_module2.py` 是否每批新建题目行；若确认为复用，需改模块二数据模型（超出本轮），标 BLOCKED 并请负责人裁定。若旧批次行已被物理删除，版本检测不可用：按“参数非法”或“不可访问”fail-closed，记录数据缺口，不得默认放行。音频检查仅覆盖提交时点；确认可见后音频被删的窗口由 T06-A13/M-29b 覆盖。 |
| 明确不做 | 不重做内容检查；不写拒绝标记/不 commit（由 T06 统一事务）；不把标注审核/模块三验收并入准入；不修改可见性状态。 |

### 4.5 T05 判分、快照与练习估分

| 项 | 内容 |
|---|---|
| 对应需求 | AS-01–04、BR-13–17、7.2 S-1–S-9、D4；G5/G6 |
| 依赖 | T02（输入模型可先约定；纯函数不依赖 DB） |
| 优先级/顺序 | P0 / 3 |
| 目标 | 以纯函数实现“逐题判分 + 快照 + 汇总 + 249 估分”，同字母空间、空解析安全、估分不可用时可判定。 |
| 输入与代码入口 | `backend/app/repositories/listening.py:138–172`（映射/答案换算；由 T04 严格版包装）；`backend/app/db/models_listening.py:184–307`（Passage/Question 字段）；本文 2.5 |
| GitHub 参考 | 2.11.7 CPython（Decimal/Fraction、round-half-even 风险）；2.11.2 SQLAlchemy（与 DB 解耦的纯函数设计） |
| 实施步骤 | 1) 定义纯输入结构 `QuestionSnapshotInput`（`question_no/question_id/passage_type/question_text/options[4]/correct_paper_letter/explanation_text`）与 `AnswerInput`；<br>1a) 输入由 T04 的整卷读取函数提供，并在该处执行严格映射校验（见 2.5.2“严格校验”）；`grading.py` 不自行调用带兜底的旧函数；<br>2) 实现 `grade(questions, answers)`：按题号遍历、未作答计错、生成 `AttemptAnswerDraft` 列表、统计 `correct_count/question_count`；<br>3) 实现 `correct_rate` 整数 half-up（2.5.3）；<br>4) 实现 `estimate_practice_score(facts)`：三组权重、25 题校验、`Fraction` 精确计算、half-up、不可用原因枚举、`score_breakdown`；<br>5) 实现空解析/空白解析原样快照；<br>6) 用表驱动测试覆盖 2.5 全部示例与边界。 |
| 交付物 | `grading.py`；快照/汇总数据结构；估分规则常量 `CET_LISTENING_249_V1`；表驱动测试；一页“公式与示例”自检记录。 |
| 可复现验收标准 | **T05-A1** 25 题全对：正确率 100、估分 249、每题目 is_correct=true → PASS。<br>**T05-A2** 24/25 且错题位于“听力篇章”（新闻 7/7、长对话 8/8、篇章 9/10）：正确率 96；估分 235、标注可用；若错题位于其他题型，按公式重新计算（不固定 235，避免验收争议）→ PASS。<br>**T05-A3** 部分作答 + 空 answers：未作答计错、正确率/估分按公式、`selected_option=NULL` → PASS。<br>**T05-A4** 重排题：正确文字所在原卷字母判对，错位判错；快照选项为原卷顺序 → PASS。<br>**T05-A5** 空解析：快照空串、无占位；估分/正确率不受影响 → PASS。<br>**T05-A6** 分别构造并断言 reason：题数≠25→`not_standard_25`；某题无题型→`question_type_missing`；出现未知类型→`unknown_type`；题数 25、类型齐全但数量非 7/8/10→`type_count_mismatch`；同时 `available=false`、`practice_score=NULL` → PASS。<br>**T05-A7** 舍入边界：1/3→33、2/3→67、**1/8→13（12.5 半入）**、0/25→0、25/25→100；无 float 参与（代码审查）→ PASS。<br>**T05-A8** 正确率与估分分开输出、无互替（字段断言）→ PASS。 |
| 失败处理 | 若公式示例与实现不一致：以需求 BR-16a（0–249、按题型占比、全对≈249、全错 0、非官方）为约束，先修正实现；若“≈249”导致边界歧义（如 248.999→249），登记为**取整边界待确认项**（D-19，不占用 D-08 的 D10/D11 语义）请负责人确认，不静默改公式。若题型名称与题库实际值不符：以受控样例实际枚举为准，更新映射表并在测试冻结；未知类型不得猜测归类。 |
| 明确不做 | 不引入逐题分值/可配置权重（OUT10）；不按百分制归一；不读数据库（纯函数）；不实现官方分数换算。 |

### 4.6 T06 提交编排与 API-1

| 项 | 内容 |
|---|---|
| 对应需求 | IN1/IN2、API-1、AS-01/05/06/08、BR-18/18a/21/22/27、BR-09/10；EX-21–EX-26 |
| 依赖 | T03、T04、T05 |
| 优先级/顺序 | P0 / 4 |
| 目标 | 按 2.6.2 固定顺序实现 API-1：认证→角色→契约→短路→校验→准入→版本→限次→判分→单事务落库；任何失败无半成品。 |
| 输入与代码入口 | `backend/app/api/deps.py:67–106`（鉴权依赖）；`backend/app/core/errors.py`（`ok/bad_request/forbidden/not_found`）；`backend/app/main.py:73–76`（挂载）；T03/T04/T05 产物 |
| GitHub 参考 | 2.11.1 FastAPI（路由/依赖/Header）；2.11.2 SQLAlchemy（单事务/`IntegrityError`）；2.11.5 PostgreSQL（advisory lock）；2.11.6 IETF（幂等/并发） |
| 实施步骤 | 1) `deps.py` 增加 `require_student`（先 401；`is_admin` → 403；无 student 角色 → 403）；<br>2) `api/attempts.py` 定义 `POST /listening-papers/{exam_paper_id}/attempts`，定义 `PathId = Annotated[int, Path(gt=0, le=2**63-1)]` 解析路径整数文本；请求体使用 T02 的 `JsonId`；解析 `Idempotency-Key` Header，注入 `Settings` 并传给服务，调用服务；<br>3) `services/attempts.py` 按 2.6.2 顺序编排；先 `lock_attempt_key`；6b 调 `check_submit_access(db, paper_id)` + `check_paper_integrity(db, paper, batch, settings)`（音频/数据）取 `(paper, batch)` 后**固定 `batch_id`**，6c 整卷读取/第 7 步判分/`import_batch_id` 全部用该值；短路后再 `lock_student_paper` + `count_success_attempts`；<br>4) 判分结果 + 快照写入 `attempts`/`attempt_answers`，**单次 commit**；拒绝标记必须先 commit 再抛 404/400；<br>5) 按 2.6.4 处理事务错误：结束失败事务，在新事务重新取键锁再重读两表；有成功/标记才回放，无记录按当前状态重新校验，读取失败仍 500；未知提交不承诺成功或原拒绝；<br>6) 组装 `AttemptSubmitData`（2.4.2 字段，逐题项不返回）；<br>7) 在 `main.py` 挂载 router；<br>8) 编写 API 集成测试（正常/空卷/部分/限次/重试/键冲突/准入/版本/管理员/无 token/失败注入/并发）；<br>9) 为 T02/T04 移交的路由级验收项补用例：Header 缺失/非法 400、422 与 401 顺序、404/400+标记；这些属 T06 集成验收，不再由 T02/T04 承担；<br>10) 覆盖执行/提交/回滚/重读异常，按 2.7.3 安全记录并转换 AppError，不让原始 SQL/异常链进入全局日志；<br>11) 增加不同键同卷并发限次自测 T06-A14 及日志捕获 T06-A15，默认口径自测与 M-32 需求验收分开记录。 |
| 交付物 | `api/attempts.py`；`services/attempts.py`；`deps.require_student`；`main.py` 挂载；API 集成测试；PR 内附：成功响应样例、库内行数 SQL、同键/不同键并发技术输出、未知提交状态分支记录、日志脱敏捕获证据；均待实际执行。 |
| 可复现验收标准 | **T06-A1** 可访问试卷完整提交 → 200，`data` 含 2.4.2 全部字段；库内 attempt=1、answers=25 → PASS。<br>**T06-A2** 部分作答（试卷 P1）与空 answers（试卷 P2，独立夹具）→ 200；正确率按 25 分母；未作答计错；避免同卷连续成功触发 BR-18a → PASS。<br>**T06-A3** 同键同内容连发两次 → 两次同一 `attempt_code`，库内 1 条 → PASS。<br>**T06-A4** 同键不同答案（同卷 A）→ 400 E09；库内不增、无标记；**改用新键提交 A → 400 E08，成功记录仍 1 条**。同键换试卷 B → 400 E09；改用新键提交可访问且尚未成功作答的 B → 200。**不得用“换新键可成功”概括同卷 A** → PASS。<br>**T06-A5** 1.5 例外生效前：同卷不同键第二次 → 400 E08，库内仍 1 条 → PASS。<br>**T06-A6** 取消可见后提交 → 404 E03 + 1 条 `paper_not_accessible` 标记（响应后立即查库，证明标记已提交而非被回滚），无 attempt；恢复后旧键仍 404，新键可提交 → PASS。<br>**T06-A7** 加载后换批 → 400 E04 + 1 条 `content_version_mismatch` 标记；不落库；旧键永不复用 → PASS。<br>**T06-A8** 管理员提交 → 403；无 token → 401（即使试卷不存在）→ PASS。<br>**T06-A9** 三类提交失败分别验证：① **提交前失败**（flush/校验/事务前故障）→ 回滚后 attempt/answers 0 行、无半成品；② **COMMIT 结果未知**：分别验证实际已提交/未提交；查到成功或标记按原规则回放，两表无记录才按当前状态重判；未提交后试卷下线可 404、未落标记后恢复可成功；读取失败仍 500。不得承诺 0 行、重试必成功或原拒绝必不变；③ **已提交但响应丢失** → 同键重试返回原结果、不新增记录。不得只用“commit 前抛异常”覆盖全部失败语义 → PASS。<br>**T06-A10** 同键并发（Barrier 两线程）→ 仅 1 条 attempt；两个响应均为 200 且同一 `attempt_code`（键锁内后到者走 5a 回放；**不得 2 条，也不以“明确失败”放宽**）→ PASS。<br>**T06-A11** 响应无答案/解析/正文/逐题正误/内部 ID → PASS（红线）。<br>**T06-A12** 路由级契约：合法路径 `/1` 必须通过参数解析；路径 0/负数/超 BIGINT 上限在已认证且角色通过时 422，JSON 字符串/浮点/布尔 ID 仍 422；各成功子场景用独立夹具。缺失/非法 `Idempotency-Key` → 400 E05；`answers` 缺失 → 422；**`loaded_question_ids=[]` → 400 E07**；**无 token + 非法 body → 401（不得 422）**；无 token + 合法 body + 不存在试卷 → 401。若实测框架先返回 422，视为缺陷，须把鉴权前置（路由级依赖/中间件）后重测，不得接受 422；若确认框架不可控，须登记 D-21 请负责人裁定 → PASS/BLOCKED。<br>**T06-A13** 从 T04 移交的 HTTP/标记断言：取消可见/不存在试卷→404+access 标记；音频缺失/映射异常→404 E14，**不写永久标记**（D-20 建议口径）；旧批次→400 E04+version 标记；他卷/不存在身份→400 E07 无标记；标记按已确认口径提交后立即查库 → PASS。<br>**T06-A14（实现自测）** 同学生、同卷、不同键，两个独立数据库会话用同步钩子竞争限次检查；无故障时响应为 200 与 400 E08，仅 1 条完整 attempt、无永久拒绝标记；能识别移除限次锁后的竞态。按 6.3a 回填默认策略技术结果，**不计矩阵通过率、不替代 M-32/M-41 的 BLOCKED 或 D11/D-14 决策**。<br>**T06-A15** 执行/flush/commit/rollback/重读及驱动 DETAIL 异常均注入虚构敏感标记；捕获服务和全局最终日志，所选/正确答案、解析、正文、完整键及异常链中的标记均不存在，安全定位字段仍可用 → PASS。 |
| 失败处理 | 见 2.6.4：提交前失败必须 rollback、不得留半成品；COMMIT 结果未知不得断言“0 行”，由同键重试与持久化记录确认；已提交但响应丢失由 5a 回放。不得吞异常返回 200。并发出现 2 条：停止合并，检查唯一约束/事务边界/advisory lock，修复后重跑；不得改断言。限次与限次锁失效：核对锁键与 `count` 是否同事务。若 400/409 口径被否决（D-01），统一改错误映射并同步测试与本文，不零散改。 |
| 明确不做 | 不实现 API-2；不返回逐题正误；不新增“已交卷”分支；不写模块二表；不做限流。 |

### 4.7 T07 权限、错误顺序与既有接口回归

| 项 | 内容 |
|---|---|
| 对应需求 | AS-16/17/18、BR-09–12、V-R1–R4；R1 |
| 依赖 | T06 |
| 优先级/顺序 | P1 / 5 |
| 目标 | 证明新接口未破坏既有鉴权顺序与学生内容裁剪；管理员不能代答；既有 6 接口语义不变。 |
| 输入与代码入口 | `backend/app/api/deps.py`；`backend/app/main.py:33–70`；`backend/app/api/listening_papers.py`；`backend/app/api/admin_listening_papers.py`；`backend/app/repositories/listening.py:175–217`；`backend/tests/test_security_edges.py`、`test_module2_listening.py` |
| GitHub 参考 | 2.11.1 FastAPI（依赖顺序/401→403）；2.11.8 pytest（回归/参数化） |
| 实施步骤 | 1) 补 `require_student` 用例：无 token、失效 token、admin、无 student 角色、正常 student；<br>2) 断言顺序：无 token + 不存在试卷 → 401；admin + 不存在试卷 → 403（不得先 404）；student 读他人/不存在 → 相关既有 404；<br>3) 交卷前后调用模块二详情/音频，字段集合与响应一致；<br>4) 学生调管理员 3 接口仍 403；音频 Range 行为不变；<br>5) 在隔离测试库运行模块二与模块一全量测试；<br>6) 验证作答错误经 AppError 返回固定 500 外壳，不进入原始异常日志；检查 T06-A15 的最终服务/全局输出，既有 HTTP 契约不变。 |
| 交付物 | `test_attempt_regression.py`；权限/顺序断言清单；交卷前后字段集合对比输出；既有测试全绿记录。 |
| 可复现验收标准 | **T07-A1** 无 token 调 API-1 → 401；admin 调 API-1 → 403；学生正常 → 200 → PASS。<br>**T07-A2** 无 token + 不存在 paper → 401；admin + 不存在 paper → 403；学生 + 不可见 → 404 → PASS。<br>**T07-A3** 交卷前后学生详情 JSON 字段集合完全一致，均无 `correct_option/explanation_text/segments` → PASS。<br>**T07-A4** 音频 `Range: bytes=0-1023` 仍 206，完整请求仍 200，不可见/未绑定仍 404 → PASS。<br>**T07-A5** 学生调 `/admin/...` 3 接口仍 403；管理员仍可正常调用 → PASS。<br>**T07-A6** `pytest -v` 既有全部用例 + 新增回归用例通过 → PASS。<br>**T07-A7** 数据库执行/提交等错误响应仍为既有 `{code:500,msg:"服务器内部错误",data:null}`；最终日志无敏感参数、驱动 DETAIL 或异常链泄露，且错误定位信息存在；实际覆盖 M-23a → PASS。 |
| 失败处理 | 若出现“交卷后详情多字段/少字段”：视为红线（V-R2/AS-18），回退 T06 中任何详情改动；本卡不允许通过修改既有接口来“对齐”。若 401/403 顺序失败：检查依赖是否被服务层提前做 404 判断；调整顺序而非改断言。 |
| 明确不做 | 不改既有接口契约；不新增管理员结果接口；不修改鉴权实现。 |

### 4.8 T08 自动化测试补全与全量回归

| 项 | 内容 |
|---|---|
| 对应需求 | V-01–V-08、V-16–V-23、V-R1–R7；验收矩阵 A/C/D 可自动项 |
| 依赖 | T06、T07 |
| 优先级/顺序 | P1 / 6 |
| 目标 | 让第 5 节矩阵中所有本轮可执行项都有对应自动化用例（或明确标为人工/端到端），并在 CI/本地一键跑通。 |
| 输入与代码入口 | `backend/tests/conftest.py:53–127`；既有测试风格；第 5 节矩阵 |
| GitHub 参考 | 2.11.8 pytest（fixture/parametrize/断言）；2.11.1 FastAPI（TestClient） |
| 实施步骤 | 1) 按矩阵逐行建立用例映射（用例名含需求编号/矩阵编号）；<br>2) 参数化覆盖：状态码分支、字母、空卷、部分、旧批/他卷、重复、缺键、非法键；<br>3) 同键并发用独立会话与同步钩子；另为 T06-A14 固定不同键同卷竞争限次的时序，检查移除限次锁时可发现竞态；失败注入用 `monkeypatch`，仅替换受控故障点；<br>3a) 增加 M-12a 快照不漂移用例：提交后直接在测试库改题库内容，只读 SQL 断言 `attempt_answers` 不变（AS-14/BR-23 提交侧）；<br>4) 迁移用例：`heads` 单 head、upgrade/downgrade/upgrade（可在脚本/CI 单独执行，不放进每次 pytest）；<br>5) 测试数据夹具：新增“按用例独立导入的可见试卷”工厂（含 25 题标准卷与 1 题卷两种），避免 BR-18a 限次导致用例顺序互相污染；**另建双批次夹具**（同一试卷导入第二批次并切换 active/check/visibility），供 M-06/M-22 使用；**不改 conftest 的建库/迁移/种子逻辑**；<br>6) 500 注入用例使用 `TestClient(app, raise_server_exceptions=False)`（或断言异常后查库），否则拿不到 500 响应；<br>7) 并发/时序用例提供可注入钩子（如 monkeypatch 服务层检查点/事务回调）以固定 EX-25 两种顺序；无钩子时 M-33 标 BLOCKED-并发，不得用“人工观察”冒充可重复验收；<br>8) 输出矩阵覆盖率表（哪些矩阵行由哪个用例覆盖，哪些留人工/端到端）；<br>9) 全量回归并记录命令/结果/环境；<br>10) 覆盖 T06-A9 的已提交/未提交及状态变化分支，捕获 T06-A15/T07-A7 最终日志；不同键限次自测单列 6.3a，不将 M-32 的 BLOCKED 改写为 PASS。 |
| 交付物 | `test_attempt_api.py`、`test_attempt_regression.py` 完整用例；按用例独立试卷夹具（25 题标准卷/1 题卷）；矩阵覆盖表；全量测试输出（真实运行，不得预填）。 |
| 可复现验收标准 | **T08-A1** 矩阵中标注“自动化”的 A/C/D 行全部有对应用例，无遗漏 → PASS。<br>**T08-A2** `python -m pytest -v` 全绿；失败/跳过（skip/xfail）为 0；若确有环境阻塞，逐项标 BLOCKED 并说明 → PASS/PARTIAL。<br>**T08-A3** 迁移往返命令成功（单 head、downgrade/upgrade）→ PASS。<br>**T08-A4** 并发用例连续运行 10 次无 flaky（记录次数与结果）→ PASS。<br>**T08-A5** 红线断言（学生响应无答案/解析/正文；管理员 403；未认证 401）全部存在 → PASS。<br>**T08-A6** 快照不漂移（M-12a）：提交后在测试库改题干/选项/答案/解析，只读 SQL 查 `attempt_answers` 仍为提交时值；无更新接口/路径 → PASS。<br>**T08-A7** 换批/时序夹具：双批次夹具可稳定构造 M-06/M-22；M-33 有注入钩子时跑通两种顺序，无钩子则标 BLOCKED-并发并说明 → PASS/BLOCKED。<br>**T08-A8** 同键互斥 SQL 断言：并发/重试用例结束后 `attempts` 与 `attempt_rejections` 不为同一 `(student,key)` 同时存在行（DB 无跨表约束，应用层保证）→ PASS。<br>**T08-A9** M-23a 日志捕获断言齐全，服务层及全局输出无测试敏感标记 → PASS。<br>**T08-A10（实现自测）** T06-A14 的双会话/不同键场景有明确同步点、行数及响应证据，并单列口径状态；D11/D-14 未确认时不得据技术结果认定 V-21/V-E4 通过。 |
| 失败处理 | 不得用 skip/xfail 掩盖失败；若环境缺 PostgreSQL/权限，标 BLOCKED 并给出复现命令。并发 flaky：定位时序/隔离/锁，不允许加重试装饰器“变绿”。测试数据污染：每个用例独立键/独立试卷，避免顺序依赖。 |
| 明确不做 | 不用 Mock 替代真实 DB 断言；不改测试夹具的建库逻辑；不为追求覆盖率写无意义断言。 |

### 4.9 T09 端到端验收脚本

| 项 | 内容 |
|---|---|
| 对应需求 | V-E1、V-E5a、V-E4 当前限次行为、11.6；R7-06；需求冲突行 M-41 仍 BLOCKED |
| 依赖 | T06；真实运行还需 T10 准备专用样例和预检记录 |
| 优先级/顺序 | P1 / 6 |
| 目标 | 通过正式 API 登录、提交、重试并验证结果的**有写入验收流程**；会产生永久作答/拒绝标记，并可能临时改变专用样例可见性。只读限制用于 T10 的 SQL 核验，不用于描述整个脚本；真实运行和最终回填由 T10/独立验收人负责。 |
| 输入与代码入口 | `backend/scripts/acceptance_module2.py`（HTTP/退出码模式）；本文 2.4/2.6；T10 提供专用试卷、学生及预检记录。 |
| GitHub 参考 | 2.11.8 httpx、2.11.1 FastAPI；不引入新依赖。 |
| 实施步骤 | 1) 参数要求 `--base-url`、`--paper-id`、`--student-user`、`--admin-user` 明确指定；缺少目标退出码 2，不自动选择列表中任意共享试卷；密码按既有安全方式读取，不进入命令/日志。<br>2) 使用 T10 的专用样例清单及只读 SQL 预检记录，确认目标存在、可访问、该学生在该卷无成功 attempt；API-2 冻结，不新增读取接口做预检。若首提交返回 E08，记录样例已消耗的前置阻塞，不靠改键绕过。<br>3) 正常提交产生成功记录；同键重试回放、不同键第二次应 E08；校验响应、无受保护字段、管理员 403、未认证 401。<br>4) 可选 `--check-visibility` 时必须同时提供另一张专用未作答卷 `--visibility-paper-id`（或独立学生+卷清单）；保存原可见状态，在 try/finally 内取消可见，以**新键**提交验证准入拒绝和旧键永久拒绝，再按原状态恢复。恢复后同键按已持久化标记拒绝；满足首次提交条件的新键可提交。不得以主流程成功键测试下线，否则会被成功回放短路。<br>5) finally 恢复失败时保留失败状态、资源 ID 和安全操作摘要，退出码 1；不输出口令、答案、完整键等；不删除已产生的 attempt 或拒绝标记。<br>6) 每项 `_check` 输出实际请求摘要、结果和退出码；SQL 行数核验由 T10 只读执行；记录已使用样例，重跑须换独立样例或按已明确的数据重建流程准备。 |
| 交付物 | 脚本、参数与写入影响说明、专用样例输入格式、状态恢复/中断处理说明、退出码定义；首次真实输出由 T10 执行后回填。 |
| 可复现验收标准 | **T09-A1** 缺目标参数/服务/样例时退出码 2，明确数据前置、不误报 PASS；不得自动挑共享卷。<br>**T09-A2** T10 用真实专用样例提交 200、响应符合契约，人工只读 SQL 确认 1 条 attempt 和 N 条 answers → PASS。<br>**T09-A3** 同键重试同一标识；不同键第二次 E08；库内不新增 → PASS。<br>**T09-A4** 管理员 403、未认证 401 → PASS。<br>**T09-A5** 连续两次使用独立学生或独立试卷，每次预检和消耗记录可追溯；样例不足则 BLOCKED，不删除生产记录或放宽限次。<br>**T09-A6** 输出逐项实际摘要及已写入资源清单，保留原键供同一次运行恢复但不打印完整键 → PASS。<br>**T09-A7** 启用可见性场景时，在专用样例取消可见后注入受控中断；finally 恢复原状态。模拟恢复本身失败时明确 FAIL、保留定位证据，不显示整体通过。此故障注入不以 Mock 替代真实服务/库。<br>**T09-A8** 说明与输出明确有写入及提交机会消耗；状态恢复不宣称已撤销永久记录 → PASS。 |
| 失败处理 | 数据/服务前置退出码 2；行为错误或恢复失败退出码 1。首次提交结果未知保留原键按 2.6.4 恢复，不直接生成新键；报告恢复失败涉及的专用资源及安全摘要，不擅自删除数据或修改共享卷。 |
| 明确不做 | 不自动选择普通/共享学生试卷；不直接 SQL 修改业务数据；不删除持久化记录；不测 API-2；不以脚本代替全部故障/并发验收。 |

### 4.10 T10 验收数据准备与真实验收执行

| 项 | 内容 |
|---|---|
| 对应需求 | P2、V-E 系列、11.9(4)、14.2；T4/T10 |
| 依赖 | T09 脚本可用（不要求 T09 已 PASS）+ 可访问试卷/账号/音频（外部） |
| 优先级/顺序 | P2 / 7 |
| 目标 | 用受控证据包导入真实、专用且可追溯的可访问试卷与音频（主流程至少一套，重复运行及可见性场景分别准备独立样例），执行端到端与只读 SQL 核验，产出可复核的验收证据；数据不具备时明确 BLOCKED。 |
| 输入与代码入口 | `backend/app/import_module2.py`（现有导入工具）；`docs/acceptance/module-2/guide.md`（导入/确认可见流程）；`backend/scripts/acceptance_attempt.py`（T09）；受控 16 表工作簿/音频（不进 Git） |
| GitHub 参考 | 无（内部数据治理任务；不适用 GitHub 参考）。**不以任何第三方仓库替代真实数据证据。** |
| 实施步骤 | 1) 按模块二验收指南导入受控样例（记录来源清单/SHA-256/批次号）；<br>2) 管理员确认可见，学生列表可见；<br>3) 记录专用试卷 ID、题数、题型分布、账号及用途（不记录密码）；只读 SQL 预检对应学生尚无成功 attempt，保存原可见状态；为两次运行和可选可见性测试分别提供独立样例，不足项标 BLOCKED；<br>4) 按明确的样例参数运行 T09，记录该流程会写入数据且消耗提交机会；可见性场景完成或中断后核查原状态恢复；<br>5) 只读 SQL 核对：attempt/answers 行数、题号覆盖 1–N、UTC 时间、标记表；<br>6) 按第 6 节模板回填每项结果、命令、证据位置、版本；<br>7) 若数据缺失：写 BLOCKED + 缺失项 + 责任人 + 下一步，不执行“造数据”。 |
| 交付物 | 导入与确认记录；脚本输出；SQL 查询结果；第 6 节回填表；证据文件清单（路径/哈希，敏感材料不进 Git）。 |
| 可复现验收标准 | **T10-A1** 至少 1 套学生可访问试卷（25 题、音频可读），来源/哈希可追溯；**记录题型分布，必须为短篇新闻 7、长对话 8、听力篇章 10**；不满足则估分相关项标 BLOCKED，不得改题型凑 7/8/10 → PASS/BLOCKED。<br>**T10-A2** V-E1：真实提交成功，库内 1 条 attempt + N 条 answers，判分与人工抽查一致 → PASS。<br>**T10-A3** V-E5a：管理员提交 403 → PASS。<br>**T10-A4** V-E4：**BLOCKED（D-14）**——V-E4 要求两条记录，与 BR-18a 限 1 次冲突，需求修订前不判 PASS；限次行为由 M-13 单独验证。<br>**T10-A5** SQL 核对：题号 1–25 无缺漏、无重复；`submitted_at` 为 UTC；标记表符合预期；人工抽查判分与 `correct_rate`、`practice_score` 精确值（全对 249/错在听力篇章 235/全错 0 至少覆盖一个）→ PASS。<br>**T10-A6** 所有结果均附命令/输出/版本；无 Mock/写死数据 → PASS。<br>**T10-A7** 专用样例清单、运行前 0 条成功记录的只读预检、运行后消耗记录和原状态恢复证据齐全；两次运行/可见性场景缺少独立数据时分别 BLOCKED，不用普通共享样例替代。 |
| 失败处理 | 数据缺失/不可导入：标 BLOCKED，写清 P2/T4 阻塞，不把测试夹具当“真实样例”。导入失败：按模块二导入工具的回滚与哈希校验流程处理，不手工改库绕过。验收环境与版本不一致：记录环境差异（P3a/P3b），必要时标 BLOCKED 而非 PASS。**T09↔T10 关系**：T10 依赖“T09 脚本可用”，不依赖“T09 验收通过”；T09 的 A2 由 T10 提供真实数据后执行，两者不构成验收循环。 |
| 明确不做 | 不提交真题/音频/账号密码；不修改题库内容来“让验收通过”；不把接口层测试冒充端到端。 |

### 4.11 本轮冻结项登记（不出任务卡）

| 编号 | 冻结项 | 需求依据 | 冻结原因 | 解冻条件 | 责任 |
|---|---|---|---|---|---|
| FZ1 | API-2 读取本人结果（AS-09–15、AS-19b、AS-20b、V-09–V-15b、V-19b、V-20b、V-E2/E3/E5b 读取部分） | 1.5、4.5 P1/P6、4.6 | 1.5 例外生效条件未满足（未书面签认/未回写）且未回写 B04.3/B05；P6 未满足 | ① 负责人书面签认 ② 回写模块二 B04.3/B05 ③ 记入需求 1.4/2.4 ④ P6 满足、T11 定 | 负责人 |
| FZ2 | API-1 逐题正误反馈 | D11=A、P1 | 防“试答反推答案”；1.5 例外生效前 | P1 三要件 + D11 拍板改为恢复逐题 | 负责人 |
| FZ3 | 结果页信息项/原型（9.2/9.3） | 9.1、P1 | 前端轮次 + P1 生效条件 | 前端轮次启动且 P1 回写 + P6 满足 | 负责人/前端 |
| FZ4 | 解析不含正文原文的自动检测（T11/V-15b） | 1.5(6)、BR-08、T11 | 属题库内容治理，非作答系统职责；阈值未定 | T11 规则确定并纳入内容检查 | 负责人 |
| FZ5 | 管理端统计/单条结果审计/历史列表/导出 | OUT6/OUT7、R1 | 明确不做 | 另开需求与接口 | 负责人 |

---

## 5 验收矩阵

> **重要**：本节是**待执行的验收计划**，不是验收结果。所有行的“实际判定”初始为空，必须由验收人按第 6 节回填；本文不预设任何 PASS。
>
> 判定状态：`PASS`（判据全部满足且证据可复核）、`PARTIAL`（主判据满足但有已登记的未覆盖项）、`FAIL`（判据不满足或红线命中）、`BLOCKED`（前置/环境/签认/数据缺失，无法判定；**BLOCKED 不等于 FAIL**）。
>
> “本轮可执行性”列：`可执行-自动`＝pytest；`可执行-脚本`＝`acceptance_attempt.py`；`可执行-人工/SQL`＝需人工或只读 SQL；`冻结`＝本轮范围外（P1/P6）；`BLOCKED-数据`＝依赖 P2/T4；`BLOCKED-状态位`＝依赖 T6 可构造性。
>
> **级别/责任角色（R7-03，拟同步需求 v0.20 §10.0）**：级别表示实际缺陷的风险及处置，不直接决定用例结果。BLOCKER 场景正确处理可 PASS，实际缺陷 FAIL，命中红线整体 FAIL；REVIEW 未确认记 BLOCKED，确认后按预期 PASS/FAIL；WARN 不豁免必需判据。默认责任：BLOCKER/WARN→开发人，REVIEW→负责人或验收人；确认记录必须真实，不能以本次文档修订代替需求负责人签认。
>
> **级别不是判定结果（REV-08）**：正确拒绝非法请求应记 **PASS**；REVIEW 在口径未确定前记 **BLOCKED**，口径确认后按已确认预期判 PASS/FAIL；WARN 不豁免任何必需校验。级别只决定“出问题时的处置/责任”，不决定“该场景天然通过”。

### 5.1 正常路径与回归（A/C/D 组）

> M-01–M-13 为提交/判分正常路径；M-14–M-20 为回归项（迁移/UTC/鉴权顺序/模块二字段与音频/模块一认证）。

| 矩阵号 | 来源 | 输入场景（可复现构造） | 预期结果 | 对应任务 | 本轮可执行性 | 判定方式 | 级别 | 责任角色 |
|---|---|---|---|---|---|---|---|---|
| M-01 | V-01 / AS-01 | 学生 A 对可访问 25 题试卷提交完整作答（`loaded_question_ids`=25、`answers`=25，**错题位于听力篇章**） | 200；`attempt_code` 非空；`question_count=25`；`correct_count=24`；`correct_rate=96`；`practice_score.available=true` 且 **`value=235`**；库内 attempt=1、answers=25；`score_breakdown` 分组为 7/8/10 | T06/T08 | 可执行-自动（精确值/库内）；人工逐题核对另记、不计入自动覆盖 | pytest + SQL；人工抽查单列 | BLOCKER | 开发人 |
| M-02 | V-02 / AS-02 | **每个子场景使用独立试卷（或独立学生）夹具**：试卷 A 提交 10 题、其余未答；试卷 B 提交 `answers=[]` | 200；分母均为 25；未作答计错；未作答与答错在逐题事实可区分（`selected_option IS NULL`）；空卷正确率=0、估分=0 或不可用按题型；不得在同卷上连续成功两次（BR-18a） | T06/T08 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-03a | V-03 / AS-03（判分/库内） | 构造选项重排题（展示 A←题库 C、B←题库 A…），学生选展示 B（正确文字） | 判对；若选展示 A（错位）判错；**库内快照** `attempt_answers.correct_option/selected_option` 均为原卷字母且与展示文本一致 | T05/T06 | 可执行-自动 | pytest + SQL | BLOCKER | 开发人 |
| M-03b | V-03 / AS-03（回显） | 读取结果并断言“回显答案与所选均为原卷字母” | 本轮无 API-2、API-1 不返回逐题字母（FZ2）→ **不可观测，BLOCKED（FZ2/FZ1）**；解冻后按 V-03 完整验 | — | **BLOCKED** | 解冻后执行 | REVIEW | 负责人 |
| M-04 | V-04 / AS-04、BR-16/16a | **每个子场景使用独立试卷（或独立学生）夹具**：24/25（错 1）、25/25、0/25；另构造题型缺失/非 25 题 | 正确率分别 96/100/0（整数）；估分精确值：全对=249、错在听力篇章的 24/25=235、全错=0；`label` 含“非官方成绩”；两者分开呈现；题型缺失/非 25 题时 `available=false`、`value=null`；不得在同卷上连续成功两次 | T05/T06 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-05 | V-06 / AS-06 | 首次提交成功后，同键同内容再发一次 | 两次同一 `attempt_code` 与结论；库内仍 1 条 attempt；answers 不重复 | T03/T06/T08 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-06 | V-07a / EX-09a | 换批发生在“加载前”：学生看到新批后按新批题目身份提交（依赖 T08 双批次夹具） | 允许提交；按提交时当前批次判分/快照；生成 1 条 attempt | T04/T06/T08 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-07 | V-12（读取部分冻结）/ AS-12 的学生侧通用 | 学生读他人/不存在 attempt | 本轮无 API-2 路由；**不定义其路径/404 业务语义**，不得探得他人数据 | — | 冻结 | — | REVIEW | 负责人 |
| M-08 | V-16 / AS-16 | 无 token / 失效 token 调 API-1，且 `exam_paper_id` 不存在 | 401（先于 404/403） | T07/T08 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-09 | V-17 / AS-17 | 管理员 token 调 API-1（试卷存在/不存在两种） | 均为 403；不得进入 404 | T07/T08 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-10 | V-18 / AS-18 | 交卷前后分别调学生详情、音频、列表 | 字段集合完全一致；均无 `correct_option/explanation_text/segments`；音频权限与 Range 响应不变；无“已交卷返回答案”分支 | T07/T08 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-11 | V-19a / AS-19a | 改变标注审核/模块三验收状态位（若可构造），再提交 | 提交准入结论不变（仍只读三条件） | T04/T08 | 可执行-自动（状态位可构造时）；否则 BLOCKED-状态位 | pytest | BLOCKER | 开发人 |
| M-12 | V-20a / AS-20a | 交卷后取消可见；只读 SQL 查 attempt/answers | 记录仍存在，不被级联删除；逐题事实完整 | T01/T06/T10 | 可执行-人工/SQL | psql 只读 | BLOCKER | 开发人 |
| M-12a | AS-14 / BR-23（提交侧快照） | 提交后**在测试库**直接改题库题干/选项/答案/解析，再只读 SQL 查 `attempt_answers` | 快照字段（S-2–S-9 中落库部分）保持提交时值；不改写、不重判；无 API-2 读取接口（读取侧随 FZ1 冻结） | T05/T08/T10 | 可执行-人工/SQL（测试库构造） | pytest + psql | BLOCKER | 开发人 |
| M-13 | V-01a / D11、BR-18a | 1.5 例外生效前：同卷不同键第二次提交 | 400 E08；不新增记录、不留永久标记；库内仍 1 条 | T06/T08 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-14 | V-R7 / BR-27 | 提交后查 `submitted_at` | 库内为 UTC；接口返回 ISO 8601 UTC；跨时区阅读不改变含义 | T01/T06/T08 | 可执行-自动 | pytest + SQL | BLOCKER | 开发人 |
| M-15 | V-R6 / BR-26 | 空库 `upgrade head` → `downgrade 0004` → `upgrade head` | 三表正确创建/删除/重建；单 head；`0001–0004` 未改；模块一 4 表未动 | T01/T08 | 可执行-人工/脚本 | Alembic 命令 | BLOCKER | 开发人 |
| M-16 | V-R1 / BR-11 | 无 token + 不存在资源；admin + 不存在资源；student + 不可见 | 401→403→404 顺序；不得先 404 | T07/T08 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-17 | V-R2 / BR-04/06 | 交卷前后学生详情与音频；学生列表 | 详情/音频无答案、解析、正文；列表只含可访问；交卷前后一致 | T07/T08 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-18 | V-R3 | 音频 `Range: bytes=0-1023`、完整请求、越界 Range | 206/200/416 与既有行为一致 | T07/T08 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-19 | V-R4 | 管理员 3 接口（配套/可见性/检查） | 语义与字段不变；学生调用仍 403 | T07/T08 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-20 | V-R5 | 模块一认证既有用例 | 全部通过；登录/退出/当前用户/角色未破坏 | T07/T08 | 可执行-自动 | pytest | BLOCKER | 开发人 |

### 5.2 异常与边界

| 矩阵号 | 来源 | 输入场景 | 预期结果 | 对应任务 | 本轮可执行性 | 判定方式 | 级别 | 责任角色 |
|---|---|---|---|---|---|---|---|---|
| M-21 | V-07 / AS-07 | 加载后取消可见，再提交 | 404 E03（按不存在）；不产生 attempt；写 1 条 `paper_not_accessible` 标记；同键重试同一 404；恢复后旧键仍 404，新键可成功 | T03/T04/T06 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-21a | AS-07、E03 | 学生用合法键/可解析体提交到**不存在的 `exam_paper_id`** | 404 E03 + 1 条 `paper_not_accessible` 标记（标记表无试卷外键，见 2.3.4）；不产生 attempt；同键重试同一 404 | T03/T04/T06 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-22 | V-07b / EX-09b、S8c | 加载后换批且新批可访问：用旧批题目身份提交（依赖 T08 双批次夹具） | 400 E04“内容已更新，请重新作答”；**不是 404**；不落库；写 1 条 `content_version_mismatch` 标记；旧键永不复用 | T04/T06/T08 | 可执行-自动 | pytest | REVIEW | 负责人 |
| M-23 | V-08 / AS-08 | 提交前故障、COMMIT 未知的已提交/未提交两支、已提交响应丢失；未提交后增加试卷状态变化 | 提交前无本次记录/半成品；查到持久化成功/标记才回放，两表均无记录按当前状态重新校验，可成功或拒绝；读取失败仍 500；同键至多一条成功 | T06/T08 | 可执行-自动（真实库受控故障注入） | pytest + SQL；日志另由 M-23a 验证 | BLOCKER | 开发人 |
| M-23a | R7-05 / 2.7.3 | 执行/提交/rollback/重读错误包含虚构敏感参数及驱动 DETAIL，捕获服务层和全局最终日志 | 日志及异常链无所选/正确答案、解析、正文、完整键等测试标记；安全定位信息存在；500 仍使用既有外壳 | T06/T07/T08 | 可执行-自动（故障注入、日志捕获） | pytest 日志捕获 + HTTP 外壳断言 | BLOCKER | 开发人 |
| M-24 | EX-16 / AS-01 | `selected_option="E"` 或 `"a"`；`question_id` 非法格式 | 422（schema）；不落库、不留标记；修正后可同键重试 | T02/T06/T08 | 可执行-自动 | pytest | WARN | 开发人 |
| M-25 | EX-17 / 5.5a | **可访问**试卷：他卷题目身份、不存在题号、重复题号 | 400 E07；不落库、不留标记；换正确试卷后用新键可提交 | T04/T06/T08 | 可执行-自动 | pytest | WARN | 开发人 |
| M-26 | EX-18 | `answers` 字段整体缺失 | 422；不得当作空卷返回成功 | T02/T06/T08 | 可执行-自动 | pytest | WARN | 开发人 |
| M-27 | EX-19 | 同一 `question_id` 出现两次（多字母） | 400；不落库 | T04/T06/T08 | 可执行-自动 | pytest | WARN | 开发人 |
| M-28 | EX-20 / D-02 | 缺失 `Idempotency-Key`；非 UUIDv4/超长 | 400 E05；不进入业务、不落库、不留标记 | T02/T06/T08 | 可执行-自动 | pytest | WARN | 开发人 |
| M-29 | EX-12a | 提交时内容检查未通过（试卷不可访问） | 404（复用准入）；无 attempt | T04/T06/T08 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-29a | EX-28 / BR-01 | 可访问试卷但题目/映射数据不一致（构造：绕过内容检查直接改映射为非排列） | 404 E14，**不写永久标记**（D-20 建议口径）；不判分、不写 attempt；修复后同键可重试；记录数据异常 | T04/T06 | 可执行-自动 | pytest | REVIEW | 验收人 |
| M-29b | EX-28 / BR-01 | 确认可见后删除/移走音频文件，再提交 | 提交时音频完整性检查失败 → 404 E14，**不写永久标记**（D-20 建议口径）；不写 attempt；修复后同键可重试 | T04/T06 | 可执行-自动（测试库受控目录） | pytest | REVIEW | 验收人 |
| M-29c | EX-28 / REV-03 | 原卷应有 25 题，删除第 25 题及其映射，但历史内容检查仍为通过 | `check_paper_integrity` 按 `expected_question_count` 判定题量/题号覆盖不完整 → 404 E14，**不写永久标记**、无 attempt；**不得按剩余 24 题判分** | T04/T06 | 可执行-自动 | pytest | REVIEW | 验收人 |
| M-30 | EX-13a / AS-19a | 标注审核状态变化 | 不影响提交准入 | T04 | 可执行-自动（可构造时） | pytest | REVIEW | 负责人 |
| M-31 | V-22 / EX-24 | 同键并发（两线程 Barrier 同时提交） | **两个请求最终均返回 200 且同一 `attempt_code`**；库内 1 条 attempt；不得 2 条成功，也不以“明确失败”放宽；锁超时/断库等故障场景另测 | T03/T06/T08 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-32 | V-21 / EX-23 | 不同键并发（两线程、同学生同试卷） | **口径冲突未决**：需求 11.4/10.4 写“两条独立记录”，BR-18a（1.5 例外生效前）要求同卷限 1 次。**本轮状态 BLOCKED（D-14）**；若负责人先修订需求（加“P1 生效后”限定或删除 V-21）再按修订口径执行；不得在未修订时按默认口径判 PASS/PARTIAL | T06/T08 | **BLOCKED（D-14）** | 暂不执行 | REVIEW | 负责人 |
| M-33 | V-23 / EX-25 | 提交与取消可见并发，两种顺序分别构造（需测试注入钩子固定时序） | 提交先/处理时仍可访问 → 成功落库；下线先/处理前已不可访问 → 404 拒绝且无 attempt | T04/T06/T08 | 可执行-自动（有钩子时）；无钩子则 BLOCKED-并发 | pytest 钩子 + SQL | BLOCKER | 开发人 |
| M-34 | EX-26 / AS-08 | **成功写入路径的提交前故障**，原键重试前题目/准入状态保持有效且无他键成功 | 本次故障不创建拒绝标记；重试可成功且仅一条；COMMIT 未知/状态变化另由 M-23 按持久化状态验证，不泛化本行预期 | T06/T08 | 可执行-自动 | pytest + SQL | WARN | 开发人 |
| M-35 | V-05 / AS-05 | P1 生效后：不同键两次提交 | 2 条独立 attempt，互不覆盖 | — | **冻结（P1）** | 解冻后 P1 轮次 | REVIEW | 负责人 |
| M-36 | E09 / BR-19b | 同键换内容/试卷（拆两种）：① 已成功提交 A，同键改 A 的答案；② 已成功提交 A，同键提交 B | ① 400 E09、不落库、无标记；改用新键提交 A → **400 E08，成功记录仍 1 条**。② 400 E09；改用新键提交可访问且尚未成功作答的 B → 200 → PASS | T03/T06/T08 | 可执行-自动 | pytest | BLOCKER | 开发人 |
| M-37 | 5.5a | **可访问**试卷：`loaded_question_ids` 为当前批次真子集 | 400 E07（整卷集合不完整）；不判分、不落库 | T04/T06/T08 | 可执行-自动 | pytest | WARN | 开发人 |
| M-38 | 5.5a | 同一 `loaded_question_ids` 但顺序打乱 | 允许（集合语义） | T04/T06/T08 | 可执行-自动 | pytest | WARN | 开发人 |

### 5.3 端到端（真实服务 + 真实库/样例）

| 矩阵号 | 来源 | 输入场景 | 预期结果 | 对应任务 | 本轮可执行性 | 判定方式 | 级别 | 责任角色 |
|---|---|---|---|---|---|---|---|---|
| M-39 | V-E1 | 受控导入 1 套真实可访问试卷与音频；学生完成 25 题提交 | 真实 DB 中 attempt=1、answers=25；判分与人工抽查一致；响应字段符合 2.4.2 | T09/T10 | BLOCKED-数据（P2 未满足时为 BLOCKED） | `acceptance_attempt.py` + SQL | BLOCKER | 开发人 |
| M-40 | V-E5a | 管理员真实提交 | 403 | T09/T10 | BLOCKED-数据（无数据时为 BLOCKED） | 脚本 | BLOCKER | 开发人 |
| M-41 | V-E4 | 同卷再次作答；1.5 例外生效前 | **BLOCKED（D-14）**：不同键第二次在 BR-18a 下应为限次拒绝，但需求 V-E4 写“两条记录”，口径未决；P1 生效后才要求两条记录 | T09/T10 | **BLOCKED（D-14）** | 需求修订后执行 | REVIEW | 负责人 |
| M-42 | V-E2 / V-E3 / V-E5b | 交卷后读结果、取消可见后读、管理员读结果 | — | — | **冻结（P1/P6）** | 解冻后 R 组 | REVIEW | 负责人 |

### 5.4 本轮冻结/BLOCKED 与不可豁免规则（必须显式列出）

> 本表是 5.1–5.3 中冻结/BLOCKED 行的**汇总索引**（M-47a/M-47b 为 M-32/M-41 的口径冲突拆分），便于一次点清，不重复计入 6.4 的 **49 行**统计；回填时按 5.1–5.3 的矩阵号对应填写，不因本表重复计数。
>
> 冻结项在验收回填时一律记 **BLOCKED** 并注明冻结原因/解冻条件；不得记 PASS，也不得用“书面接受 BLOCKED”替代红线、鉴权、准入、快照、不删除等不可豁免项（5.5）。

| 矩阵号 | 来源 | 场景 | 本轮状态 | 原因 | 解冻/责任 |
|---|---|---|---|---|---|
| M-07 | V-12（读取部分）/ AS-12 | 学生读他人/不存在 attempt（API-2） | **BLOCKED（P1）** | 无 API-2 路由；本文不定义其路径/404 语义 | 负责人（FZ1） |
| M-42 | V-E2 / V-E3 / V-E5b | 交卷后读结果、取消可见后读、管理员读结果 | **BLOCKED（P1/P6）** | 读取接口冻结 | 负责人（FZ1） |
| M-43 | V-09–V-11、V-12（读取侧）、V-13、V-14、V-15a | 结果读取、快照漂移、管理员读结果、空解析读取 | **BLOCKED（P1/P6）** | 1.5 例外生效条件未满足（未回写/未签认）；P6 未满足 | 负责人（FZ1） |
| M-47a | M-32 / V-21 / EX-23 | 不同键并发的“两条独立记录” | **BLOCKED（D-14 需求冲突）** | V-21/EX-23 与 BR-18a 字面冲突，未修订前不可判定 | 负责人（D-14） |
| M-47b | M-41 / V-E4（多条部分） | 同卷再次作答产生两条记录 | **BLOCKED（D-14）** | 同上 | 负责人（D-14） |
| M-44 | V-15b / BR-08 / T11 | 解析逐句/连续片段与正文比对 | **BLOCKED（T11 未定）** | 检测规则未定，且属题库内容治理 | 负责人（FZ4） |
| M-45 | V-19b | 标注审核变化不影响读取 | **BLOCKED（P1）** | 依赖 API-2 | 负责人（FZ1） |
| M-46 | V-20b | 下线期间读结果 404 | **BLOCKED（P1）** | 依赖 API-2 | 负责人（FZ1） |
| M-47 | V-05（完整口径）/ V-E4 多条部分 | P1 生效后的多次作答 | **冻结（P1）→ 验收记 BLOCKED** | BR-18a 当前限 1 次；D-14 冲突未决 | 负责人（D11/D-14） |
| M-48 | EX-27、EX-29–EX-32 | 空解析读取、快照不漂移读取、换批后读取、外部删除、快照字段缺失 | **BLOCKED（P1/读取接口）** | 读取接口冻结；提交侧快照由 M-12a 单独验证 | 负责人（FZ1） |
| 规则 | 5.5 红线 | 红线出现即整体 FAIL；不得以书面接受 BLOCKED 替代 | **不可豁免** | 需求 11.1 不可豁免项 | 验收人 |

### 5.5 红线检查（任一出现即整体 FAIL）

| 编号 | 红线 | 检查方式 | 首责任务 |
|---|---|---|---|
| RED-1 | 除 API-2（本轮不存在）外，任何时点学生接口出现答案、解析、听力正文 | 响应全文断言 + 字段集合断言 | T06/T07 |
| RED-2 | 既有学生接口新增“已交卷则返回答案”分支 | 交卷前后对比 + 代码审查 | T07 |
| RED-3 | 判分跨字母空间比较，或回显字母与展示选项不一致 | 判分/库内：M-03a；**回显**：M-03b BLOCKED（FZ2/FZ1），需负责人书面裁定是否以库内快照代理 | T05 |
| RED-4 | 管理员可提交作答或读取学生结果 | 403 用例 | T07 |
| RED-5 | 未认证请求返回 404/403 | 401 优先用例 | T07 |
| RED-6 | 半成品记录、重复成功记录、删除既有作答记录 | 失败注入/并发/SQL 用例 | T01/T06 |
| RED-7 | 修改模块二既有接口语义、既有迁移或模块一表结构 | diff + 回归测试 | T01/T07 |

#### 5.5a 明确禁止的处理方式（需求 v0.20 §11.7a，出现即整体 FAIL）

| 编号 | 禁止做法 | 检查方式 | 与 5.5 的关系 |
|---|---|---|---|
| RED-8 | 以“前端隐藏”代替服务端剔除答案、解析、正文 | 响应字段/全文断言 + 代码审查 | 与 RED-1/2 重叠，按更严记 |
| RED-9 | 以 Mock、写死响应、内存数据或跳过测试代替真实依赖验证并据此判 PASS | 检查测试/验收是否真实连 DB、真实样例；Mock 仅限故障注入 | **新增**（需求 11.7a-2） |
| RED-10 | 修改模块二 6 个既有接口语义或既有迁移来“适配”本功能 | diff + 既有用例回归 | 与 RED-7 重叠 |
| RED-11 | 对无法判定的内容用默认值、占位值或“待审”字样填充，而不记录状态 | 响应/库内检查空值与占位文案（如“暂无解析”“待审”） | **新增**（需求 11.7a-4） |
| RED-12 | 在 P1 回写与 P6 未满足前先行开发结果读取能力（A/C/D 组内含判分与 249 估分不受限） | 路由/代码审查：无 API-2 实现；FZ1 冻结对照 | **新增**（需求 11.7a-5） |
| RED-13 | 删除或弱化测试、红线与校验规则来换取“通过” | 测试数/用例 diff、断言完整性审查 | **新增**（需求 11.7a-6） |

> 说明：RED-8/RED-10 与既有红线重叠；RED-9、RED-11、RED-12、RED-13 为 v0.20 新增禁止项。任何一项出现，整体 FAIL，不得以“已接受风险”替代。

---

## 6 验收回填模板

> 本节是**模板**，初始不含任何实际结果。验收人按矩阵逐项执行后填写；未执行项保持“未执行”，不得用默认 PASS 填充。
>
> 证据原则（需求 11.1）：真实依赖运行证据（真实 DB、音频、可见试卷）；Mock、写死、仅 200、仅 pytest 全绿、仅文件存在均不构成 PASS。环境不明标 BLOCKED。

### 6.1 版本与环境（每次回填必填）

| 项 | 填写内容 |
|---|---|
| 文档版本 | `development.md` **v0.12**（或实际被测版本；不得回填旧版 v0.11/v0.10.1/v0.10） |
| 需求基线 | **v0.19（负责人确认，书面件待补）** + **v0.20 编修性补充（待负责人确认）** |
| 代码提交 | `<commit sha>`（被测分支，不是 `develop` 口头描述） |
| 后端 Python | `<python --version>` |
| 依赖版本 | `backend/requirements.txt` 哈希或关键版本（fastapi/SQLAlchemy/alembic/pydantic/psycopg） |
| PostgreSQL | `<版本>`；开发库/测试库名（不写密码） |
| 操作系统 | `<Windows 版本>` |
| 验收时间 | `<YYYY-MM-DD HH:mm +08:00>` |
| 验收人 | `<姓名/角色>`；独立验收 A/B 分别填写 |
| 数据来源 | 受控样例名称+哈希；或“测试夹具（仅 L1/L2，不用于 V-E）” |
| 环境异常 | 断库/代理/权限/版本不一致等（有则写，无则“无”） |

### 6.2 主回填表（逐矩阵行）

| 序号 | 矩阵号 | 对应任务 | 执行命令/操作 | 实际结果 | 证据形式 | 证据位置 | 未覆盖项/备注 |
|---|---|---|---|---|---|---|---|
| 1 | M-01 | T06/T08 | `<命令>` | 未执行 / PASS / PARTIAL / FAIL / BLOCKED | 接口请求/响应样例 + 库内记录查询 | `<日志/截图/输出文件路径或 PR 链接>` | `<仅未覆盖时填>` |
| 2 | M-02 | T06/T08 |  | 未执行 | 接口请求/响应样例 + 只读 SQL |  |  |
| … | … | … |  |  |  |  |  |
| N |  |  |  | 未执行 |  |  |  |

**证据形式与 O1–O4 对应（需求 v0.20 §3.1）**：

| 业务目标 | 证据形式 | 适用矩阵行（示例） |
|---|---|---|
| O1 作答闭环 | 接口请求/响应样例 + 库内记录查询 | M-01、M-02、M-13、M-39 |
| O2 服务端唯一权威 | 判分结果与人工核对记录 | M-03a、M-04、M-05、T05 自测 |
| O3 逐题事实 | 只读 SQL 结果 | M-12、M-12a、M-21、M-22 |
| O4 权限边界 | 交卷前后接口响应对比；最终日志脱敏捕获 | M-10、M-17、M-23a、RED-1/RED-2 |

> 回填时“证据形式”按对应 O 目标填写；一个矩阵行若同时验证多个目标，可并列填写（如“接口样例 + 只读 SQL”）。

填写规则：

0. **模板按矩阵行数扩展**：5.1–5.3 共 **49 个矩阵编号**（包括 M-23a 日志项及既有子项）；每行一条，不得只填示例两行；5.4 的冻结/BLOCKED 行保留状态与原因，5.5 红线按 6.2b 单独回填；冻结行也不得删除。
1. **实际结果只允许** `PASS / PARTIAL / FAIL / BLOCKED`（或“未执行”）；不得写“基本通过”“看起来正常”。
2. `PARTIAL` 必须写清“哪条判据未满足、为什么不影响主判据、谁接受”；`BLOCKED` 必须写“缺什么、责任角色、下一动作”。
3. 证据位置写**可复核路径/URL**：命令输出保存为文本文件、SQL 结果保存为 `.txt`、响应保存为 `.json`；不要只写“已测试”。
4. 红线项（5.5）单独列一行或附在对应矩阵行，命中即整体 FAIL，不允许 PARTIAL。

### 6.2b 红线回填表（逐条）

| 红线 | 检查方式/命令 | 实际结果（PASS/FAIL） | 证据位置 | 备注 |
|---|---|---|---|---|
| RED-1 学生接口泄露答案/解析/正文 | 响应全文字段断言 + 字段集合 | 未执行 |  |  |
| RED-2 既有学生接口新增“交卷返回答案”分支 | 交卷前后对比 + 代码审查 | 未执行 |  |  |
| RED-3 判分跨字母空间/回显不一致 | 重排题库内快照 + 代码审查 | 未执行 |  |  |
| RED-4 管理员代答/读结果 | 403 用例 | 未执行 |  |  |
| RED-5 未认证返回 404/403 | 401 优先用例 | 未执行 |  |  |
| RED-6 半成品/重复成功/删除记录 | 失败注入/并发/SQL | 未执行 |  |  |
| RED-7 修改既有接口/迁移/模块一表 | diff + 回归 | 未执行 |  |  |
| RED-8 前端隐藏代替服务端剔除 | 响应断言 + 代码审查 | 未执行 |  |  |
| RED-9 Mock/写死/内存/跳过测试冒充真实验证 | 检查真实 DB/样例与测试实现 | 未执行 |  |  |
| RED-10 修改模块二接口/迁移“适配” | diff + 既有用例 | 未执行 |  |  |
| RED-11 占位值/“待审”填充且不记录状态 | 响应/库内空值与占位检查 | 未执行 |  |  |
| RED-12 P1/P6 未满足前开发结果读取 | 路由/代码审查 + FZ1 对照 | 未执行 |  |  |
| RED-13 删除/弱化测试、红线换通过 | 测试/断言 diff 审查 | 未执行 |  |  |

### 6.3 任务卡完成回填（每卡一份）

| 项 | 内容 |
|---|---|
| 任务卡 | `T0X` |
| PR / 分支 | `#<编号>` / `feature/...` |
| 代码提交 | `<commit sha>` |
| 完成任务 | `<卡内目标一句话>` |
| 卡内验收项结果 | `T0X-A1=PASS；T0X-A2=PARTIAL（原因…）；…` |
| 实际改动文件 | `<文件列表；与写作用域对照>` |
| 测试命令与结果 | `<命令>` → `<实际输出摘要，含通过/失败数>` |
| 证据位置 | `<PR 评论/日志/截图路径>` |
| 未覆盖项 | `<若有；无则写“无”>` |
| 失败/回退记录 | `<失败尝试、修复 commit、回退步骤；无则写“无”>` |
| 结论 | `PASS / PARTIAL / FAIL / BLOCKED`（由验收人填，不由开发人自封） |

### 6.3a 默认策略实现自测回填（R7-07，不计矩阵通过率）

| 自测项 | 依据与口径状态 | 命令/实际技术结果 | 数据库及响应证据 | 决策/验收边界 |
|---|---|---|---|---|
| T06-A14 / T08-A10 不同键同卷并发限次 | 默认 D11=A、BR-18a；D11/D-14 当前仍未确认 | 未执行；门禁解除后如实填写技术结果 | 两独立会话/同步点、200 与 E08、仅一条完整 attempt、无标记；移除锁对照记录 | 不计 49 行通过率；M-32/M-41 保持 BLOCKED，负责人确认后再映射正式验收 |

> 技术自测结果只说明默认策略实现表现；不能据此填写“需求已签认”或宣称 V-21/V-E4 已通过。

### 6.4 本轮汇总

| 统计项 | 数量/说明 |
|---|---|
| 矩阵总行数 | `49`（5.1–5.3；新增 M-23a；T06-A14 等实现自测另列 6.3a，不混入矩阵）；另 5.4 冻结/BLOCKED 汇总索引、红线 **13 项**（5.5 的 RED-1–7 + 5.5a 的 RED-8–13），单独统计、不混入通过率 |
| PASS | `<n>` |
| PARTIAL | `<n>`（逐条列编号） |
| FAIL | `<n>`（逐条列编号，命中红线则写“整体 FAIL”） |
| BLOCKED | `<n>`（逐条列编号 + 原因 + 责任角色） |
| 未执行 | `<n>`（未执行不得计入通过） |
| 不可豁免项状态 | 红线/鉴权/准入/**快照不漂移**/不删除：`<全部满足/有不满足>`（不得以书面接受 BLOCKED 替代） |
| 快照项说明 | 本轮“快照不漂移”以 **M-12a 的库内只读 SQL** 验证提交侧快照不被题库修改影响；**API-2 读取侧**因范围收缩（4.6）整体冻结，不属于“以 BLOCKED 替代通过”，须在结论中写明“读取侧未实现（FZ1）” | 
| 是否满足合并条件 | `是/否` + 依据（需求 11.1：全部非 BLOCKED 项 PASS 且无红线）。**存在 D-14 导致的 BLOCKED 时不得宣称整体通过**，须先由负责人修订需求或书面接受范围调整（不得以“默认口径”绕过） |

### 6.5 未覆盖项与后续工作

| 编号 | 未覆盖/未满足项 | 影响 | 后续动作 | 责任角色 | 目标时间 |
|---|---|---|---|---|---|
| U-01 | 例：API-2/结果读取（FZ1） | 学生只能看汇总，不能看逐题 | P1/P6 满足后另开轮次 | 负责人 | 待定 |
| U-02 | 例：T11 解析检测（FZ4） | V-15b 无法判定 | 题库内容治理排期 | 负责人 | 待定 |
| U-03 | 例：验收数据不足（P2） | V-E 系列 BLOCKED | 按 T10 导入受控样例 | 验收人 | 待定 |
| U-04 | 例：Python 版本迁移（P3b） | 验收环境与 V1.2 不一致 | 另立迁移任务 | 负责人 | 待定 |

### 6.6 签署

| 角色 | 姓名 | 日期 | 结论/意见 |
|---|---|---|---|
| 开发人（自测） |  |  |  |
| 验收人 A（独立） |  |  |  |
| 验收人 B（独立，如适用） |  |  |  |
| 负责人（合并决定） |  |  |  |

> 双人独立验收是否沿用模块二 B12、验收人数与时间由 T10（需求 §13）确定；未定前不虚构验收人。**验收人不得是同一实现的开发人**；模块二维护人负责回写 B04.3/B05，角色须真实留痕（v0.20 §3.4）。

### 6.7 回填示例（仅格式示意，禁止照抄为结果）

```text
矩阵号：M-13（V-01a）
命令：python -m pytest -v tests/test_attempt_api.py -k limit
实际输出：1 passed（耗时 2.31s；测试库 shengshengruer_test；commit abc1234）
实际结果：PASS
证据位置：PR #12 评论附件 pytest-limit-20261109.txt
备注：无
```

---

## 附录 A 需求—任务—验收追踪表

> 说明：本表用于证明“需求、任务、验收相互对应”。`本轮状态` 指本文档是否给出可执行落点：`有卡`＝第 4 节任务卡；`冻结`＝4.11；`不适用`＝需求明确不做；`持续`＝跨轮次的流程要求。
>
> **版本引用**：需求编号引用 **v0.20**（业务规则编号与 v0.19 一致，未变）；v0.20 新增的异常分级、禁止做法、证据形式、角色独立性、门禁已并入第 2/5/6 节。
>
> **证据形式**：A.1 已按 O1–O4 标注；A.2–A.6 的证据形式沿用其映射的 AS/V 行，不重复列。完整对应见 6.2“证据形式与 O1–O4”。
>
> **列语义**：A.1/A.2 的“验收”列可能同时出现矩阵号（M-xx）与任务卡自测项（T0X-AY）。验收回填以 **M-xx** 为准；T0X-AY 是开发自测/任务卡判据，不替代矩阵行，也不单独计入 6.4 的矩阵通过率。

### A.1 功能需求 AS-01–AS-20b

| 需求 | 任务 | 验收矩阵 | 本轮状态 | 证据形式 |
|---|---|---|---|---|
| AS-01 提交整卷作答 | T02/T04/T05/T06 | M-01、M-24、M-25、M-37 | 有卡 | O1/O2/O3 |
| AS-02 部分作答/空卷 | T05/T06 | M-02 | 有卡 | O1/O3 |
| AS-03 不跨字母空间 | T05/T06 | M-03a（判分/库内）；M-03b（回显，BLOCKED） | 有卡（判分与库内）；**回显部分随 FZ2/API-2 冻结，V-03 记 PARTIAL** | O2/O3 |
| AS-04 计分口径固定 | T05 | M-04 | 有卡 | O2 |
| AS-05 同卷多次（P1 后） | T06（常量切换） | M-35 | 冻结（P1） | O1 |
| AS-06 提交幂等 | T03/T06 | M-05、M-31、M-34 | 有卡 | O1 |
| AS-07 提交时不可访问 | T03/T04/T06 | M-21 | 有卡 | O1 |
| AS-08 提交原子性 | T06 | M-23、M-34 | 有卡 | O1/O3 |
| AS-09 按标识读结果 | — | M-43 | 冻结（FZ1） | O1 |
| AS-10 空解析可读 | — | M-43/M-48 | 冻结（FZ1） | O1 |
| AS-11 读取时不可访问 | — | M-43 | 冻结（FZ1） | O1 |
| AS-12 非本人/不存在 | — | M-43 | 冻结（FZ1） | O1 |
| AS-13 管理员读结果 | — | M-43 | 冻结（FZ1） | O1 |
| AS-14 结果不漂移 | T01/T05（快照落库） | **M-12a（提交侧库内 SQL）**；读取侧 M-43 冻结 | 数据层有卡；**读取侧冻结（FZ1），不宣称读取侧通过** | O1/O3 |
| AS-15 不泄露受保护内容 | — | M-07/M-43（读取侧） | **冻结（FZ1）**：AS-15 属结果读取条目，提交侧不泄露由 AS-18/BR-04 与 T06-A11 覆盖，不能替代 AS-15 | O4 |
| AS-16 未认证 | T07 | M-08、M-16 | 有卡 | O4 |
| AS-17 管理员提交 | T07 | M-09 | 有卡 | O4 |
| AS-18 交卷不改变既有接口 | T07 | M-10、M-17 | 有卡 | O4 |
| AS-19a 准入只看三条件（提交） | T04 | M-11 | 有卡 | O4 |
| AS-19b 准入只看三条件（读取） | — | M-45 | 冻结（FZ1） | O4 |
| AS-20a 下线不删记录 | T01/T06 | M-12 | 有卡 | O3/O4 |
| AS-20b 下线期间读结果 404 | — | M-46 | 冻结（FZ1） | O3/O4 |

### A.2 业务规则 BR-01–BR-27（按主题映射）

| 规则 | 落点 | 验收 |
|---|---|---|
| BR-01/02 准入（提交侧） | 2.6.2；T04 | M-21、M-29、M-29a/M-29b/M-29c |
| BR-03 查询时准入（读取侧） | 2.1.2 冻结 | **冻结（FZ1）**：M-07/M-43 |
| BR-04/06/07 内容权限（提交侧） | 2.9、2.4.4；T06/T07 | M-10、M-17、RED-1/2 |
| BR-05 读取权限 | 2.1.2 冻结 | **冻结（FZ1）**：M-07/M-43 |
| BR-08 解析不得含正文 | FZ4/T11（内容治理） | M-44（BLOCKED） |
| BR-09/10/11/12 角色与错误顺序 | 2.7、T07 | M-08、M-09、M-16 |
| BR-13/14 字母空间 | 2.5.2；T05 | M-03a/M-03b、RED-3 |
| BR-15 未作答/答错 | 2.5.5；T05/T06 | M-02 |
| BR-16 正确率 | 2.5.3；T05 | M-04 |
| BR-16a 练习估分 | 2.5.4；T05 | M-04、T05-A6 |
| BR-17 分开呈现 | 2.4.2、2.5.4 | M-04；**逐题所选“返回”归 API-2/FZ1 冻结**；D11=A 仅汇总，本轮不返回逐题项 |
| BR-18/18a 多次/限次 | 2.6.3；T06 | M-13；T06-A14/T08-A10 默认限次实现自测另列 6.3a；M-32 仍 BLOCKED |
| BR-19/19a–d 幂等与顺序 | 2.6.2–2.6.4；T03/T06 | M-05、M-21、M-22、M-23、M-36 |
| BR-20 拒绝标记永久 | 2.3.4、2.6.2；T03 | M-21、M-22、M-34 |
| BR-21 原子性 | 2.6.4；T06 | M-23；日志安全另由 M-23a 验证 |
| BR-22 结果标识返回 | 2.4.2；T06 | M-01、M-05 |
| BR-23 快照不漂移 | 2.3.3、2.5；T01/T05 | 提交侧 **M-12a（库内 SQL）**；读取侧 M-43（冻结） |
| BR-24 无历史列表 | 2.4（无列表接口） | — |
| BR-25 空解析占位 | 2.5.5；T05 | T05-A5 原样快照；M-43/M-48 读取侧冻结 |
| BR-26 迁移约束 | 2.8.1；T01 | M-15、T01-A1–A5 |
| BR-27 UTC | 2.3.2/2.3.3；T01 | M-14 |

### A.3 异常场景 EX-01–EX-32

| 场景组 | 任务 | 矩阵 |
|---|---|---|
| EX-01–EX-03、EX-06 权限（提交侧） | T07 | M-08、M-09、M-16 |
| EX-04、EX-05（读结果/读他人 attempt） | — | **冻结（FZ1）**：M-07/M-43 |
| EX-07–EX-09b 状态/换批 | T03/T04/T06 | M-21、M-22、M-06 |
| EX-10–EX-13b 读取/标注 | 提交侧 T04；读取侧冻结 | M-11、M-29（EX-12a）、M-30、M-43/M-45 |
| EX-14–EX-20 输入 | T02/T04/T06 | M-02、M-24–M-28、M-37、M-38 |
| EX-21–EX-26 并发与重试 | T03/T06/T08 | M-05、M-23、M-31–M-34；T06-A14 为另列实现自测，不替代 M-32 |
| EX-28 映射/题目/音频异常 | T04/T06 | M-29a、M-29b、M-29c（404 E14，不写永久标记，D-20 建议） |
| EX-27、EX-29–EX-32 数据/读取 | 快照 T01/T05；读取冻结 | M-12a（提交侧快照）、M-43/M-48（读取侧冻结） |
| EX-23 不同键并发（口径冲突） | T06/T08 | M-32（D-14，仍 BLOCKED）；当前默认限次另记 T06-A14/6.3a |

### A.4 验收用例 V-01–V-23、V-R、V-E

| 验收项 | 任务 | 矩阵 | 备注 | 证据形式 |
|---|---|---|---|---|
| V-01、V-01a | T06 | M-01、M-13 | V-01 的“逐题正误按 D11”本轮仅落库不返回 | O1/O2/O3 |
| V-02–V-04 | T05/T06 | M-02–M-04、M-03a/M-03b | V-03 回显部分 BLOCKED，整体记 PARTIAL | O1/O2/O3 |
| V-05 | T06 | M-35 | 冻结（P1） | O1 |
| V-06–V-08 | T03/T06 | M-05、M-06、M-21、M-22、M-23 | V-07a/V-07b 分别对应换批前后 | O1/O3 |
| V-09–V-15b | — | M-43/M-44 | 冻结（FZ1/FZ4） | O1/O4 |
| V-16–V-18 | T07 | M-08–M-10、M-16 | — | O4 |
| V-19a | T04 | M-11 | V-19b 冻结 | O4 |
| V-20a | T01/T06 | M-12 | V-20b 冻结 | O3/O4 |
| V-21 | T06/T08 | M-32 | **BLOCKED（D-14）**，不得判 PASS/PARTIAL；T06-A14 自测不替代该判定 | O1 |
| V-22 | T03/T06 | M-31 | — | O1 |
| V-23 | T04/T06/T10 | M-33 | 时序证据需真实并发 | O1/O3 |
| V-R1–V-R5 | T07/T08 | M-16–M-20 | — | O4/O1 |
| V-R6–V-R7 | T01/T08 | M-15、M-14 | — | O3/O4 |
| V-E1 | T09/T10 | M-39 | 依赖 P2 | O1/O2/O3 |
| V-E2/V-E3 | — | M-42 | 冻结 | O1/O4 |
| V-E4 | T09/T10 | M-41 | **BLOCKED（D-14）**；限次行为另由 M-13 验证 | O1 |
| V-E5a/V-E5b | T09/T10 / — | M-40 / M-42 | E5b 冻结 | O4 |

### A.5 决策/待确认项的落点

| 项 | 本文落点 | 是否影响本轮实施 |
|---|---|---|
| D1–D9、R1–R4 | 1.2、2.4–2.7 | 是（已按 v0.19 确认口径，**书面件待补**；v0.20 约束待确认） |
| D4（249 估分） | 2.5.4、T05 | 是 |
| D10（禁止引用正文） | 1.5(6)、FZ4、T11 | 否（内容治理） |
| D11（仅汇总 + 限 1 次） | 2.4.2、2.6.3、T06；**仍待拍板** | 是（草稿口径） |
| U1–U7 | 1.6；U7→D-02、U6→FZ5、U4/U5→FZ3 | 部分 |
| T1–T11 | 1.6；T2→D-06、T3→D-10、T4→D-11、T7→D-02、T11→FZ4 | 部分 |
| 本文新增 D-01–D-21 | 1.6 + 5.2（D-14） | 是（默认口径可回退） |

### A.6 数据约束 DC-1–DC-9 追踪

| 约束 | 任务/落点 | 验收 |
|---|---|---|
| DC-1 一次成功一条 attempt | T01（表/唯一键）、T06（单次写入） | M-01；T06-A1 |
| DC-2 逐题条数=题目总数 | T01（应用+测试保障，无延迟约束）、T06（同一事务写入） | T06-A1；`SELECT count(*)` 断言 |
| DC-3 同学生+键至多一条成功且拒绝后不得成功 | T03（键锁/唯一键/标记短路）、T06 | M-05、M-21、M-31；**跨表互斥仅应用层保障**（见 2.3.4/2.6.4），直接 SQL 写入不在保障范围 |
| DC-4 所选字母属于展示选项集合 | T02（A–D schema）、T04/T05 | M-24、M-25 |
| DC-5 结论服务端生成 | T05（纯函数）、T06（客户端输入不成为结论） | T05-A1–A8；代码审查 |
| DC-6 提交后不可修改 | T01（无 `updated_at`）、T06（无更新/删除接口） | T06-A11；代码审查 |
| DC-7 不随试卷/批次/检查删除 | T01（RESTRICT/快照自足）、T06（不级联） | M-12 |
| DC-8 不写模块二既有表 | T07（只读复用）、T06（仅新表） | M-17；代码审查 |
| DC-9 不暴露内部主键/状态 | T02/T06（响应只含 `attempt_code`/原卷题号） | T06-A11；字段集合断言 |

---

## 附录 B 代码入口索引

### B.1 既有代码（本轮只读/最小改动）

| 文件:行号 | 作用 | 本轮用途 |
|---|---|---|
| `backend/app/repositories/listening.py:34–41` | `get_current_batch` | 确定提交时批次/题号/快照来源 |
| `backend/app/repositories/listening.py:44–59` | `get_latest_check`/`get_visibility` | 被 `student_access` 复用 |
| `backend/app/repositories/listening.py:71–87` | `student_access` 三条件判定 | 提交准入（T04） |
| `backend/app/repositories/listening.py:90–101` | `list_papers` | 回归（学生列表只含可访问） |
| `backend/app/repositories/listening.py:138–153` | `_options_for` 原卷选项顺序 | **旧函数不改**；T04 新增严格包装 `paper_options_for` 供判分/快照 |
| `backend/app/repositories/listening.py:156–172` | `_paper_correct_option` 答案换算 | **旧函数不改**；T04 新增严格包装 `paper_letter_for`，失败抛 `PaperUnavailable` |
| `backend/app/repositories/listening.py:175–217` | `assemble_student_detail` | 回归基线；不新增字段 |
| `backend/app/api/listening_papers.py:42,52,65` | 学生列表/详情/音频 | 回归（M-10/M-17/M-18） |
| `backend/app/api/admin_listening_papers.py:36,50,88` | 管理员 3 接口 | 回归（M-19） |
| `backend/app/api/deps.py:67–96` | `get_current_user` | API-1 鉴权（401） |
| `backend/app/api/deps.py:99–106` | `require_admin` | 校区分角色模式参考 |
| `backend/app/core/errors.py:8–48` | `AppError/not_found/bad_request/ok` | 错误映射（T02/T06） |
| `backend/app/main.py:33–70` | 四类异常处理器 | 422/500 统一外壳 |
| `backend/app/main.py:73–76` | router 挂载 | 新增 attempts router |
| `backend/app/db/base.py:10–49` | 命名约定/engine/session/get_db | 复用；不改 |
| `backend/app/db/models_listening.py:261–343` | Question/Presentation | 只读整卷/映射 |
| `backend/alembic/env.py:9–11` | 模型注册 | 追加 `models_attempt` |
| `backend/alembic/versions/0004_expected_count_source.py:15–16` | 当前 head | 新迁移父节点 |
| `backend/tests/conftest.py:53–127` | 测试库/迁移/种子/登录 | 新测试复用 |
| `backend/scripts/acceptance_module2.py` | 端到端脚本风格 | 新脚本模板 |
| `docs/development/module-2/api.md:76` | 管理员可调学生视角详情 | 保留既有语义 |

### B.2 新增文件（目标设计，未实现）

| 文件 | 作用 | 任务 | 状态 |
|---|---|---|---|
| `backend/app/db/models_attempt.py` | 3 张表 ORM | T01 | 待实现 |
| `backend/alembic/versions/0005_attempt_system.py` | 迁移 | T01 | 待实现 |
| `backend/app/schemas_attempts.py` | 请求/响应模型 | T02 | 待实现 |
| `backend/app/repositories/attempt_keys.py` | 幂等/标记/限次/两把锁 | T03/T06 | 待实现 |
| `backend/app/repositories/attempt_content.py` | 整卷读取/严格映射/身份分类/答案校验 | T04 | 待实现 |
| `backend/app/services/grading.py` | 判分/快照/估分纯函数 | T05 | 待实现 |
| `backend/app/services/attempts.py` | 提交编排、未知提交恢复及异常安全记录/转换 | T06 | 待实现 |
| `backend/app/api/attempts.py` | API-1 路由 | T06 | 待实现 |
| `backend/tests/test_attempt_grading.py` | 纯函数测试 | T05/T08 | 待实现 |
| `backend/tests/test_attempt_api.py` | API/集成测试 | T06/T08 | 待实现 |
| `backend/tests/test_attempt_regression.py` | 权限/回归 | T07/T08 | 待实现 |
| `backend/scripts/acceptance_attempt.py` | 端到端脚本 | T09 | 待实现 |

---

## 附录 C 调研证据与复核命令

### C.1 证据来源

- 代码基线：`D:\ShengShengRuEr\ShengShengRuEr` @ `b965a0f3771c9f6212be29b65fda326ce0307b11`（2026-11-04 提交，2026-11-08 实读）。本轮取证底稿保存在工作区临时目录（**不入版本控制**）；关键结论、版本与链接已内联到 2.11，复核命令见 C.3。
- 技术调研：PyPI 项目页/PyPI JSON、SQLAlchemy 2.0/2.1 文档、Alembic 文档、IETF Datatracker、docs.python.org、postgresql.org；**GitHub 页面在本环境不可直接访问**，仓库链接只作核对入口。
- 版本数据截止：2026-11-08。本仓库实际版本以 `backend/requirements.txt` 为准，调研版本不构成升级要求。

### C.2 关键链接（与 2.11 对应）

| 参考 | 链接 |
|---|---|
| FastAPI 仓库/文档 | https://github.com/fastapi/fastapi ；https://fastapi.tiangolo.com/tutorial/dependencies/ |
| SQLAlchemy 仓库/事务文档 | https://github.com/sqlalchemy/sqlalchemy ；https://docs.sqlalchemy.org/en/21/orm/session_transaction.html |
| Alembic 仓库/分支文档 | https://github.com/sqlalchemy/alembic ；https://alembic.sqlalchemy.org/en/latest/branches.html |
| Pydantic 仓库/文档 | https://github.com/pydantic/pydantic ；https://docs.pydantic.dev/latest/concepts/models/ |
| PostgreSQL 许可证/文档 | https://www.postgresql.org/about/licence/ ；https://www.postgresql.org/docs/current/indexes-partial.html |
| IETF Idempotency-Key draft-08 | https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/08/ |
| IETF 仓库 | https://github.com/ietf-wg-httpapi/idempotency |
| CPython decimal | https://docs.python.org/3/library/decimal.html |
| pytest / httpx | https://github.com/pytest-dev/pytest ；https://github.com/encode/httpx |

### C.3 复核命令（只读/可重复）

```powershell
# 代码基线
git -C D:\ShengShengRuEr\ShengShengRuEr log -1 --format='%H %ci'

# 关键入口
Select-String -Path D:\ShengShengRuEr\ShengShengRuEr\backend\app\repositories\listening.py `
  -Pattern '^def (student_access|assemble_student_detail|_options_for|_paper_correct_option)'
Select-String -Path D:\ShengShengRuEr\ShengShengRuEr\backend\alembic\versions\*.py `
  -Pattern '^(revision|down_revision)'

# 迁移 head（在 backend 目录、配置好 .env 后）
python -m alembic heads
python -m alembic history

# AGENTS.md 检索
Get-ChildItem -Path D:\guochuangxiangmu,D:\ShengShengRuEr\ShengShengRuEr -Recurse -File -Filter AGENTS.md
```

---

## 附录 D 本文自查清单（文档质量，不替代验收）

| # | 检查项 | 自查结论 | 说明 |
|---|---|---|---|
| 1 | 需求基线、签认状态、P1/P6 前提是否写清 | 通过 | 1.1–1.2、2.8.4 |
| 2 | 当前实现与目标设计是否分离 | 通过 | 1.4（代码已核对）vs 2.2/2.3/附录 B.2（待实现） |
| 3 | 每条 AS/BR/V/EX 是否有任务或冻结落点 | 通过（见附录 A） | 冻结项在 4.11/5.4 显式列出 |
| 4 | 任务卡是否都有目标/入口/参考/步骤/交付物/可复现验收/失败处理 | 通过 | T01–T10 七项齐全 |
| 5 | 是否编造 GitHub 调研或测试结果 | 通过 | GitHub 未抓取已声明；测试结果未预填；版本仅 PyPI/官方页证据 |
| 6 | 是否使用 PASS/PARTIAL/FAIL/BLOCKED | 通过 | 矩阵与模板均限定四态；初始“未执行” |
| 7 | 是否遵守 AGENTS.md | 通过（已检索，无项目级规则） | 0.4 检索记录；不虚构规则 |
| 8 | 是否包含需求—任务—验收映射 | 通过 | 附录 A；每卡“对应需求/矩阵” |
| 9 | 是否写明异常处理与兼容回退 | 通过 | 2.7、2.8 |
| 10 | 是否区分“可执行”与“BLOCKED/冻结” | 通过 | 5.4、6.4、4.11 |
| 11 | 是否明确本轮只写文档、不实施 | 通过 | 页首、0.1、6 节 |
| 12 | 是否存在未登记的口径冲突 | 已登记 D-01–D-21 | D-13（空卷表述）、D-14（V-21 与 BR-18a）、D-15（准入优先）、D-16（身份分类优先级）、D-19（取整边界）、D-20（EX-28 标记）、D-21（401 优先框架限制）需负责人确认 |

---

## 附录 E v0.2–v0.10.1 对外部审查意见与决策的处理记录

> 说明：本表只记录“文档层”如何处理 2026-11-08 外部审查（结论 PARTIAL）的 Q-01–Q-18；**不代表运行时验证通过**。涉及需求/负责人拍板的事项列“待拍板”，不得当作已闭环。

| 审查项 | 处理方式 | 落点 | 状态 |
|---|---|---|---|
| Q-01 冻结 API-2 被具体设计 | 删除 path/字段/错误分支草案；只保留冻结与解冻条件 | 2.1.2、2.4.3、2.4.5、2.8.2 | 已处理 |
| Q-02 混合身份优先级冲突 | 改为“任一旧批次→E04+标记”优先，并登记 D-16 | 1.6 D-16、2.6.2 6c、2.7.2、T04-A8 | 已处理（D-16 仍待负责人确认） |
| Q-03 M-02/M-04 同卷多次违反 BR-18a | 增加“独立试卷/学生夹具”约束，禁止同卷连续成功 | 5.1 M-02/M-04、T06-A2、T08 | 已处理 |
| Q-04 T02 验收依赖路由/HTTP | T02 改为模型级验收；路由/Header/422 移交 T06 | 4.2 T02、4.6 T06-A12 | 已处理 |
| Q-05 T04 验收依赖 404/标记 | T04 改为仓储级判定；HTTP/标记移交 T06-A13 | 4.4 T04、T06-A13 | 已处理 |
| Q-06 AS-15/BR-05/BR-03、AS-14 追踪错配 | AS-15/BR-05/BR-03 标冻结（FZ1）；AS-14 只保留数据层快照 | 附录 A.1/A.2、5.4 | 已处理 |
| Q-07 V-03 回显不可验 | 拆 M-03a（判分/库内）/M-03b（回显，BLOCKED）；V-03 记 PARTIAL；RED-3 明示代理边界 | 5.1 M-03a/b、A.1/A.2/A.4、5.5 | 已处理 |
| Q-08 DC-1–DC-9 无追踪 | 新增 A.6 数据约束追踪表 | 附录 A.6 | 已处理 |
| Q-09 EX-28 音频不可用无落点 | 增加提交时音频/数据完整性检查（T04 1b），补 M-29b、T06-A13；**数据异常是否写标记仍待 D-20 拍板** | 2.6.2 6b、2.7.2、T04、5.2 | 部分处理（D-20 待拍板） |
| Q-10 估分判据过弱 | M-01 固定 235、M-04 固定 249/235/0；T10 记录 7/8/10 题型分布 | 5.1 M-01/M-04、T10-A1/A5 | 已处理 |
| Q-11 换批/时序夹具缺失 | T08 增双批次夹具与时序钩子；M-06/M-22/M-33 标注依赖 | T08 步骤 5/7、5.1/5.2 | 已处理（M-33 无钩子时 BLOCKED-并发） |
| Q-12 T09/T10 门槛循环与限次 | T09-A2 改由 T10 执行；T10 依赖“脚本可用”而非 T09 PASS；A5 用独立试卷/学生 | 4.9 T09、4.10 T10 | 已处理 |
| Q-13 BR-17 逐题所选返回 | 明确归 API-2/FZ1 冻结；D11=A 仅汇总 | 2.4.2、附录 A.2 BR-17 | 已处理（D11 仍待拍板） |
| Q-14 B.1 暗示改旧函数 | 改为“旧函数不改，T04 新增严格包装” | 附录 B.1 | 已处理 |
| Q-15 记账/编号问题 | T03/T04 拆行；G8–G10 改 L-G8–L-G10；5.4 标汇总索引；统一冻结→BLOCKED | 3.1、1.5、5.4、6.4 | 已处理 |
| Q-16 行号/表述/ P1 措辞 | 修正 `base.py` 行号与“代码检索”表述；修正 `visibility.py:41,73`、`config.py:78–81`；统一用“1.5 例外生效前/生效条件未满足” | 1.4、2.11.2、T04、全文 | 已处理 |
| Q-17 额外字段/跨表互斥/标记滥用 | 删除 `feedback_scope`；补充跨表互斥仅应用层保证、标记容量与任意 `paper_id` 风险、SQL 断言 | 2.4.2、2.3.4、2.6.4、2.9、T08-A8 | 已处理（标记滥用风险由 N-09/D-17 接受并监控） |
| Q-18 T01-A4 固定测试数 | 改为实际收集数、不预设 29/34 | 4.1 T01-A4 | 已处理 |

### E.2 复审 N-01–N-09 处理记录

| 编号 | 处理方式 | 落点 | 状态 |
|---|---|---|---|
| N-01 `check_paper_integrity` 缺 `db` | 签名改为 `(db, paper, batch, settings)`，明确通过 `db` 读取题目/映射/音频；T06 步骤 3 同步 | 4.4 T04 1b、4.6 T06 步骤 3 | 已处理 |
| N-02 无 token+非法 body 允许 422 | T06-A12 改为必须 401 优先；若框架实测 422 视为缺陷，需鉴权前置，不得接受；框架不可控时登记 D-21 请负责人裁定 | 4.6 T06-A12、2.7.3 | 已处理（框架限制时的 D-21 待定） |
| N-03 EX-28 写标记先于拍板 | 新增 D-20；**v0.5 建议改为“数据异常 404 不写永久标记”**，T06-A13/M-29a/M-29b 按建议口径；待负责人签认，否决时回改 | 1.6 D-20、T06-A13、5.2 M-29a/b | 部分处理（D-20 待签认） |
| N-04 T02-A4↔T06-A12 未闭合 | T06-A12 增加 `loaded_question_ids=[]`→400 E07 | 4.6 T06-A12 | 已处理 |
| N-05 T04 仍列 BR-03 | 删除 BR-03，只留 BR-01/02；BR-03 保持 FZ1 冻结 | 4.4 T04 对应需求、附录 A.2 | 已处理 |
| N-06 visibility/config 行号 | `visibility.py:41,73`、`config.py:78–81` | 1.4.1、4.4 T04 | 已处理 |
| N-07 A.3/A.4 漏映射 | A.3 补 M-29（EX-12a）；A.4 V-06–V-08 补 M-06/M-22 | 附录 A.3/A.4 | 已处理 |
| N-08 M-01 自动行含人工核对 | 判定方式改为“精确值/库内自动；人工核对单列、不计入自动覆盖” | 5.1 M-01 | 已处理 |
| N-09 任意 paper_id 标记滥用 | 2.9 风险表新增监控口径与可选限制方案；D-17 接受风险 | 2.9、1.6 D-17 | 已处理（风险接受，需监控） |

**仍需负责人拍板/后续轮次**：D-14（V-21/V-E4 vs BR-18a）、D-16 优先级、D11 最终口径、D10/P1/P6、BR-17 返回范围、V-03 回显是否接受库内代理、D-20（EX-28 数据异常是否等同 AS-07 的永久标记）、D-21（框架无法保证 401 优先时的裁定）、T2/T3/P2/T4。**本文不代替这些决定。**

### E.3 三次复审 L-01/L-02 处理记录

| 编号 | 处理方式 | 落点 | 状态 |
|---|---|---|---|
| L-01 音频只验 `is_file()`，未验可读 | T04 1b 增加 `os.access(path, os.R_OK)` 或显式打开/读取校验；T04-A9 明确“存在但不可读”场景 | 4.4 T04 1b/A9 | 已处理 |
| L-02 D-20 影响清单漏 2.1.1/2.7.2 | D-20 影响列补 2.1.1 第 6.2 步、2.7.2；两处标注“按 D-20 口径” | 1.6 D-20、2.1.1、2.7.2 | 已处理 |

### E.4 四次复审结论（2026-11-08，**历史记录：已被 v0.6 修订稿取代**）

> 以下为当时记录，仅用于追溯；**当前门禁与开工结论以本文头部/1.3.4/2.8.4 为准**。当时的“可先做 T01”建议已废止。

- 审查结论：**PASS（文档层，附条件）**。Q-01–Q-18、N-01–N-09、L-01/L-02 的实质问题均已关闭；未发现新增高/中危问题。
- PASS 的含义限于“本文可作为开发依据”，**不代表代码、迁移或验收已通过**；本轮仍未运行任何测试。
- 附条件/待负责人书面签认：D-14、D-16、D11、D10/P1/P6、D-20、D-21、BR-17/V-03、T2/T3/P2/T4。
- **历史建议（已废止）**：当时建议“可先做 T01”；**v0.6 修订后 T2/T3 未定 → T01–T10 一律 BLOCKED**。D-14 未修订前 M-32/M-41 保持 BLOCKED。

### E.5 v0.5 决策建议入档（均待负责人书面签认）

| 决策 | 本次入档的建议口径 | 状态 |
|---|---|---|
| D-01 | 统一用 400，不引入 409 | 建议，待签认 |
| D-02 | `Idempotency-Key` 必须是 UUIDv4 字符串 | 建议，待签认 |
| D-08 | D10=B（禁止引用正文）；D11=A（仅汇总 + 同卷 1 次） | 建议，D11 待签认 |
| D-10 | 本轮固定 Python 3.14.x，不迁移 3.13.16 | 建议，待签认 |
| D-14 | 修订需求：V-21/EX-23 加“P1 生效后”，V-E4 拆两行 | 建议，待负责人修订 |
| D-15 | 准入优先（结构→准入→数据完整性→身份/版本→限次） | 建议，待签认 |
| D-16 | 任一旧批次优先→E04+标记 | 建议，待签认 |
| D-20 | EX-28 数据异常 404 **不写永久标记**，修复后同键可重试 | 建议，待签认 |
| D-21 | 必须 401 优先，不设 422 例外 | 建议，待签认 |
| D-03/04/05/13/17/18/19 | 维持文档现有默认口径 | 已入档，待签认 |

> 本表只表示“建议已写入文档”，**不等于负责人已签认**；签认前实现仍应以负责人书面结论为准。D-14 修订需求前，V-21/V-E4 相关矩阵保持 BLOCKED。

### E.6 v0.6 按需求 v0.20 同步记录

| # | v0.20 要求 | 本文落点 |
|---|---|---|
| 1 | 矩阵增加“级别/责任角色” | 5.1–5.3 表新增两列；分组默认值见 2.7.0 |
| 2 | 异常分级 | 新增 2.7.0（BLOCKER/REVIEW/WARN + EX 分组→责任角色） |
| 3 | 11.7a 禁止做法 | 5.5a 新增 RED-8–RED-13；6.2b 增加回填行 |
| 4 | 证据形式 | 6.2 增加“证据形式”列 + O1–O4 映射 |
| 5 | 版本基线 | 文档头改为 v0.19 确认（书面件待补）+ v0.20 编修性补充（待确认） |
| 6 | 角色与独立性 | 0.2 增角色职责/独立性/真实留痕 |
| 7 | §14.2 门禁 | 1.3.4、2.8.4 写明：v0.20 未确认/门禁未正式生效，但按项目保守规则 **T2/T3 未定 → T01–T10 暂缓开工（BLOCKED）**；R 组/API-2/结果页冻结 |
| 8 | 决策表同步 | 1.6 D-06/D-10 标“v0.20 要求先定、默认值待确认”；D-07/D-08 同步签认状态 |
| 9 | 附录 A | A.1 增加“证据形式”列；版本引用更新到 v0.20 |
| 10 | 节号与签认限定 | 核对 9.2/9.3；全文“已签认”处补“书面件待补”/“待确认” |

### E.7 v0.7 对外部审查 REV-01–REV-08 的处理记录

| 编号 | 问题 | 处理 | 落点 |
|---|---|---|---|
| REV-01 | 换新键可成功与同卷限次冲突 | 拆两种情况：同卷新键→E08 仍 1 条；换试卷新键→200；T06-A4/M-36 同步 | 4.6 T06-A4、5.2 M-36 |
| REV-02 | 提交异常一概解释为未落库 | 拆分提交前失败/COMMIT 未知/已提交响应丢失；拒绝标记 commit 未知同理；故障注入覆盖三类 | 2.6.4、T06-A9、M-23 |
| REV-03 | 完整性检查未对照应有题量 | 强制以 `expected_question_count` 及来源校验题量/映射/题号；新增 M-29c/T04-A10 | 2.5.2、T04 1b/A10、M-29c |
| REV-04 | 同键并发两套标准 | 统一为两个请求均返回 200 且同一 `attempt_code`，库内 1 条；故障场景另测 | 2.6.3、T06-A10、M-31 |
| REV-05 | 估分 reason 顺序遮蔽 | 改为 `not_standard_25 → question_type_missing → unknown_type → type_count_mismatch`；补四类用例 | 2.5.4、T05-A6 |
| REV-06 | 锁键哈希未定义 | 固定 SHA-256 前 4 字节大端有符号 int32；禁用 `hash()`/`hashtext()`；classid 1/2 与获取顺序 | 2.6.2、2.6.3、T03 步骤 5 |
| REV-07 | Schema 类型不足以满足 ID 契约 | `StrictId = Annotated[int, Field(strict=True, gt=0, le=2**63-1)]`；字符串/浮点/布尔/越界→422；2.14.1 复验 | 2.4.2、T02 步骤 1/A3/A4 |
| REV-08 | 异常级别与测试结果混淆 | 明确“级别≠验收结论”：正确拒绝=PASS；REVIEW 未定=BLOCKED，确认后按预期判；WARN 不豁免校验 | 2.7.0、第 5 节引言 |

> 以上为文档修订，不代表运行验收通过；REV-01–REV-08 的测试需在真实 PostgreSQL/接口环境执行并回填第 6 节。

### E.8 v0.7 复审 V7-01–V7-03 处理记录

| 编号 | 问题 | 处理 | 落点 |
|---|---|---|---|
| V7-01 | 2.6.4 仍用未定义 `hash32` | 改为 `lock_objid("attempt-key:{student_id}:{key}")`，与 2.6.2/2.6.3/T03 统一；明确禁用 `hash32`/`hash()`/`hashtext()` | 2.6.4 |
| V7-02 | 5.4 仍写 47 行 | 改为 **48 行**，与 6.2/6.4 一致 | 5.4 |
| V7-03 | D-20 影响面漏 M-29c | D-20 影响列与回改清单补 M-29c | 1.6 D-20 |

> 历史版本说明：本节记录 v0.7 当时的修订；当前文件已升为 v0.8，当前适用口径以文档头部、正文和 E.9 为准。

---

### E.9 v0.8 按终版审查报告修订（2026-11-10）

依据：《基础作答系统开发文档 v0.7 终版审查报告》（**待归档**；入仓后应存放于仓库 `docs/acceptance/attempt-system/基础作答系统开发文档_v0.7_审查报告_20261108.md`；当前本机未见该文件，原绝对路径不作为可依赖引用）。原 v0.7 被审文件哈希为 `ecdfb11e7ba326affb0a494edb27bf4ec84b75df345038adc17d26ae8b1b6082`，原文另存审查证据目录，保留历史行号与实验适用对象。

| 编号 | 本版文档修改 | 实施/验收落点 | 当前状态 |
|---|---|---|---|
| R7-01 | JSON 使用 JsonId，普通路径使用允许转换且受限的 PathId | 2.4.2、T02、T06-A12 | 设计已修订，实际路由集成待实现/复验 |
| R7-02 | 未知提交按成功/标记/两表无记录/读取失败恢复，修正 E11 与 M-34 前提 | 2.6.4、2.7.1、T06-A9、M-23/M-34 | 设计已修订，真实库故障验证待执行 |
| R7-03 | 原分级表及矩阵引言统一；正确处理可 PASS，REVIEW 未决 BLOCKED | 2.7.0、第 5 节、回填规则 | 开发文档已统一；需求 v0.20 对应解释待负责人确认/同步 |
| R7-04 | 代码回退与数据库降级分支明确，默认保留表和 0005 | 2.8.3、T01/T08 迁移证据 | 文档已修订，未执行回退或迁移 |
| R7-05 | 作答服务先脱敏再转换 AppError；禁止原始参数/驱动 DETAIL/异常链进入日志 | 2.2/2.7.3/2.9、T06-A15/T07-A7/T08-A9、M-23a | 设计已修订，真实错误与日志集成待验 |
| R7-06 | 脚本明确有写入，指定专用样例、finally 恢复和重复运行前置 | T09-A1–A8、T10-A7 | 设计已修订，数据/运行证据待补 |
| R7-07 | 增加默认限次的不同键双会话自测；M-32/M-41 不解冻 | 2.6.3、T06-A14/T08-A10、6.3a、附录 A | 自测方案已补；D11/D-14 与开工门禁仍未解决 |
| 完善建议 1 | CHECK 短名与显式 UNIQUE/INDEX 最终名分开说明 | 2.3.2、T01-A6 | 文档已修订 |
| 完善建议 2 | 增加正确率 1/8→13 的 half-up 边界 | 2.5.3、T05-A7 | 用例方案已补，项目测试未运行 |
| 完善建议 3 | HTTP 状态与标记断言补映射 T06/T08 | M-24–M-29、M-37/M-38 | 任务责任已同步 |

**统计与范围**：主验收矩阵由 48 行增为 **49 行**（新增 M-23a），红线仍为 13 项，任务卡仍为 10 张；T06-A14 等默认策略实现自测另列 6.3a，不混入通过率。本轮仍只交付 A/C/D 接口方案；API-2、结果页、解析治理保持冻结，v0.20/T2/T3/D11/D-14/D-20 等真实未决状态保留。

**本次性质**：仅按审查意见修改开发文档并检查编号、映射和口径一致性；未编写业务代码、未运行数据库/迁移/业务接口/并发验收。审查方既有独立库级实验仅证明相关技术行为，不代替本项目实际实现验收，也不填入第 6 节为项目 PASS。

### E.10 v0.10 版本统一记录（2026-11-10）

| 项 | 处理 |
|---|---|
| 版本统一 | 以 2026-11-10 的 v0.8 内容为唯一权威版本，升为 v0.10；工作区旧 v0.9（2026-11-08）归档为 `development_v0.9_20261108.md`，不再作为依据 |
| 版本谱系（V10-03） | 2026-11-08 的 v0.8 为 48 行；2026-11-10 的 v0.8 已含 **M-23a 日志项，为 49 行**。v0.10 以 2026-11-10 v0.8 为基线，**未新增/删除矩阵行或任务卡**；49 行不是 v0.10 引入的变更，而是该基线与 11-08 快照的差异，已在 E.9 记录 |
| 改动范围 | 仅文档头、版本引用、审查报告引用、1.3.5 建议与结尾版本号；**未改动任何设计、任务卡与验收矩阵**（相对 2026-11-10 v0.8 基线） |
| 本次补充（V10-01/V10-02） | 2.8.3 恢复 V8-01/V8-02：路径 A 旧应用不执行 Alembic、用保留 0005 的新 Alembic 目录或查 `alembic_version`；路径 B 记录导出文件名/哈希/行数并取得书面授权 |
| 审查状态 | v0.8 依据 v0.7 终版审查报告修订；**v0.10 本身仍待独立复审**，不得据此宣称 PASS |
| 未决项 | v0.20 确认、T2/T3、D-14、D10/D11/D-20/D-21、验收数据来源，均保持原文状态 |

### E.11 v0.10.1 按 V10-01–V10-03 修订记录

| 编号 | 问题 | 处理 | 落点 |
|---|---|---|---|
| V10-01 | v0.9 已修正的 V8-01 在 v0.10 的 2.8.3 中丢失 | 恢复：默认路径旧应用不执行 Alembic；验证用保留 0005 的新 Alembic 目录或只读查 `alembic_version`；禁用不含 0005 的旧镜像；明确路径 A 迁移版本仍为 0005 | 2.8.3 表格/步骤 |
| V10-02 | v0.9 已修正的 V8-02 丢失 | 恢复：路径 B 导出记录文件名/SHA-256/各表行数、校验可读并取得书面授权后再 downgrade | 2.8.3 步骤 1/2 |
| V10-03 | E.10 称未改矩阵，但当前为 49 行/M-23a | 澄清版本谱系：2026-11-08 v0.8 为 48 行；2026-11-10 v0.8 已含 M-23a、为 49 行；v0.10 以 11-10 v0.8 为基线，未新增/删除矩阵行 | E.10“版本谱系” |

> 版本确认：**当前文件为 v0.11**；v0.10.1/v0.10/v0.9/v0.8 仅作历史版本引用。

### E.12 v0.11 负责人签认与门禁解除（2026-11-10）

| 项 | 内容 |
|---|---|
| 负责人确认 | 需求 v0.20 编修性补充；D10=B（维持禁止）；D11=A（仅汇总+同卷 1 次）；T2=中性 `attempt-system`；T3=3.14.x 开发+验收；D-01/03/04/05/13/15/16/17/19/20/21 按本文建议口径 |
| D-14 | 已由需求 v0.21 修订关闭：V-21/EX-23/V-E4 增加“P1 生效后”限定 |
| 门禁变化 | T01–T10 由 BLOCKED → **可开工**；T10 与 V-E 系列在验收数据就位前仍记 BLOCKED |
| 未变 | R 组/API-2/结果页继续冻结；模块二 6 接口与 0001–0004 迁移不改；本轮只做 A/C/D |
| 留痕 | 负责人 2026-11-10 确认（书面件待补）；本文随之升 v0.11 |

### E.13 v0.12 T01–T03 验收回改（2026-11-10）

| 项 | 内容 |
|---|---|
| 依据 | 独立验收报告（T01–T03，19 项可复现标准全部 PASS；本回改为其"建议但非阻断"项） |
| 命名表补齐 | §2.3.2/2.3.3/2.3.4 补列 9 个已实现对象：1 UNIQUE、3 CHECK、5 FK（列级定义原有，仅命名表遗漏） |
| 序列化口径 | `submitted_at` 示例改为 `Z`，并注明 `+00:00` 等价 |
| 键大小写 | 明确十六进制大小写均接受 |
| 代码 | 未改任何代码；仅补文档口径，保持文档与 T01–T03 实现一致 |
| 结论 | v0.12 作为 PR1 的文档基线 |

---

> **文档结束**。当前为 **v0.12** 开发文档草案；修订后的方案与任务可供评审，**未实施项目开发、数据库迁移或业务运行验收**。开工仍受 1.3.4 门禁约束，实际结果须由真实验收人按第 6 节回填。

