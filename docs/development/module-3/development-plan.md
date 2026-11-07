# 模块三开发文档：自动数据处理与入库

> 文档版本：V1.9；更新日期：2026-11-07（Asia/Shanghai）；对齐需求V2.3及全项目统一技术版本V1.2，冻结编号沿用M3-WIN64-1.1.0。
> 当前默认stop_after=align；本轮已获授权执行第7—8步，显式使用assemble / annotate_sample / annotate草稿停止点，第9步前硬停止。
> 本文区分设计、组件实跑和完整验收；`MEDICAL_VALIDATION=NOT_CLAIMED`。

本轮新增R15扫描原卷独立全链路及9.2质量统计，均通过本套检查；交接材料和当前结果见[独立验收交接](independent-acceptance.md)。扫描初稿270/275，5个句号通过API纠正；首次完整标注13/25经12题真实修复后25/25通过。当前173个不同测试用例通过。以下第7—8步计数及停止点保留为历史，不作为最新状态。

本轮最新范围为用户明确授权的本套第1—10步后端全流程，详见[第9—10步及全流程说明](full-pipeline.md)。上一轮第9步前停止及下文早期阶段观察均为历史记录；每题主要技能和答案证据必有、错因有依据才标注的规则不变。默认align停止点仍保留，显式入库与后续人工确认动作分离。

本轮增量：已通过整套候选的显式completed请求可进入待审入库，API冻结原卷独立题量/题组及来源后计算任务指纹；worker重核候选并写pending。修复草稿speaker到业务speaker_code映射，复核结果按范围同步业务review_status。用户音频审批以有来源的user_confirmation记录，保留逐端300ms测量路径且不补造数值。真实本机TCP API→独立worker→业务入库、检查/复核、版本切换、独立可见确认、模块二回读及原音读取通过，详情见全流程证据（历史本地资料，随验收证据另行交接）。

历史第7—8步完成记录：真实管理员ASGI API→独立worker已完成本套25题组装与关联标注。原卷100个选项、25份答案解析、25条原卷映射、25项主要技能和25项答案证据均通过对应检查；Codex逐题语义复核25题通过，保留1项错因候选。提示词`m3.annotations.v5`，对结构失败最多3次有界尝试；整套语义修复只重请求未通过题，已通过题按哈希和逐题复核绑定复用。最终状态`awaiting_confirmation / annotate`，无业务批次，第9步未启动。147个不同回归用例已在对应环境覆盖。费用、运行修订及完整25题效果见本轮验收报告（历史本地资料，随验收证据另行交接）。下文截至第6步的运行计数和待办均为历史阶段记录。

本次变化：已有完整答案正文和提问时不再默认转写；缺少原文先待补充，只有明确选择无原文模式才运行ASR。固定原文ID、body/question、题号、原件哈希和页码；粗搜索范围不能充当最终边界，U.S./No.等缩写不误切。对齐确认后才能继续组装及后续标注。

已确认口径：5题小样≤0.50美元、单套≤2美元、阶段累计≤5美元；正文句起止误差分别≤300ms，全部必交正文与证据句仍须核听。确认预算和口径不等于已验收通过，也不越过当前对齐停止点。

当前证据：原始试卷/答案PDF及音频已通过真实管理员API→独立worker→align整套运行。原卷自动导出8篇25题，程序生成140正文句＋25提问句；165句字词及ID全部一致，3句仅直/弯引号差异。全部330端点与上次样本相差≤300ms（起点最大28ms、终点最大104ms），自动异常、相邻重叠及搜索贴边均为0。运行621.596秒，ASR/LLM/组装/业务入库均为0；118个不同回归用例已在各自环境覆盖。正式证据见原件自动链路报告（历史本地资料，随验收证据另行交接）。旧人工准备样本只用于隔离评估；独立人工300ms绝对精度、标注及全业务入库验收未声称。

证据及详细停止规则见[对齐复核说明](alignment-review.md)与当前自动修正报告（历史本地资料，随验收证据另行交接）。修订前需求V1.7与开发V1.2保存在同步前快照（历史本地资料，随验收证据另行交接），历史ASR产物保留，不作为当前正文或题干。

### 原件自动准备流程（V1.5）

1. 登记原始试卷、答案解析与音频及各自SHA-256；自动模式`reference_preparation=auto`不传`reference_segments`，可信题量可从原卷导出。
2. 试卷有文字层则直接提取；答案扫描页由PaddleOCR官方文本检测、PaddleX SortQuadBoxes排序及CropByPolys透视裁图，以中文识别器识别标题、英文识别器原生提取正文/提问，保留原页和行框、原始读数与置信度。
3. 从原卷Questions…are based on…独立读取连续题组范围；与答案的News Report/Conversation/Passage顺序及完整题号交叉检查。无法识别的版式、缺句缺题、冲突均停止。
4. 清除来源引用标记、保留OCR原生单词边界，按说话人和英文句界分句；保存稳定ID、原件哈希和来源页码。禁止用历史ASR补字或预录入当前套别答案。
5. 原音按20秒核心加两侧2秒上下文生成CTC声学特征；以篇章开头原文全局定位，再按完整原文顺序定位每句，形成带余量的搜索范围。该阶段不生成自由转写，粗时间不作为最终边界。
6. 使用固定`m3.reference-ctc.v2`精细对齐，输出边界、分数和风险；在align等待确认，不进入组装、DeepSeek、业务入库或版本激活。

生产实现：`document_reference.py`、`reference_document_scan.py`、`ocr_refinement.py`、`acoustic_features.py`、`reference_locator.py`、`auto_reference.py`；由既有API及worker调用。离线原件复跑入口为`python -m app.module3.auto_reference_review --paper ... --answer ... --audio ... --output ...`，使用ASR环境启动，OCR自动转入独立OCR环境。开发与实跑证据见自动链路报告（历史本地资料，随验收证据另行交接）。旧人工准备样本只作对照，不进入生产输入；实际通过范围以该报告为准。

## 1. 需求与实现基线

### 1.1 文档依据、规则和证据等级

本文须与下列文件一起使用。需求编号沿用 M3-01—M3-12，回归编号为R01—R21；T01—T14为实施任务，A01—A41为验收场景。R17—R21及A37—A41对应本次原文路线和停止点变化。

| 依据 | 本文采用的口径 |
| --- | --- |
| [全项目统一技术版本V1.2](technical-version.md) | 当前统一版本入口；冻结编号M3-WIN64-1.1.0及既有组件/解释器/锁/模型revision不升级；新增英文识别和轻量检测权重按同日资源补充登记；原模块三V1.1留作历史 |
| [模块三需求 V2.2](../../requirements/module-3/requirements.md) | 本套后端全流程、逐层检查和审批追溯；三个环境统一Python 3.13.16 |
| 16 表结构及词典快照（历史本地资料，随验收证据另行交接） | SHA-256：`6348030d2b5acb49e0cf036487f4ddd508428f33b0033e5cfb4261d40a986580`；包含字段、规则及部分词典/关系行 |
| [逐字段实施映射](field-mapping.md) | 配套开发设计，逐字段区分现有列、新列、审计承载和后置项；不是已迁移报告 |
| [CONTRIBUTING](../../../CONTRIBUTING.md)、[命名规则](../naming-conventions.md)、[目录决策](../../decisions/common/0003-document-organization.md) | UTF-8、LF；代码 `snake_case`，文档 `kebab-case`；增量迁移；实现、需求、验收分开存放 |

本次检查了 `D:/AGENTS.md`、`D:/ppt or work/AGENTS.md`、工作区根及仓库内（含隐藏目录、排除 `.git` 与依赖目录）的 `AGENTS.md`，未发现适用文件；没有据此虚构项目规则。后续开工如出现 AGENTS.md，应先阅读并记录新增约束。开发阶段按贡献规则建立 Issue、从最新 `develop` 创建任务分支，通过 PR 合并；Issue #7和独立任务分支已建立；本次文档同步不创建新PR、合并或部署，开发工作区现状见1.2。

证据目录：本轮调研与基线快照（历史本地资料，随验收证据另行交接）。其中 `input-files.json` 记录输入哈希；`baseline-files.json` 和 `baseline-evidence/` 保存固定提交的源码及文档；`github-evidence/` 保存本轮实际读取的 GitHub 元数据、源码和许可证。它们不是运行测试证据，不应将受控材料或大体积证据包直接提交公开仓库。

V1.2同步记录：本次将最新技术基线、需求、processing-profile和新旧API锁文件逐项比较，确认API目标由3.14.10改为3.13.16，profile由 `M3-WIN64-1.0.0` 改为 `M3-WIN64-1.1.0`；新旧API锁均39个包且包版本一致。ASR/OCR解释器、模型和推理参数未因此改变。对比证据保存为 `input-files-v1.2.json`；原 `input-files.json` 保留为首次编写的历史身份记录，旧开发文档和文档检查报告保存在 `history/development-v1.1/`，不覆盖旧观察。该记录仅表示2026-11-04的版本同步；预算及300ms口径后来已由用户确认，当前按1.5—1.6执行。

### 1.2 集成基线与当前独立开发状态

| 对象 | 2026-11-06本机核对 | 解释边界 |
| --- | --- | --- |
| 原仓库ShengShengRuEr | develop，HEAD b965a0f，工作区干净 | 保留集成版本；本次未重新查询远端分支头 |
| 独立开发目录ShengShengRuEr-module3 | feature/7-module3-auto-processing，HEAD 8ace961；有后续未提交实现 | 模块三代码及开发文档在此修改，尚未合并为正式交付 |
| 解释器/环境 | API、处理、OCR分别使用Python3.13.16独立环境 | 原文对齐使用处理环境内固定CPU模型；无需先运行GPU转写 |
| 当前方法 | reference默认、stop_after=align；ASR仅显式无原文路线 | 相同组件版本下通过文字来源、代码、原文/分句/定位指纹区分任务 |
| 技术证据 | 真实API→worker→align通过；165句自动提取/定位/对齐，全部118个不同回归用例在对应环境验证 | 证明本套材料与参考样本一致，不等于独立人工绝对精度或标注/业务入库通过 |
| 人工及完整验收 | 300ms整套核听、标注语义及全流程入库读取尚未验收 | 保持待确认；不签整体PASS，不修改旧批次或可见性 |

2026-11-04的远端源码、版本调研和旧运行观察保存在历史证据目录；按记录日期解释，不作为2026-11-06新运行结论。

### 1.3 已确认需求与对应关系

| 需求 | 已确认内容及边界 | 实施任务 | 验收场景 |
| --- | --- | --- | --- |
| M3-01 | 原件登记、哈希、来源、可信应有题量；不能以识别题数自证完整 | T01、T04、T10 | A01、A02、A09、A10、A38 |
| M3-02 | 管理员通过 API 创建任务；所有管理员可统一管理 | T04、T05 | A03、A04、A05 |
| M3-03 | 独立进程执行，状态、失败、草稿可查 | T05、T11 | A05、A06、A07、A08、A25、A38、A40 |
| M3-04 | 同套文本/扫描提取；原文优先逐句对齐，用户确认后组装；显式无原文ASR | T02、T06、T07、T08 | A11、A12、A13、A14、A15、A34、A37—A41 |
| M3-05 | 每题主要技能及其证据、答案证据必交；扩展关系有依据才生成 | T03、T09、T10 | A16、A17、A18、A19、A33 |
| M3-06 | 补九张业务表及必要辅助表；增量迁移、统一正式 ID | T01、T03、T11 | A20、A21、A29、A35 |
| M3-07 | 原卷题号、展示→底层选项映射、答案语义不变 | T08、T10、T12 | A09、A10、A22、A23 |
| M3-08 | 初稿、历史、幂等、管理员确认后整体切换；切换默认隐藏 | T05、T10、T11、T12 | A24、A25、A26、A27、A36、A40 |
| M3-09 | 音频版本不覆盖、身份冲突拒绝、失败仅清理本次所有文件 | T04、T07、T11 | A02、A14、A28、A30、A31、A39 |
| M3-10 | 保留自动初稿、修正前后、操作者和依据；改动使关联复核失效 | T09、T10、T14 | A18、A19、A32、A33、A41 |
| M3-11 | 复用模块二题库、鉴权、可见性、Range 和媒体访问 | T12、T13 | A03、A23、A26、A27、A31 |
| M3-12 | 初稿与最终质量分报；逐题核对、整套核听、真实后端链路 | T13、T14 | A11、A12、A31、A32、A33、A34、A41 |

固定验收样例为 2025 年 6 月四级第一套，正文按句切分，证据可引用连续多句。只覆盖实际测试的固定版式和清晰度。默认采用核对答案原文→WhisperX→对齐后用户确认→后续DeepSeek；ASR只用于明确选择的无原文路线，原始音频留在本地。采用管理员确认版本切换，切换后再独立确认学生可见。

本期不开发前端、播放器、学生练习、个体错因诊断、推荐算法、跨卷内容复用或派生音频链。不新增 Celery、Redis、管理 UI、云端语音供应商对照。JSON、Excel 和手工试填只能辅助核对，不能替代自动链路和 PostgreSQL 入库。

### 1.4 现有能力与实际缺口

以下链接均固定到 `b965a0f`，代码入口的函数名以该提交为准。

| 入口与证据 | 当前实现 | 模块三开发缺口 |
| --- | --- | --- |
| [models_listening.py](https://github.com/ShengShengRuEr-Team/ShengShengRuEr/blob/b965a0f3771c9f6212be29b65fda326ce0307b11/backend/app/db/models_listening.py) | 7 张业务表＋4 张批次/检查/可见性辅助表，模块一另有4张认证表；现有业务字段是16表的子集 | 9 张业务表、任务、来源、版本、复核记录；补齐必交字段，详见配套映射 |
| [import_module2.py](https://github.com/ShengShengRuEr-Team/ShengShengRuEr/blob/b965a0f3771c9f6212be29b65fda326ce0307b11/backend/app/import_module2.py#L153) `run_import` | 七段 JSON 入库、临时ID映射、媒体版本保护、有效结果幂等；末尾自动激活批次 | 不能原样调用：需拆成待审写入和显式激活；原件/标注方法/证据尚未纳入指纹；失败草稿和执行记录不足 |
| [prepare_module2_materials.py](https://github.com/ShengShengRuEr-Team/ShengShengRuEr/blob/b965a0f3771c9f6212be29b65fda326ce0307b11/scripts/prepare_module2_materials.py#L161) `build_payload` | 从已有工作簿整理导入包 | 没有原始 PDF/OCR/音频自动识别；不能把该脚本当模块三识别链路 |
| [content_check.py](https://github.com/ShengShengRuEr-Team/ShengShengRuEr/blob/b965a0f3771c9f6212be29b65fda326ce0307b11/backend/app/services/content_check.py#L28) `evaluate/run_check` | 可信题量存在性、题序、A—D映射、字段与音频文件存在性 | 未证明哈希、可解码性、解析来源、全部句级时间、技能证据及语义复核；音频当前从 `paper.playback_audio_id` 取，草稿检查应改用目标批次音频 |
| [0003/0004迁移](https://github.com/ShengShengRuEr-Team/ShengShengRuEr/blob/b965a0f3771c9f6212be29b65fda326ce0307b11/backend/alembic/versions/0004_expected_count_source.py) | 可信题量字段及来源已合入；无来源旧题量/检查失效 | 作为迁移前置和回归，不能重复列为待开发修复；运行库revision待查 |
| [listening.py](https://github.com/ShengShengRuEr-Team/ShengShengRuEr/blob/b965a0f3771c9f6212be29b65fda326ce0307b11/backend/app/repositories/listening.py#L156) | 按当前批次读取；管理员区分展示答案和底层答案 | 扩展批次一致性与历史查询；保留映射换算；已有展示函数含恒等回退，新增写入/检查不得以此接受未知映射 |
| [学生路由](https://github.com/ShengShengRuEr-Team/ShengShengRuEr/blob/b965a0f3771c9f6212be29b65fda326ce0307b11/backend/app/api/listening_papers.py)、[管理员路由](https://github.com/ShengShengRuEr-Team/ShengShengRuEr/blob/b965a0f3771c9f6212be29b65fda326ce0307b11/backend/app/api/admin_listening_papers.py) | 列表、整卷、受控音频、配套、检查读取、confirm/cancel可见性 | 无材料、处理任务、历史标注结果、校正及当前版本确认接口 |
| [conftest.py](https://github.com/ShengShengRuEr-Team/ShengShengRuEr/blob/b965a0f3771c9f6212be29b65fda326ce0307b11/backend/tests/conftest.py)、[模块二回归](https://github.com/ShengShengRuEr-Team/ShengShengRuEr/blob/b965a0f3771c9f6212be29b65fda326ce0307b11/backend/tests/test_module2_recheck.py) | 真实PostgreSQL夹具、HTTP鉴权、文件回滚/独立题量等回归；夹具有清空测试schema行为和开发库防护 | 新增模块三故障、竞争、迁移、权限与真实流程证据；本轮不运行此夹具 |

### 1.5 已确认口径与剩余前提

| 编号 | 当前状态 | 仍需完成 |
| --- | --- | --- |
| U01 | 用户已提供受控DeepSeek配置，确认5题≤0.50美元、单套≤2美元、累计≤5美元 | 进入收费阶段前检查配置可用性、剩余额度及价格；本轮已获准第7—8步，禁止进入第9步，不重复索取同一预算 |
| U02 | 已确认正文起止误差分别≤300ms，证据句全部核听 | 30正文句抽样与整套正文核听、参考边界和修正记录；尚未形成精度PASS |
| U03 | 已生成300DPI无文本层派生扫描输入并实跑OCR | 完整管理员API双路径真实处理及内容核对仍须验收；不外推实物扫描版式 |
| U04 | 三个3.13.16环境及固定组件已完成部分诊断/实跑 | 完整API→worker→标注→入库→模块二读取仍待执行；部署库状态单独核实 |
| U05 | 原卷25题、8题组已独立核对用于固定样例；原文140正文句＋25提问句为本次分句结果 | 不硬编码为所有试卷的数量；最终来源及逐题复核仍须记录 |

### 1.6 已确认口径的执行方案

预算与300ms阈值已由用户在本会话明确采用；以下保留执行方法，不再作为未决建议。本轮已明确授权第7—8步真实标注，仍不授权业务入库或版本切换。

#### D01｜调用预算：小样先跑，按阶段限额

**已确认额度：5题小样最多0.50美元；一次整套运行最多2.00美元；模块三本阶段真实调用累计最多5.00美元。** 小样、文本路径、扫描路径、重试和失败调用均计入累计额度；不能拆成多个task绕开总额。这些是已确认预算上限，不是实际费用估算或充值要求；费用以账号真实扣费和调用账本为准。

执行方法：

1. 密钥已有受控配置、预算已确认；真实试跑前核查配置可用性和剩余额度；文档、命令行及日志不保存密钥。先处理5道有代表性的题，验证JSON、词典、证据和调用用量，再启动整套。
2. 继续采用固定 `deepseek-flash`、非思考模式、temperature=0、max_tokens=4096、单并发和最多额外2次重试，不另换更贵模型。文本/扫描共享完全相同且有效的标注输入时允许复用，并记录缓存键与原调用，不能冒充再次调用。
3. 2026-11-04核对的官方高峰、缓存未命中输入价为每百万token **0.30美元**，输出价为每百万token **1.20美元**。预算预留按较高适用价计算，不依赖命中缓存或低峰优惠；执行时重新核对并保存价格快照。[官方模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)
4. 账本记录每次请求的输入/输出token、响应model、时间、重试、实耗/估算/未知三种计费状态。请求前按输入token保守估计及4096输出上限预留费用，并保留20%安全余量；不足容纳下一次请求时不发起。请求超时的消费未知仍保留预留额，不能直接按0费用继续重试。
5. 任何层级触顶时保存已完成结果，任务进入awaiting_confirmation并给出BUDGET_LIMIT；停止新调用，不自动充值。客户端预留属于费用控制措施，不是供应商账单的绝对硬上限保证；若账号提供硬限额，再同步设置。预算不得绕过U01的真实调用前置条件。

对应T05/T09/T13；A17增加小样/单轮/累计额度、超时保留预留和跨task累计断言。真实调用尚未进行时，真实标注及用量验收仍为BLOCKED。

#### D02｜句级时间：已确认300ms阈值，超差逐句修正

**已确认交付标准：每个必交正文句起点和终点绝对误差分别≤300ms；所有答案/技能证据引用句100%完成核听和复核。** 这是用户确认的项目口径，不是模型精度保证或本轮已测结果；缺人工参考和完整核听时不得记为精度PASS。

执行方法：

1. 先抽取至少30个正文句，覆盖新闻、长对话、篇章，分布在整段音频前/中/后，包含句间短停顿、连续语流和较长停顿；另检查提问片段与说明边界。记录抽样规则，不只选容易对齐的句子。
2. 人工参考起点取首个可听语音开始，终点取最后可听语音结束，不把尾随长静音计入句子。对同一原音版本，以绝对毫秒记录参考值和疑点；边界有争议先复听标定，不能直接把模型结果当参考。
3. 对每句计算 `abs(auto_start_ms-reference_start_ms)` 和 `abs(auto_end_ms-reference_end_ms)`，任一超过300ms即列入修正清单。缺句、无法对齐、插值或原时间回退都计为异常，不从分母中剔除。
4. 自动初稿可将“双端误差均在300ms内的句子比例95%”作为试跑观察目标，**不新增为自动初稿最低正确率或通过门槛**。初稿全部如实报告；任何比例都不能免除最终错误修正。
5. 正式样例完整核听并逐句记录，最终所有必交正文句满足已确认的边界标准、无未决缺句/错归属，证据引用句逐条核听；超差先局部重新对齐，仍超差则保存有原音依据的人工校正及复核。校正后重新生成受影响证据、检查和result_hash。
6. 30句小样用于验证已确认的300ms口径，不替代整套核听。若小样显示300ms口径不适用，应先提交误差分布、具体难例和修订建议，确认并冻结新口径后再进行正式评测，不能看最终输出后放宽阈值。

对应T07/T10/T14、A14/A15/A32/A33/A34。未实际标定或未完成整套核听时，相应精度/内容结论保持BLOCKED。

#### D03｜运行资源：优先现有8GB机器，分阶段释放模型

已保存的环境观察记录显示RTX 5060 Laptop、8151MiB显存、驱动580.88；它是前次资源盘点，**不是本轮重新探测或推理成功证据**。已有环境观察（历史本地资料，随验收证据另行交接）

**原文默认路径使用CPU对齐，不以GPU可用、large-v3模型或先完成ASR为前置。** 复用已有环境，不预设购置硬件。仅显式无原文ASR路线按固定large-v3/CUDA int8_float16执行，完成后释放模型再CPU对齐；以下GPU/OOM降级处理仅适用于该可选路线。

若失败，按以下顺序处理：

1. 先区分DLL/驱动/模型文件错误与OOM；环境配置错误按T02修复，不因一次失败就换模型或设备。
2. OOM时确认没有并发识别任务、额外GPU模型或无关占用，释放阶段模型后以同profile单次复测；保留失败和复测证据。分块用于限制中间张量及保留原音偏移，不能宣称它会减少模型权重本身的显存占用。
3. 仍无法执行时，建议使用**同一large-v3模型revision、CPU int8、单并发**作为独立降级profile，例如 `M3-WIN64-1.1.0-CPU-1`。该编号仅为待采用示例，不表示已生成配置或已通过。另保存配置/方法hash及实际耗时，复验转写、对齐和最终内容；不能把CPU结果写成原GPU基线通过，也不自动改成small模型降低质量要求。
4. CPU路线若实际速度不可接受，再提交已测整套耗时、预期工作量以及现有设备继续处理/补充运行资源的具体影响，届时才讨论新增资源。本文不承诺未经实测的完成时间，不租用或购买资源。

对应T02/T05/T07、A13/A14/A35；所有降级复测必须保留原失败记录和版本差异。

#### U03/U05｜材料准备直接落实到开发任务

- **扫描输入**：优先使用已有同套真实扫描件；若没有，由T06以原文本PDF按300DPI生成仅含页面像素的派生PDF或PNG，保留原文件hash、页码、渲染器版本/参数和派生产物hash。独立OCR任务从像素输入运行，不读取原文本层，明确结论仅覆盖该派生条件。无需为此另选OCR供应商。
- **可信题量**：T01从原卷逐页登记听力题号和题组起止范围，与来源答案题号交叉核对；本套预计25题，但正式值只能在来源核查后登记。保存原件hash、页码/位置、核对记录；冲突待确认，不能以识别/导入结果的数量回填基准。

扫描/OCR及原文CPU对齐已有组件实跑证据；本轮未进行收费标注或正式业务入库，未完成整套人工核听。各项按实际证据分报，不沿用历史“全部未执行”，也不签完整交付PASS。

## 2. GitHub技术调研与采用方式

### 2.1 方法和维护情况

以下为本轮实际访问上游仓库API、固定tag对应源码和许可证所得。观察时间约为 `2026-11-04T13:34Z`，日期列为UTC。`pushed_at`反映仓库推送活动，不等于默认分支代码提交；“未归档＋近期活动”也不构成Windows兼容、无缺陷或维护承诺。默认分支和最新版本仅用于评估维护，开发仍使用冻结版本。

| 编号／仓库 | 固定引用→源码提交 | 本轮维护观察 | 许可证核对 |
| --- | --- | --- | --- |
| G01 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | `v1.2.1` → `65882eee9f5cdbeeb2d877f1131d48cf241b327d` | 未归档；默认分支最近提交2026-11-02；最新release仍为v1.2.1（2025-10-31） | [MIT](https://github.com/SYSTRAN/faster-whisper/blob/65882eee9f5cdbeeb2d877f1131d48cf241b327d/LICENSE) |
| G02 [WhisperX](https://github.com/m-bain/whisperX) | `v3.8.6` → `3ccc17b8de34f305300f8a3fd3c9f76ba820c0d0` | 未归档；默认分支最近提交2026-10-22；最新release v3.8.6（2026-05-25） | [BSD-2-Clause](https://github.com/m-bain/whisperX/blob/3ccc17b8de34f305300f8a3fd3c9f76ba820c0d0/LICENSE)，不能沿用旧资料的其他许可证结论 |
| G03 [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | `v3.7.0` → `b03f46425e8ff4442b268ce449e3eef758146cd4` | 未归档；默认分支最近提交2026-09-16；最新release v3.7.0（2026-06-11） | [Apache-2.0](https://github.com/PaddlePaddle/PaddleOCR/blob/b03f46425e8ff4442b268ce449e3eef758146cd4/LICENSE) |
| G04 [pdfplumber](https://github.com/jsvine/pdfplumber) | `v0.11.10` → `7d4f2f582f2d99f9e60ba522fdf7afd2f6d54c62` | 未归档；默认stable最近提交2026-06-15，仓库推送2026-10-15；release v0.11.10（2026-06-15） | [MIT](https://github.com/jsvine/pdfplumber/blob/7d4f2f582f2d99f9e60ba522fdf7afd2f6d54c62/LICENSE.txt) |
| G05 [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | `5.14.0` → `21f85e273036f3bade4f67d896e1d05927e5f4b1` | 未归档；默认分支最近提交2026-11-04；release 5.14.0（2026-10-04） | 源码[许可头](https://github.com/pypdfium2-team/pypdfium2/blob/21f85e273036f3bade4f67d896e1d05927e5f4b1/src/pypdfium2/_helpers/page.py#L1)：Apache-2.0 OR BSD-3-Clause；[许可说明](https://github.com/pypdfium2-team/pypdfium2/blob/21f85e273036f3bade4f67d896e1d05927e5f4b1/README.md#licensing)另区分文档与PDFium二进制依赖 |
| G06 [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy) | `rel_2_1_4` → `632c664fe9ff67ebaecc6ceed99262afdf80011f` | 未归档；默认分支最近提交2026-11-04；观察到更新release rel_2_1_8，不因此升级项目 | [MIT](https://github.com/sqlalchemy/sqlalchemy/blob/632c664fe9ff67ebaecc6ceed99262afdf80011f/LICENSE) |
| G07 [TorchCodec](https://github.com/pytorch/torchcodec) | `v0.7.0` → `7dd6092b40a76a262b633c591d8edb6ce0a86c11` | 未归档；仓库推送2026-11-04；最新release v0.17.0（2026-09-30），冻结版明显落后，需实际验证组合 | [BSD-3-Clause](https://github.com/pytorch/torchcodec/blob/7dd6092b40a76a262b633c591d8edb6ce0a86c11/LICENSE) |
| G08 [GyanD分发仓库](https://github.com/GyanD/codexffmpeg)／[FFmpeg源码](https://github.com/FFmpeg/FFmpeg) | 分发release `7.1.1`；源码按归档README声明 `db69d06eee` | 分发库未归档；最近默认提交2026-10-10；新release为9.0.2（2026-09-20），仍用7.1.1 | 已读取冻结ZIP的LICENSE和README，**该full shared构建标明GPL v3**；不能泛称所有FFmpeg都是LGPL |

GitHub API对pypdfium2的 `license` 返回null、顶层 `LICENSE` 返回404；本轮继续核对了源文件SPDX头、`LICENSES/`、`BUILD_LICENSES/`和README，不能把null当成“没有许可证”。最初误查 `huggingface/torchcodec` 得到404，已更正为 `pytorch/torchcodec`；失败记录保留，不作为采用依据。

### 2.2 关键代码、适配和局限

| 引用 | 可借鉴的代码及行为 | 本项目适配 | 局限与失败处理 |
| --- | --- | --- | --- |
| G01 | [transcribe.py](https://github.com/SYSTRAN/faster-whisper/blob/65882eee9f5cdbeeb2d877f1131d48cf241b327d/faster_whisper/transcribe.py)、[audio.py](https://github.com/SYSTRAN/faster-whisper/blob/65882eee9f5cdbeeb2d877f1131d48cf241b327d/faster_whisper/audio.py)：转写入口接受波形，文件解码走PyAV | 默认先用TorchCodec规范化为16kHz/mono/float32，再传波形；完整消费转写迭代器，保存原始片段、VAD和参数 | 识别、VAD会漏段或错词；不能从选项/答案反写“听到”的内容；PyAV入口另测 |
| G02 | [load_align_model与align](https://github.com/m-bain/whisperX/blob/3ccc17b8de34f305300f8a3fd3c9f76ba820c0d0/whisperx/alignment.py#L80)、[失败返回原时间](https://github.com/m-bain/whisperX/blob/3ccc17b8de34f305300f8a3fd3c9f76ba820c0d0/whisperx/alignment.py#L210)、[插值及同时间合并](https://github.com/m-bain/whisperX/blob/3ccc17b8de34f305300f8a3fd3c9f76ba820c0d0/whisperx/alignment.py#L366) | 从已核验本地revision路径加载英文模型，CPU对齐；保存字符级原始依据用于判别回退；程序按固定句子ID汇总有效边界，回加chunk偏移 | 有start/end不等于成功对齐；空字符/无有效对齐、估算边界及被合并句子必须标为待复核，不能无声接受库的默认nearest插值；如需局部适配保留上游许可证并测回归 |
| G03 | [PaddleOCR构造参数与predict](https://github.com/PaddlePaddle/PaddleOCR/blob/b03f46425e8ff4442b268ce449e3eef758146cd4/paddleocr/_pipelines/ocr.py#L66) | 显式配置本地PP-OCRv5 server det/rec目录、CPU及禁用项，保存检测框、识别文字/置信度；项目解析器再按题号和版式组装 | 新版默认模型不能代替固定v5；OCR不理解答案归属，跨栏/断行/低清晰度须复核；不用其新VL/PP-Structure全链路替换冻结方案 |
| G04 | [Page.extract_text/extract_words](https://github.com/jsvine/pdfplumber/blob/7d4f2f582f2d99f9e60ba522fdf7afd2f6d54c62/pdfplumber/page.py#L529) | 保留页码、文字坐标、原文顺序，按页裁定文本层质量；文本层为空/明显乱码时转扫描路径并记录原因 | 无OCR能力；选项断行、阅读顺序和可用文本层仍需项目规则，不能仅依据字数判定正确 |
| G05 | [PdfPage.render](https://github.com/pypdfium2-team/pypdfium2/blob/21f85e273036f3bade4f67d896e1d05927e5f4b1/src/pypdfium2/_helpers/page.py#L353) | 300DPI使用scale=300/72；保存页尺寸、旋转、像素尺寸及坐标换算；及时关闭文档/页面资源 | 包装层许可不覆盖全部PDFium依赖；固定页面样例不代表复杂版面都可用 |
| G06 | [Session.begin](https://github.com/sqlalchemy/sqlalchemy/blob/632c664fe9ff67ebaecc6ceed99262afdf80011f/lib/sqlalchemy/orm/session.py#L1957)、[commit](https://github.com/sqlalchemy/sqlalchemy/blob/632c664fe9ff67ebaecc6ceed99262afdf80011f/lib/sqlalchemy/orm/session.py#L2059) | 服务显式事务，草稿写入与激活分离；同卷锁、乐观版本及数据库唯一索引共同保证切换 | SQL事务不回滚磁盘文件，也不回滚收费API；文件所有权清单、失败记录独立事务和阶段缓存须自行实现 |
| G07 | [AudioDecoder/get_all_samples](https://github.com/pytorch/torchcodec/blob/7dd6092b40a76a262b633c591d8edb6ce0a86c11/src/torchcodec/decoders/_audio_decoder.py#L21) | 显式sample_rate=16000、num_channels=1；验证返回采样率、形状、有限float值和总时长 | 依赖实际FFmpeg共享库；torch能用GPU不代表TorchCodec/CT2链路可用；失败禁止改用全局未知FFmpeg冒充通过 |
| G08 | [7.1.1发行](https://github.com/GyanD/codexffmpeg/releases/tag/7.1.1)、[上游许可组成](https://github.com/FFmpeg/FFmpeg/blob/n7.1.1/LICENSE.md) | 使用冻结ZIP及DLL哈希；受控绝对路径，不覆盖本机9.0；分发清单保留归档README、LICENSE及源码定位 | GyanD仓库tag提交本身不是FFmpeg业务源码；二进制许可按实际构建判定；安装、导入顺序和DLL加载仍未验证 |

MIT/BSD采用时保留版权和免责声明；Apache采用时保留许可证、适用NOTICE及修改说明；pypdfium2还须按所用wheel保存PDFium依赖许可证。FFmpeg采用实际GPL v3分发包，交付/再分发前按该构建梳理所需源码和许可材料，不宣称依赖链已完成全面法律审查。模型权重、词典及试卷资料的使用条件另行记录，不能从代码许可证推导其授权。

DeepSeek为外部服务，本项目通过现有httpx直接请求，**不因为有开源模型仓库就推断API服务权重固定或其服务许可**。以[官方模型说明](https://api-docs.deepseek.com/quick_start/pricing/)和[JSON模式](https://api-docs.deepseek.com/guides/json_mode/)核对服务行为，本轮已保存页面。JSON输出仍需检查空内容、截断和业务字段，不能把JSON可解析当作标注正确。官方服务别名不保证不可变；请求名、实际响应model、调用时间、原始响应和用量一起记录。

## 3. 目标开发方案

本章定义目标契约；独立开发目录已实现其中部分接口和处理逻辑，实际范围以1.2、各任务证据及对齐复核报告为准，不将目标设计整体标为已实现。预算与精度阈值已确认，其执行条件及待验收项见U01—U05。

### 3.1 目标流程与进程职责

```text
同套原卷/答案解析/音频登记 ＋ 独立可信题量
  → 文本提取或OCR → 核对答案正文/提问/选项/解析
  → 固定原文句子ID、body/question、题号及来源哈希/页码
  → 创建/修订reference任务（缺原文先await确认，不自动运行ASR）
  → 独立处理进程：音频16kHz单声道float32规范化 ＋ 粗搜索定位
  → CPU强制对齐：保持原文、输出每句绝对起止
  → 【当前停止点】awaiting_confirmation；核听并记录300ms检查
  → 用户明确确认继续后：题目组装及原卷映射 → DeepSeek候选标注
  → 本地检查 → 非当前pending业务批次与自动初稿
  → 内容/音频/标注复核、修正与重检
  → 管理员确认当前批次切换（原子事务，默认隐藏）
  → 独立visibility确认学生可见 → 模块二整卷和媒体接口读取
```

| 目标模块／建议入口（新增，除明确复用者） | 职责与输入输出 | 禁止跨越的边界 |
| --- | --- | --- |
| `backend/app/api/admin_processing.py`、`schemas_processing.py` | 材料、任务、草稿、差异、复核、检查和激活接口；使用现有 `require_admin` | API进程不得导入torch/Paddle等推理依赖，不在请求中完成整套识别 |
| `backend/app/services/processing/` | 材料校验、任务状态、结构检查、草稿写入、激活；复用/拆分现有导入公共逻辑 | 不重建认证、题库或第二套可见性体系 |
| `backend/app/module3/worker.py` | 独立处理解释器运行；任务领取、reference/可选ASR分支、对齐和停止点；获准后才继续DeepSeek及待审入库 | 公共契约和业务代码以Python3.13.16为目标，不依赖仅3.14支持的语法/行为；不导入FastAPI入口；不自动激活 |
| `backend/app/module3/ocr_worker.py` | OCR解释器独立子进程；输入只读材料manifest，输出版本化JSON和页证据 | 无数据库写权限、无密钥；无shell拼接，只用受控解释器＋固定参数数组 |
| `backend/app/module3/contracts.py`、`adapters/` | JSON边界、识别器适配、规范化、坐标与偏移转换 | 不把供应商临时ID写成数据库主键 |
| `backend/app/db/models_processing.py` | 来源、任务、产物、词典快照、复核、激活审计 | 失败任务持久性独立于业务草稿事务 |
| `backend/app/db/models_annotations.py` | 9张业务表与证据多句引用等必要辅助表 | 词典定义复用确认稿；不生成学生诊断 |
| 既有 `repositories/listening.py`、`services/visibility.py`、`core/audio_response.py` | 当前批次读取、最低检查、可见性和媒体流 | 学生接口只返回既有允许字段，不泄露答案、正文、解析、标注理由或原件 |

### 3.2 环境、配置与安装验收边界

| 环境 | 冻结要点 | 必须分别实测 |
| --- | --- | --- |
| API | Python3.13.16；FastAPI0.143.0、SQLAlchemy2.1.4、PostgreSQL18.6；按3.13.16重新解析的 `requirements-api.lock.txt` | 安装/pip check、py313代码检查、数据库连接、迁移、HTTP鉴权和模块一/二回归；Starlette1.7.0的TestClient依赖httpx2另有锁定 |
| 处理／历史ASR环境 | Python3.13.16；faster-whisper1.2.1、WhisperX3.8.6、CT2 4.8.3、torch2.8.0+cu128、TorchCodec0.7.0；`requirements-asr.lock.txt` | 默认align诊断核验固定DLL、TorchCodec及CPU对齐模型；仅ASR模式追加CT2/GPU/large-v3验证；PyAV另作独立检查 |
| OCR | Python3.13.16；PaddleOCR3.7.0、PaddleX3.7.2、CPU Paddle3.3.1、pdfplumber0.11.10、pypdfium2 5.14.0；`requirements-ocr.lock.txt` | 文本提取、页面渲染、固定PP-OCRv5本地模型CPU推理；方向分类/去畸变/行方向/oneDNN默认关闭 |

所有精确间接依赖、GPU wheel URL/哈希、模型revision及原生组件以原版本基线和产物清单为准，本文不另建一套宽松requirements。安装和组件实跑证据见当前状态及对应报告；不能由锁文件、旧ASR成功或组件PASS推定原文路线全链路与内容通过。

三个环境共用同一Python精确版本，不合并虚拟环境、site-packages或依赖锁。分别记录三个python.exe绝对路径、3.13.16版本、Windows x64和常规GIL构建信息；工具环境中观察到的3.14.3、模块二历史3.14.10，以及旧API锁仅用于回查，不作为当前目标。历史API锁和profile位于旧冻结产物目录（历史本地资料，随验收证据另行交接）。依赖解析由何种工具解释器驱动，与最终安装/运行解释器是两件事，不能混记。

T02在开发分支将 `backend/pyproject.toml` 的Ruff目标由py314调整为py313，核查项目Python版本声明、启动说明、测试及部署命令；随后在3.13.16真实执行导入/语法检查和认证、数据库迁移、题库、音频及测试客户端回归。独立开发目录已采用py313并在3.13.16隔离环境完成85项自动测试；部署及完整验收另报。本次文档同步不修改代码、运行配置或依赖锁。

新增配置契约：`M3_MATERIALS_DIR`（只读原件根）、`M3_ARTIFACTS_DIR`（中间结果根）、`M3_ASR_PYTHON`、`M3_OCR_PYTHON`、`M3_MODEL_ROOT`、`M3_PROFILE_PATH`、`FFMPEG_DLL_DIR`、`NLTK_DATA`、`DEEPSEEK_API_KEY`；保留 `DATABASE_URL`、`AUDIO_STORAGE_DIR` 和JWT现有配置。路径在启动预检时解析为绝对路径。密钥使用SecretStr，不写入命令行、响应或日志。`.env`须显式由各进程加载，不能假设跨进程自动读取。

默认原文模式直接用固定英文模型CPU对齐，单并发，不加载转写模型或要求GPU。仅显式无原文ASR模式采用large-v3、en/transcribe、CUDA int8_float16、beam5、batch1、VAD开启，再执行CPU对齐。冻结模型目录及哈希，禁止任务启动自动下载latest。ASR模式GPU不足/驱动或DLL失败时报告阻塞，转写CPU降级或解码器替换须记录独立方法并重新验收；默认CPU对齐不属于降级。

### 3.3 数据存储、ID和批次契约

既有七段结构继续使用 `exam_paper/audio/content_groups/passages/transcript_segments/questions/presentations`。新增 `schema_version="m3.v1"`、`sources`、`method`、`evidences`、`skill_question_relations`、`error_question_relations`、`other_relations`、`quality` 和 `issues`。草稿JSON允许不完整，正式业务行遵守非空/外键约束；不能用空解析或假技能填满数据库。

| 数据对象 | 字段与约束冻结 |
| --- | --- |
| `material_sources` | `id BIGINT`；试卷编码、类别、相对storage_key、SHA-256、大小、真实媒体类型、来源/页码说明、派生父材料ID和生成参数、登记管理员和UTC时间；内容不可原地替换。`(source_kind, storage_key, sha256)`识别重复；同路径内容变更视为冲突 |
| `dictionary_snapshots` | schema文件和确认稿引用、schema/data哈希、版本、词典行及旧ID/显示码/旧码→正式ID映射。词典表用 `(snapshot_id, stable_code)` 唯一，叶子24项技能和12项错因与目录节点分别统计 |
| `processing_tasks` | UUID主键；材料ID集合、试卷编码/可空正式ID、parent_task_id、state、stage、attempt、lease_token、worker_id、heartbeat/expires_at、input/method/result_hash、batch_id（可空）、复用来源task/batch、结构化异常及UTC时间。失败时batch_id可空 |
| `processing_artifacts` | 任务、阶段、输入指纹、产物相对路径/哈希/大小、生成时间、schema版本、来源产物ID。只追加，任务恢复必须重核哈希；管理员查询不能获得任意服务器绝对路径 |
| `import_batches`增量 | 保留pending/active/failed和is_current；新增 `result_fingerprint` 完整64位、profile/check版本及 `check_profile`（legacy/module3）。同卷同完整指纹唯一；任务执行与结果批次分离。batch_code用受长度约束的UUID编码，不截短完整指纹作为唯一依据 |
| 9张业务表 | `skills`、`skill_error_relations`、`error_question_relations`、`skill_question_relations`、`other_relations`、`evidence_items`、`classification_dicts`、`error_causes`、`language_items`；具体逐字段映射见配套文件 |
| 版本化归属 | 篇章、片段、题目、映射、内容组、证据和卷内关系均有batch_id；`(batch_id, code)`唯一；技能/错因/体裁按词典快照共享，语言点按本期批次内 `(item_type, normalized_text, sense)` 去重。保留现有非全局唯一业务码语义，不无故修改已修复的约束 |
| `evidence_segments` | 多句证据辅助表：`evidence_id,batch_id,passage_id,segment_id,sort_order,start_char,end_char`；同证据顺序唯一。只引用同批次同篇连续body句，字符范围采用Python Unicode码点 `[start_char,end_char)`；全文证据留空字符范围 |
| 复核/校正/激活 | `processing_reviews`、`processing_corrections`、`batch_activation_logs`；保存对象、前后内容/哈希、操作者、UTC时间、来源依据、判定及目标result_hash。自动初稿immutable；review_status不能替代真实记录 |

补充辅助表：`batch_paper_metadata`承载随批次变化的本套绑定/排序依据；`batch_audio_groups`承载稳定音频与批次内内容组关系；`batch_source_refs`将题目/片段/解析关联到原件页框、原始文字及转换产物。`content_checks`增量保存result_hash、规则版本和检查profile，模块三检查/复核必须匹配目标hash；不得用同批次旧结果的检查记录批准新修订。字段映射中的审计承载及这些辅助表均属于T03范围。

临时引用统一为实体命名空间内字符串 `_src_id`，例如 `q:1`、`seg:p1:3`、`ev:q1:a`；现有整数临时ID可经适配转字符串。入库顺序为：词典快照与正式词典 → 稳定试卷/音频 → pending批次 → 内容组/篇章 → 片段 → 题目/映射 → 证据/证据句 → 标注主行 → 标注证据行及其他关系。映射键为 `(task_id, entity_type, src_id)`，重复、悬空、跨篇/跨批次引用明确失败。数据库主键均由数据库分配，不沿用历史试填整数主键。

关系条件约束：

- `QUESTION_SKILL`必须有question_id、skill_id、role；只能选择当前快照中适用、启用的三级技能，目录节点不得用于题目标注。PRIMARY默认每题一个，共同主要须有理由；`SKILL_EVIDENCE`必须有owner_relation_id和evidence_id，owner指向同批次QUESTION_SKILL。每条实际技能关联均须有证据；S07/S13等专项用途必须按确认稿的使用边界判断。
- `QUESTION_ERROR_CANDIDATE`引用题目和当前快照启用的三级错因；`CANDIDATE_EVIDENCE`指向同批次候选主行。只生成有依据的候选，保留option_letter的底层字母语义。所有关系按配套映射的rulesByKind检查必需字段、允许对象字段和属性白名单，其余对象字段必须为空；不能仅检查必填而留下串用外键。
- `ANSWER_EVIDENCE`在other_relations中关联question_id和evidence_id；不同于技能证据。技能目录/先修等共享关系的batch_id为空、snapshot_id非空；卷内关系batch_id非空，二者以scope字段及CHECK区分。
- 证据时间由有效句子计算：起点为第一条引用句的起点，终点为最后一条引用句的终点。引用文字为句内子串时，时间仍取包含它的句级边界，不按字符比例推算。不得由LLM返回任意时间写入。连续多句之间不得夹入提问片段；不能只存一句ID却声明覆盖多句。
- 用复合唯一键 `(id,batch_id)` 和复合外键约束可表达的同批次归属；跨表同篇、owner种类、连续句、语义等由服务检查。普通单列FK不等于归属已正确。

### 3.4 材料、处理与API契约

材料入口冻结为**受控目录登记**，本期不增加上传接口。管理员预先将原件放入 `M3_MATERIALS_DIR`，API只接受相对storage_key。拒绝绝对路径、盘符、UNC、`..`、NTFS数据流冒号及解析后越界的symlink/junction；校验文件类型、大小及实际哈希，不能仅信扩展名或调用方sha256。任务开始与各阶段读取前重核，不一致报SOURCE_CHANGED，不覆盖已登记原件。

除既有音频流外，JSON接口沿用 `{"code": HTTP状态码, "msg": "中文说明", "data": ...}`；创建材料201、创建/重试任务202、查询/操作200。未登录/失效401，已登录非管理员403，资源不存在404，身份/指纹/并发冲突409，字段校验422，数据库不可用503。后台失败由任务issues表达；不能用HTTP200中的completed掩盖失败。

| 方法与路径（前缀 `/api/v1`） | 输入关键字段 | 输出／约束 |
| --- | --- | --- |
| `POST /admin/materials` | `exam_paper_code,source_kind,storage_key,expected_sha256,source_locator,derived_from_material_id?,generation?` | `material_id,sha256,size_bytes,media_type`；类别paper_text/paper_scan/answer_explanation/audio/transcript；同一文件可登记明确来源类别，不猜来源 |
| `GET /admin/materials/{material_id}` | ID | 登记信息、哈希、可追溯来源；无原件公开URL、无服务器绝对路径 |
| `POST /admin/processing-tasks` | `exam_paper`元数据、`material_ids,document_mode,text_source,reference_segments,stop_after,expected_question_count,expected_question_count_source,expected_question_ranges,dictionary_snapshot_sha256,profile_version` | 202：`task_id,state="pending",stage="registered"`；固定profile，材料/题量冲突409；缺少必需材料或reference原文时创建awaiting_confirmation及issues；默认text_source=reference、stop_after=align |
| `GET /admin/processing-tasks` | `exam_paper_code?,state?,cursor?,limit=20`（1—100） | 管理员统一列表，按created_at和task_id稳定分页 |
| `GET /admin/processing-tasks/{task_id}` | ID | state/stage/attempt、batch、复用关系、时间、issues和检查摘要 |
| `GET /admin/processing-tasks/{task_id}/stages/{stage}` | extract/normalize/reference/transcribe/align | 管理员鉴权、返回前验证产物哈希；缺失返回missing=true。reference路径不生成transcribe产物 |
| `GET /admin/processing-tasks/{task_id}/result` | `view=auto_draft/final`、`section?`、cursor/limit | 版本化结构、正式ID和src_id对应、来源、阶段产物摘要；未生成部分明确missing，不能回退另一任务样例 |
| `GET /admin/processing-tasks/{task_id}/diff` | 可选基准task_id | 自动初稿→本次修订的字段/关系差异及来源，不修改初稿 |
| `POST /admin/processing-tasks/{task_id}/checks` | `expected_result_hash` | 新检查ID、最低内容/模块三规则两个维度、规则版本及issues；这才执行新检查 |
| `POST /admin/processing-tasks/{task_id}/reviews` | `result_hash,scope,decision,items,evidence_refs,note` | 真实核对记录；scope=content/audio/annotations，decision=approved/changes_required；服务端记录登录操作者和时间 |
| `POST /admin/processing-tasks/{task_id}/corrections` | `expected_result_hash,reason,source_refs,changes[]` | 202新task_id、parent_task_id和修订草稿；changes为受限实体/字段/关系操作，不能执行任意JSON路径/SQL；改变文本/时间触发相应阶段重跑 |
| `POST /admin/processing-tasks/{task_id}/retries` | `expected_input_hash,reason,from_stage` | 202新task_id；原失败任务不抹除；只有上游指纹全匹配才能复用检查点 |
| `GET /admin/listening-papers/{exam_paper_id}/batches` | cursor/limit | 当前、历史、待审批次及任务引用；尚无正式paper的失败任务仍从任务接口查 |
| `POST /admin/listening-papers/{exam_paper_id}/current-batch` | `task_id,batch_id,check_id,result_hash,expected_current_batch_id`（首次null） | 检查/复核匹配后原子切换，返回current_batch_id及is_visible=false；并发基线不符409；重复确认同一当前批次只返回现状，不取消已有可见性 |

启动请求示意如下，尖括号项由T01盘点结果替换，不能直接当作已存在资源：

```json
{
  "exam_paper": {"exam_paper_code":"CET4_2025_06_1","exam_level":"CET4","exam_year":2025,"exam_month":6,"paper_set":1},
  "material_ids": ["<原卷ID>","<答案解析ID>","<音频ID>"],
  "document_mode":"text",
  "text_source":"reference",
  "reference_segments":[],
  "stop_after":"align",
  "expected_question_count":25,
  "expected_question_count_source":{"document":"<原卷storage_key>","sha256":"<64位实际哈希>","locator":"<人工核对页码和题号范围>"},
  "expected_question_ranges":[{"section":"<原卷题组>","start":1,"end":25}],
  "dictionary_snapshot_sha256":"6348030d2b5acb49e0cf036487f4ddd508428f33b0033e5cfb4261d40a986580",
  "profile_version":"M3-WIN64-1.1.0"
}
```

示例reference_segments为空表示先保存待补充任务，不会进入推理或自动转写。完整原文准备好后建立带来源句子的新任务。25是独立核对的本样例题量，不是全系统常数；题组范围示意必须替换为实际分组，不能只填整卷范围跳过题组覆盖检查。question_count_source须指向同任务已登记原件及有效locator。

reference_segments每行固定：segment_id、text、segment_type（body/question）、passage_key、可选speaker（来源M/W）、question_no、source_storage_key、source_sha256、source_pages、search_start_ms、search_end_ms。来源必须指向本任务答案/原文材料及真实哈希；正文不得带题号，提问按可信题量完整且不重复覆盖；ID唯一。搜索范围为正序、单句不超过30秒，不能直接作为最终时间。模型改写/漏句/新增文字报REFERENCE_TEXT_CHANGED；库内部缩写拆分仅可按原文顺序、完整文字归并回固定ID。

当前API接收已准备的reference_segments；PDF/OCR到经核对逐句输入的完整自动串联尚待完成和验收。固定样例原文由开发人员逐页核对准备；组件工具不替代完整管理员API→worker处理。

阶段结果契约统一包含 `schema_version,task_id,stage,input_hash,method_hash,artifact_hash,created_at,items,issues`。异常项为 `{issue_code,severity,stage,material_id,entity_type,src_id,locator,message,retryable,affected_refs}`，未知项用null，不伪造定位。正文保留规范化规则及源文字符映射；原解析另存原文字、文件页码/框坐标，摘要须记录转换版本。

任务创建允许可信题量及来源暂缺（两项均为null），此时仅保存待确认任务及材料，不能将其判为完整。试卷身份元数据和document_mode（text/scan）仍须有效；提供的题量和来源必须成对有效且与已登记原件一致。实体ID通过JSON返回十进制整数，task_id为UUID字符串；src_id仅是草稿引用，不能代替正式ID。

LLM返回限定 `question_src_id,skills[{skill_code,role,rationale,evidence_segment_src_ids,quote}],answer_evidence,candidate_errors,language_items,genre_candidate`。不接受模型提供正式主键、标准答案覆盖、生成时间戳或任意词典码；本地白名单解析并与完整输入对照，非预期字段拒绝。材料正文只当数据，不作为指令。每题或小组调用，完整篇章保留；输入过长时按题分配上下文，不静默截掉候选正文。

### 3.5 任务状态、恢复与阶段复用

任务state冻结为 `pending/running/failed/awaiting_confirmation/completed`，与批次pending/active/failed分开。`completed`表示既定处理、保存和规定复核完成，不等于已经切换、可见或整体验收PASS。自动链路得到候选后通常为awaiting_confirmation；缺材料、语义疑点或句级阈值未定同样待确认，并明确issue_code。

任务在数据库提交后才返回202；独立处理进程轮询并以 `FOR UPDATE SKIP LOCKED` 领取，持久lease_token。单音频处理并发1；心跳10秒、租约120秒，均记录配置。长外部调用期间也须独立续约。阶段写入须核验lease_token，失效worker不得回写。推理和HTTP请求不持有长数据库事务。

默认阶段为registered/preflight/extract/normalize/reference/align；保存align后，stop_after=align或请求缺省时释放租约，state=awaiting_confirmation、stage=align，记录ALIGNMENT_REVIEW_REQUIRED。此时不进入assemble/annotate/persist。本轮使用显式assemble/annotate_sample/annotate新任务，均在业务校验/入库前释放租约；不得使用completed。本轮之后的validate/persist/review/completed须另获授权；显式ASR路线以transcribe替代reference。每步产物原子写临时文件后改名、计算哈希再登记。进程中断保留最后成功检查点；租约过期由恢复巡检标记failed/WORKER_LOST，管理员显式retry生成新任务，不无限重试或重复收费。API重启不丢任务；worker可重新领取pending。数据库故障时503或受控失败，不能回退为静态演示数据。

规范化缓存覆盖原音哈希及解码/规范化方法；可选ASR缓存另覆盖转写模型revision、计算精度、VAD/切块参数。原文模式不依赖ASR缓存；对齐缓存覆盖规范化音频及文字来源模式、原件/可靠原文及分句哈希、固定句子ID、粗搜索范围和对齐实现版本；标注缓存再覆盖题目、答案解析来源、词典、提示词、请求/响应模型及schema版本。各阶段同时记录profile_version、实际解释器版本和相应环境锁哈希；由1.0.0转1.1.0时不得覆盖旧任务配置或默认将旧阶段产物当新基线通过。需要跨profile复用时明确来源、内容和兼容校验证据；未证明可复用则重新执行。文本与扫描两条文档路径必须实际各跑，允许明确复用同哈希音频有效产物并保留来源；不能复用文本提取结果冒充OCR执行。

### 3.6 幂等、草稿写入、媒体与激活事务

区分 `input_fingerprint`（原件哈希、试卷元数据、可信题量来源、全部方法版本）和 `result_fingerprint`（再含规范化业务内容、全部证据/关系及人工修订）。采用UTF-8规范JSON、键排序、明确数组排序规则、禁NaN、完整SHA-256；排除任务UUID/随机临时ID/运行时间，引用按稳定实体键归一化。不同词典、提示词、模型映射、校正结果必须得到不同指纹。

每次用户重跑保留独立task；相同有效结果复用已存在batch，不重写业务行、不恢复历史为当前、不清除已确认可见性。未通过检查的草稿不能冒充“有效幂等命中”。并发唯一冲突重查完整指纹后绑定结果，不能盲删既有批次。

草稿业务事务只创建非当前pending批次，不改 `ExamPaper.playback_audio_id`、旧批次、旧检查或可见性。不完整产物保存在任务草稿，满足业务非空约束后才构建关系行；业务写入失败回滚后，用独立短事务保存任务failed及失败阶段，防止回滚带走失败记录。

媒体写入保留所有权：`created_by_attempt`、目标路径、哈希、`needs_write`、是否已引用、临时路径。使用独立版本目录和不可覆盖发布；已存在同哈希文件只复用，不归本次清理所有。文件发布先完成并核验，数据库随后引用；提交失败时核查有效引用后仅清理本次新建文件。进程崩溃遗留无引用文件由清单对账报告后受控清理，不删除无法确认所有权的文件。Windows路径检查覆盖大小写、junction和跨盘，不能用字符串前缀代替路径包含关系。

激活在单个数据库事务中锁定试卷：校验期望旧批次、目标task/batch/result_hash、目标批次音频哈希与可解码报告、最新最低内容检查和模块三检查，以及对应内容/音频/标注复核。先撤旧current，再设新active/current，更新整套音频绑定、新可见记录false并追加激活审计，同次提交。任一环节失败整笔回滚。旧active历史保留，查询只选current。重复激活当前版本只返回现状，不能再次隐藏；两个不同目标竞争只能一个成功，另一个409。

读取请求一次确定并沿用同一batch_id，题目、片段、证据、检查、可见性和音频都以它为依据；音频取 `batch.audio_id`，不得先取旧batch又从已被并发切换的paper指针拿新音频。`paper.playback_audio_id`继续作为激活时同步更新的兼容表示。读事务使用一致快照或同等可证明的一致读取，T12/T13须增加“切换同时读整卷/音频”的并发断言。取消之后新开始的学生请求必须重新检查访问条件。

既有模块二CLI继续保持原默认行为作为兼容入口；拆分公共逻辑后明确其 `legacy` 检查profile。模块三不得经该CLI自动激活绕过检查。历史模块二批次不强制凭空补技能，但无可信题量来源的旧记录按0004规则保持失效；模块三新批次必须满足新规则才能激活。

### 3.7 异常及兼容回退表

| 情况 | 行为与可定位信息 | 可继续的方式 |
| --- | --- | --- |
| 缺答案、解析、音频或可信题量来源 | awaiting_confirmation；保存已提取草稿，列出材料/题号和缺项 | 补登记材料后新修订任务；禁止模型猜答案/占位解析 |
| OCR/来源文字冲突、无法对齐（或可选ASR识别冲突） | 原稿保留，异常定位页框/句子/原音时间；无效边界不能成为正式证据 | 对受影响阶段重跑或有依据人工修订，再复核 |
| 缺reference原文或模型改变原文 | REFERENCE_TEXT_REQUIRED待补充，或REFERENCE_TEXT_CHANGED待复核；不得回退ASR | 补原文或修正来源后新任务，不接受模型文字替换 |
| 模型/FFmpeg/DLL/设备不可用 | failed/preflight或对应阶段；记录组件实际版本和路径 | 修复/修订profile后重跑，旧可见批次不受影响 |
| DeepSeek429、5xx、网络超时 | 单次绝对截止120秒（不能仅设httpx分阶段超时）、额外最多2次；采用有上限的指数退避并尊重Retry-After，超过任务预算/等待上限则待确认；每次attempt和用量可追溯 | 超限待确认或failed；不重复完整本地推理；超时收费状态标未知，不捏造0费用 |
| DeepSeek401/403或预算耗尽 | 不自动重试；待确认配置/预算，不写密钥 | 配置解决后显式retry；本轮不实际调用 |
| 空JSON、finish_reason截断、无效词典/跨篇引用 | 保存原响应；在同一最多2次重试预算内修复请求；最终待确认 | 不使用未验证响应、不临时增设词典 |
| 写库/提交/文件发布失败 | failed，事务与媒体所有权对账；旧current、音频、检查和可见性均保留 | 从有效检查点恢复，保留原失败记录 |
| 正文、题干、边界/词典被修订 | 新task/result_hash；失效受影响对齐/证据/标注/复核；不得改当前数据 | 重新检查复核后再确认切换 |
| 数据库不可用/并发基线冲突 | API503/409；不静态兜底、不覆盖他人确认 | 恢复数据库或重新读取current后显式操作 |

## 4. 任务总表与实施顺序

优先级：P0为交付阻断项，P1为P0闭环后的完善项。本期下列任务均为P0，不以扩展关系合理为空省略存储和核心校验。顺序表示依赖拓扑，不承诺工期或人员分工。

| 编号 | 任务 | 对应需求 | 优先级 | 前置依赖 | 实施顺序 |
| --- | --- | --- | --- | --- | --- |
| T01 | 基线、材料、词典与字段冻结 | M3-01/06/12 | P0 | 无 | 1 |
| T02 | 三环境统一Python3.13.16、py313适配及模型/原生库预检 | M3-04/09/12 | P0 | T01 | 2 |
| T03 | 九张业务表及辅助存储增量迁移 | M3-05/06/08/10 | P0 | T01 | 3 |
| T04 | 受控材料登记、来源及权限 | M3-01/02/09 | P0 | T03 | 4 |
| T05 | 任务API、独立worker和阶段恢复 | M3-02/03/08 | P0 | T02/T03/T04 | 5 |
| T06 | 文本PDF和扫描提取 | M3-04 | P0 | T01/T02/T05 | 6 |
| T07 | 原文核对/固定分句、音频规范化与逐句对齐（可选ASR） | M3-04/09/12 | P0 | T02/T05 | 6 |
| T08 | 题目组装、可信完整性和原卷映射 | M3-04/07 | P0 | T06/T07 | 7 |
| T09 | DeepSeek结构化候选、技能证据和版本 | M3-05/10 | P0 | T03/T08；真实调用还需U01 | 8 |
| T10 | 分层检查、修正和复核记录 | M3-01/05/07/10 | P0 | T08/T09/T11；精度判定需U02 | 10（草稿规则可提前） |
| T11 | 草稿入库、ID、指纹和媒体事务保护 | M3-03/06/08/09 | P0 | T03/T05/T08/T09 | 9 |
| T12 | 管理员确认切换和模块二接口接入 | M3-07/08/11 | P0 | T10/T11 | 11 |
| T13 | 隔离数据库/HTTP自动验收和回归 | M3-01—M3-12的技术项 | P0 | T04—T12 | 12（各卡同步积累） |
| T14 | 真实内容、双路径质量报告及交付回填 | M3-10/12 | P0 | T01—T13、U01—U05满足所需条件 | 13 |

T06/T07可在同一开发阶段独立推进；这里不表示本轮已执行并行开发。T11可先基于受控合成结构实现事务行为，但真实链路交付必须等待T09和T14。各卡按证据分报：原文组件运行和部分控制逻辑已有PASS，完整API双路径链路、人工300ms精度及下游标注/入库验收仍待完成；85项自动测试不代表T01—T14全部通过。

## 5. 逐张任务卡

每卡中的入口“新增”均为建议落点。验收引用第6章场景及第7章命令；测试脚本/测试文件未实现前相应命令不可执行，应回填BLOCKED，不能填写预测测试数。

### T01｜冻结基线、输入和逐字段映射

- **目标／需求**：把M3-01/06/12的原件、可信题量、词典和字段变成可追溯输入。
- **输入与入口**：统一技术版本V1.2、需求V1.8、profile `M3-WIN64-1.1.0`、16表JSON、`验收资料/materials`、固定提交模型；[field-mapping.md](field-mapping.md)。
- **GitHub参考**：项目固定提交的模型、迁移、导入器（§1.4）；G01—G08只用于技术依据，不替代原卷来源。
- **实施步骤**：① 开工重核develop和AGENTS，记录提交/未提交差异；② 重算原件及schema哈希，盘点文本/扫描条件，区分派生扫描和实物扫描；③ 从原卷登记可信题量、各题组范围、locator及确认记录；④ 固定词典行、目录/叶子统计和旧码映射；⑤ 逐字段核对类型、非空、枚举、来源、复核承载及后置理由。
- **交付物**：基线清单、材料manifest、词典快照、逐字段差异确认稿、输入场景fixture说明。
- **可复现验收**：A01/A02/A09/A20/A34；重新计算哈希应与manifest一致；每个16表字段有唯一处置且无“全部已对齐”空泛结论；扫描缺失和题量来源缺失应明确BLOCKED。
- **失败处理**：哈希/来源冲突暂停对应材料；保留原件和差异，不自动覆盖。U03/U05仅阻塞依赖样例的验收，不阻止无关设计。

### T02｜统一Python3.13.16并验证三个隔离环境

- **目标／需求**：建立M3-04/09/12实际可运行环境，消除“解析成功等于运行成功”的误判。
- **输入与入口**：最新三份带哈希锁（API已按3.13.16重解析）、模型/FFmpeg/NLTK清单、profile `M3-WIN64-1.1.0`；现有 `backend/pyproject.toml` 的py314声明；新增环境诊断命令 `app.module3.diagnostics`。
- **GitHub参考**：G01/G02/G03/G05/G07/G08的固定源码及许可证。
- **实施步骤**：① 先盘点既有解释器/设备，不覆盖全局环境；② 核验Python3.13.16常规GIL/x64后创建API/ASR/OCR三个独立环境，各自按最新锁安装和pip check；③ 开发时将Ruff目标改为py313，更新版本说明及启动/测试/部署命令，验证API与公共代码在3.13.16可解析、可导入；④ 核验模型本地文件哈希；⑤ 新进程注册并保留DLL目录句柄，分别验证TorchCodec、PyAV、CT2、torch设备、WhisperX和Paddle；⑥ 在新API环境重跑模块一/二回归并保存实际DLL路径、驱动、decode输出及小样结果；⑦ 记录许可证材料和不兼容项。
- **交付物**：无密钥环境样例、py313配置适配、诊断工具、三环境路径/版本报告、新API环境模块一/二回归记录、组件烟测证据及许可清单。
- **可复现验收**：A13/A14/A35；三个python.exe均为3.13.16/x64/常规GIL，路径及依赖分别可查；§7.2诊断能用真实小样输出有限float波形、转写/对齐和OCR结果；Ruff目标为py313且模块一/二在新环境实际回归。仅import成功、39包解析成功或旧3.14环境通过均不能代替新环境PASS。冻结包安装失败不得替换为latest后声称原基线通过。
- **失败处理**：组件级FAIL或缺资源BLOCKED；提出精确版本/profile修订并重新锁定/实测；不安装未经需要的完整CUDA工具链，不删除本机已有FFmpeg。

### T03｜增量建设业务与辅助表

- **目标／需求**：实现M3-05/06/08/10的存储与批次归属。
- **输入与入口**：T01映射；既有 `db/models_listening.py`、`db/models.py`、Alembic0001—0004；新增 `models_annotations.py/models_processing.py`。
- **GitHub参考**：G06事务与会话；项目现有模型/0004迁移。
- **实施步骤**：① Alembic接现有head生成新revision；② 建九张业务表及§3.3辅助表；③ 增补现有表必要字段/索引/复合FK，旧行可空字段分阶段回填，不能虚构审核；④ 固定词典和显示码/旧码映射；⑤ 在空库和模块二旧库副本迁移，检查账号、角色、旧题库及审计记录；⑥ 文档明确回退和备份恢复步骤。
- **交付物**：迁移、模型、字段/约束说明、词典导入服务、迁移前后对账记录。
- **可复现验收**：A20/A21/A29/A35；空库upgrade head成功；旧库升级数据身份/数量/哈希保持，0004无来源旧基准不能沿用；跨批次外键及非法relation_kind被拒；重复词典导入不新增重复定义。
- **失败处理**：迁移事务回滚或从隔离备份恢复；保存失败revision。对有模块三数据的库不承诺无损downgrade，回退应用前需先验证schema兼容和备份。

### T04｜受控材料登记及权限

- **目标／需求**：实现M3-01/02/09的材料入口和可信来源。
- **输入与入口**：T01原件manifest；既有 `api/deps.py::require_admin`、`core/config.py`；新增材料API和来源服务。
- **GitHub参考**：项目固定提交鉴权与配置；G08媒体身份清单思路；不复制外部完整管理框架。
- **实施步骤**：① 冻结相对storage_key及source_kind；② 服务端解析路径、阻止越界/重解析点绕过、核对实际类型/大小/哈希；③ 登记派生链和locator，验证同套材料绑定及题量来源；④ 实现幂等登记和冲突返回；⑤ 所有管理员统一访问，无学生原件下载入口。
- **交付物**：材料登记/查询接口、Pydantic契约、受控目录说明、路径与鉴权测试。
- **可复现验收**：A01/A02/A03/A04；未登录401，学生403，另一管理员成功；相同原件幂等；`../`、绝对/UNC路径、junction越界、伪后缀/错误哈希和同路径变更均拒绝且无外部读取；成功响应不泄露机器绝对路径。
- **失败处理**：拒绝请求并定位材料，不修改原件；任务执行前原件已变更时标记SOURCE_CHANGED，不能继续使用旧sha256。

### T05｜任务API、独立worker和恢复

- **目标／需求**：实现M3-02/03/08的可追踪异步任务。
- **输入与入口**：§3.4/3.5契约、T03/04；新增 `admin_processing.py`、`module3/worker.py`、`processing/tasks.py`。
- **GitHub参考**：G06短事务；项目统一响应/require_admin。重任务不放FastAPI请求或仅内存BackgroundTasks中。
- **实施步骤**：① 任务先提交再返回202；② worker凭lease领取并落stage/heartbeat；③ 固定解释器启动OCR子进程，路径参数数组传递；④ 原子保存产物与阶段检查点；⑤ 实现状态/结果/异常/历史列表；⑥ worker失联标failed，显式retry产生新task；⑦ 长请求期间续约、失效worker回写拒绝。
- **交付物**：任务路由、worker命令、运行/恢复说明、结构化错误模型及状态测试。
- **可复现验收**：A05/A06/A07/A08/A25；测试中阻塞worker时启动API仍返回202且不执行识别；重启API任务可查；kill worker后按租约规则失败且初稿保留；两个worker领取同任务仅一个有效；旧租约无法提交结果。
- **失败处理**：数据库创建失败503且无假task；进程失败不伪装completed；只从输入/方法hash相符的检查点恢复。

### T06｜文本与扫描文档自动提取

- **目标／需求**：实现M3-04两条真实文档路径。
- **输入与入口**：同套原卷与答案解析、文本/扫描manifest；新增OCR进程、`adapters/pdf_text.py/pdf_scan.py`及固定版式解析器。
- **GitHub参考**：G03 `PaddleOCR.predict`、G04文字/位置、G05页面渲染。
- **实施步骤**：① 逐页检查文本层和版式，保留原输出；② 文本路径保存页码和点坐标；③ 扫描路径实际渲染/读取图片并OCR，显式v5模型；④ 固定坐标系统和阅读顺序，解析题号、选项及解析来源；⑤ 空白页、乱码、低置信/跨栏冲突定位；⑥ 两路分别保存来源、初稿和质量统计，不能用工作簿答案覆盖初稿。
- **交付物**：提取适配器、页级产物、版式规则、两类输入fixture和异常报告。
- **可复现验收**：A11/A12/A15/A34；同套文本与扫描分别由API创建任务并实际进入相应提取器；页/坐标回查有效；无文本层不返回假成功；解析缺失待确认，派生扫描记录来源、DPI和压缩/旋转条件。
- **失败处理**：保留页级成功产物和失败位置，针对页重跑；复杂版式/倾斜超出当前profile时PARTIAL或BLOCKED，不自动引入未冻结大模型。

### T07｜原文分句、句级强制对齐与精度核听

- **目标／需求**：M3-04/09/12；已有完整答案原文直接对齐，默认不转写，缺原文不静默转ASR。
- **入口**：schemas_processing.ReferenceSegment/TaskRequest；module3/audio.py、reference.py、reference_review.py、diagnostics.py；worker及stages/reference接口。
- **步骤**：① 文本提取/OCR后逐页核对正文及提问，保留识别稿与校正依据；② 固定来源ID、分句、正文/提问类型、题号/说话标签及原件哈希/页码；③ 规范化原音并保留PTS/偏移；④ 定位逐句搜索范围，来源粗时间和方法另记；⑤ CPU强制对齐，按固定原文ID归并内部缩写拆分，不改字、不复制搜索边界；⑥ 保存reference/align检查点、逐句表、字幕及30个正文句空白核听表，停在await确认；⑦ 实际核听起止分别≤300ms，异常修正后重对齐，用户确认后才继续T08/T09。
- **ASR分支**：只有明确选择无原文模式才执行audio.transcribe，保留初稿及核对。默认原文路径的diagnostics --profile align不要求GPU或large-v3；依赖环境及固定CPU对齐模型不变。
- **当前证据**：140个正文句＋25个提问句已实跑，165句原文及ID保持，对齐约150秒；新ASR/LLM调用0。旧ASR词时间仅作为本样例的搜索线索；文字来自原图，粗范围不是正式边界。完整自动原文准备/API编排和300ms整套核听仍未验收。
- **验收**：A13—A15/A34及A37—A41；0≤start_ms<end_ms≤duration_ms，原文/题号/归属不变；缺句/改写/无效边界不得PASS；无人工参考不记精度通过。
- **失败处理**：原件/方法变更阻止继续；缺原文待补充、改字/分句异常待复核，不猜时间，不自动转写；修改原文/搜索范围后失效相应对齐和证据/复核。

V1.4实现修正：保留WhisperX加载固定英文模型，使用冻结TorchAudio CTC解码；标点不作为任意语音，空白不并入首末字符，前后文守卫吸收搜索范围中的邻句声音。字符映射保持来源偏移。低声学分数（0.60，仅调试启发式）或边界贴搜索窗口≤50ms时，按邻句位置有界扩窗重试一次，最大30秒；保存requested/effective范围、每次分数及方法。未消除的低分/贴边、明显相邻冲突保留异常，不编造时间。调试先自动处理全量，只集中复核程序仍不能解决的异常，不再要求用户完成此前27条抽样待办；正式300ms精度结论仍需独立参考。组件/锁/模型revision及业务需求V1.8不变。

### T08｜题目组装、完整性与原卷映射

- **目标／需求**：实现M3-04/07，保持模块二已修复的题量与映射语义。
- **输入与入口**：T06页级提取、T07正文/提问片段、可信题量；现有 `validate_payload`、`build_payload`、`repositories/listening.py::_paper_correct_option`；新增组装服务。
- **GitHub参考**：项目固定导入/展示代码（§1.4），G04仅作来源位置依据。
- **实施步骤**：① 按题号、篇章顺序和真实录音提问建立题干；② 核对A—D选项和来源答案/原始解析；③ 生成本套presentation和明确mapping_source，样例用经核对恒等映射；④ 可信题量、题组范围、题号/映射数量独立检查；⑤ 统一临时引用，不采用历史主键；⑥ 保留摘要解析的原始文本及变换记录。
- **交付物**：兼容七段结构的自动草稿、选项/题号映射表、解析来源及缺项列表。
- **可复现验收**：A09/A10/A15/A22/A23；可信25题而结果24题失败；无可信基准不能自行设24；A→Z/重复值/空展示选项均拒；A/B交换后展示答案随映射变化、底层答案不改；不能把question片段当正文。
- **失败处理**：缺题、缺解析、未知映射保存草稿待确认，不写“可用/已通过”；修正后重新检查，不能把导入成功当完整性通过。

### T09｜DeepSeek候选及技能/证据关系

- **目标／需求**：实现M3-05/10的自动候选和可回查依据。
- **输入与入口**：题目、来源答案解析、可靠正文及片段ID、词典快照；新增 `adapters/deepseek.py`、提示词文件、标注契约。
- **GitHub参考**：G02的片段来源、项目批次模型；API参数以§2官方DeepSeek资料为准，不引用无关开源项目作为服务保证。
- **实施步骤**：① 固定提示词/schema/方法哈希，使用httpx0.28.1；② 按冻结endpoint/deepseek-flash参数调用，记录实际响应model和用量；③ 有限重试和预算控制；④ 白名单解析技能/证据候选，验证真实词典、正文引用、quote及同篇同批次；⑤ 从有效句子取时间，分别生成QUESTION_SKILL/SKILL_EVIDENCE和ANSWER_EVIDENCE；⑥ 有依据才建辅助技能/候选错因/语言点/体裁；⑦ 原始响应和初稿只追加保存。
- **交付物**：客户端、提示词、schema、调用账本、候选结构、关系装配器和响应异常fixture。
- **可复现验收**：A16/A17/A18/A19/A33；真实调用至少覆盖完整样例必交题目并可追溯；429/超时/截断/空JSON/不存在skill_code分别触发既定行为；模型伪造时间、答案覆盖和跨篇证据不得入正式结果；无依据扩展为空不能误报必交缺失。
- **失败处理**：缺密钥/预算BLOCKED，不实际收费试跑；不猜标签、不假造用量或声称服务snapshot固定。Mock只证明协议和重试行为，不替代真实标注及语义复核。

### T10｜分层检查、人工修正与复核追溯

- **目标／需求**：实现M3-01/05/07/10，使“结构合法”和“内容正确”分别有证据。
- **输入与入口**：T08/T09草稿、原页/原音、U02口径；既有 `content_check.evaluate/run_check`；新增模块三规则、corrections/reviews/checks接口。
- **GitHub参考**：项目最低检查及可见性服务；G02对齐回退限制。
- **实施步骤**：① 最低内容检查复用并补候选batch.audio_id、实际文件身份/解码；② 模块三规则覆盖解析来源、句级范围、词典、关系、连续正文证据和覆盖率；③ 实现受限校正操作及diff，新task保留parent和初稿；④ 正文/题干/时间/标注修改按依赖失效检查和复核；⑤ 真实人员提交逐题/整音频/标注复核记录，绑定result_hash；⑥ 已有检查读取接口保持只读，新增POST显式重检。
- **交付物**：规则清单、可定位issues、校正记录、复核接口和对象版本检查。
- **可复现验收**：A09/A10/A18/A19/A32/A33；每题主要技能和答案证据齐全，每条技能证据有效；修改正文/边界后旧review不能用于激活；自动初稿不能改成修正版；无真实复核记录不能仅改review_status通过。
- **失败处理**：问题明确归类规则FAIL、待人工BLOCKED或合理扩展空缺；未核听/未复核不签PASS；修订后重新执行受影响规则和复核。

### T11｜草稿入库、统一ID、幂等和媒体保护

- **目标／需求**：实现M3-03/06/08/09，失败不影响旧可见内容。
- **输入与入口**：T03模型、自动草稿、方法指纹、音频；拆分 `import_module2.py::run_import/manifest_hash/_resolve_audio_target` 到公共服务。
- **GitHub参考**：G06会话事务；项目已合并媒体所有权/冲突回归测试。
- **实施步骤**：① 分离validate/stage/persist/activate，模块三默认只stage；② 完整result_fingerprint归一化并数据库唯一约束；③ 分阶段统一src→正式ID映射，使用batch复合FK和服务校验；④ 合法待审结果落pending，不碰旧paper音频；⑤ 安全暂存/发布、清理所有权账本和无引用遗留对账；⑥ 独立事务记录失败；⑦ 相同有效结果复用batch但新增任务记录，不重置可见性。
- **交付物**：公共入库服务、媒体发布/回收服务、指纹规范、失败和幂等测试。
- **可复现验收**：A20/A21/A24/A25/A28/A30；同输入/方法/结果重复不新增题目、不改变current/visible；变词典/提示词/校正得到新版本；注入写库、文件发布、提交故障，旧表快照/文件哈希/HTTP可读性不变；复用B文件不得被清理。
- **失败处理**：回滚本次业务写入，保留失败task和草稿证据；有引用或来源不明文件保留并报待对账，不盲删同名或哈希后缀文件。

### T12｜显式确认当前版本及既有接口联通

- **目标／需求**：实现M3-07/08/11，不混用不同批次内容。
- **输入与入口**：目标task/batch/check/result_hash、完整复核记录；新增current-batch接口，复用 `repositories/listening.py`、`services/visibility.py`、既有题库路由。
- **GitHub参考**：G06事务；项目当前批次唯一索引、答案映射、Range和权限代码。
- **实施步骤**：① 锁定试卷并核对期望current及目标全部门槛；② 同事务切换current、绑定音频、设置新批次隐藏、保存审计；③ 保留旧历史及幂等确认；④ 当前详情/配套/媒体从同一批次一致读；⑤ 既有visibility再执行confirm/cancel；⑥ 以学生允许字段白名单序列化，不带正文/解析/答案/标注理由。
- **交付物**：激活服务、兼容API说明、并发/越权/隐藏回归证据。
- **可复现验收**：A03/A23/A26/A27/A31/A36；确认前旧current和音频不变，确认后新current且默认隐藏；之后独立confirm才可读；cancel后新的学生列表/详情/媒体均受阻；两个不同确认只有一个成功；重复确认当前版本不清空已有可见性。
- **失败处理**：409返回并发/版本不匹配，旧状态不变；激活中途失败回滚；不得用visibility确认暗中代替版本切换。

### T13｜隔离技术验收与模块一/二回归

- **目标／需求**：覆盖M3-01—M3-12的技术行为及R01—R21。
- **输入与入口**：第6章矩阵；现有四份测试及conftest；新增 `backend/tests/module3/`、运行夹具与HTTP验收工具。
- **GitHub参考**：项目模块二真实PostgreSQL/HTTP/媒体失败测试，G06事务并发行为。
- **实施步骤**：① 测试库和媒体副本双隔离，禁止收集阶段提前绑定开发库；② 新增各矩阵场景的明确断言与证据输出；③ 技术测试允许可控响应fixture但明确标Mock；④ 单独启动真实API/worker走HTTP验收，验证可解码音频和范围请求；⑤ 在Python3.13.16 API环境完整回归既有认证/角色、数据库迁移、题库/媒体与TestClient，旧3.14运行记录另列为历史；⑥ 记录提交、三个解释器路径/版本、profile、锁哈希、命令、退出码、用例数和产物哈希。
- **交付物**：可复现测试/fixture、HTTP验收工具、日志、隔离说明及矩阵结果。
- **可复现验收**：A01—A41技术子项；§7实际运行均按退出码和断言回填；404/403/401、409、503、206/416等精确断言；测试失败不能靠降低检查门槛转绿。Mock结果与真实处理分报。
- **失败处理**：定位失败用例、保留隔离库/文件证据；防护无法证明隔离时BLOCKED并停止测试，不清空工作数据库。技术PASS不能覆盖U02及真实人员核查。

### T14｜真实内容、双路径质量与交付报告

- **目标／需求**：完成M3-10/12最终闭环。
- **输入与入口**：同套文本与扫描任务、自动初稿/最终结果、真实核对/核听/标注复核记录；新增 `docs/acceptance/module-3/`报告和证据索引。
- **GitHub参考**：项目既有内容核对空模板仅作为结构参考；G01—G08不提供本卷质量结论。
- **实施步骤**：① 正式评测前固定关键字段分母、关系覆盖规则，并按已确认的300ms句级阈值执行；② 真实人员逐题核对、整套核听、判断技能及证据语义；③ 分别统计两条文档路径自动初稿与最终正确率/覆盖率；④ 统计人工修正题数、字段/标注修改与耗时；⑤ 汇总HTTP、数据库、模型调用和媒体证据；⑥ 用§8模板回填全部卡和矩阵，注明未覆盖条件。
- **交付物**：逐题记录、整套核听表、标注复核记录、初稿/最终质量报告、总体验收和交付说明。
- **可复现验收**：A11/A12/A31/A32/A33/A34；关键字段及必交关系最终完整正确，疑点关闭，数据库/接口返回来自本次自动结果，音频与原件哈希一致；无真实记录或缺一条文档路径不得整体PASS。
- **失败处理**：明确PARTIAL/FAIL/BLOCKED及受影响题目/关系；不设未经约定的初稿最低正确率或人工修正比例，不把人工逐题重录当自动链路通过。

## 6. 验收矩阵

### 6.1 统一判定

| 结论 | 判定规则 |
| --- | --- |
| PASS | 对应标准实际执行且全部满足，证据可定位；规定的真实内容核查也已完成 |
| PARTIAL | 已执行范围内部分满足，但仍有缺项；列出通过/未通过的具体子项；不能代表整体验收通过 |
| FAIL | 已执行且观察到违反标准的结果，须附输入、预期、实际及复现证据 |
| BLOCKED | 未实施、未执行、资源/材料/阈值/真实复核等前提不足，无法判定；不能记为PASS或伪装成运行FAIL |

每一行分别记录技术结论和内容/人工结论（适用时）；总体PASS要求所有必交场景及内容证据满足。合理扩展空缺在允许场景单列，不作为必交缺失。当前结论以原文实跑和85项隔离测试的具体断言为准；A01—A41未逐项完成完整真实验收，不统一标PASS或“全部未执行”。内容/精度仍待核听，下游真实标注及整套入库链路保持BLOCKED。

### 6.2 输入、预期、追溯

| 场景 | 输入与操作（按证据分别回填） | 可复现预期／关键证据 | 需求／任务／原回归 |
| --- | --- | --- | --- |
| A01 | 登记同套原卷/答案/音频；重复登记 | 服务端重算哈希一致；重复返回同材料身份；manifest有locator；数据库记录可查 | M3-01；T01/T04 |
| A02 | `../`、UNC、绝对路径、junction越界、伪后缀/错哈希；任务前改源文件 | 请求被拒且无越界读取；SOURCE_CHANGED可定位；旧原件及绑定不变 | M3-01/09；T04；R07 |
| A03 | 无token、过期token、student、另一admin调用材料/任务/检查/复核/激活 | 401先于权限检查；学生403；另一管理员合法管理；无原件下载旁路 | M3-02/11；T04/T05/T12；R12 |
| A04 | 缺音频/答案/解析、材料套别或题量来源冲突 | 待确认及明确缺项，或冲突409；不猜答案，不标completed | M3-01/02；T04/T05；R11 |
| A05 | 阻塞worker后管理员创建任务，再启动worker | POST202先返回持久task，worker独立执行；查询state/stage与实际一致 | M3-02/03；T05；R14 |
| A06 | running时kill worker，租约过期，再retry | 原task保留failed/WORKER_LOST及检查点；retry产生新task并只复用相符产物 | M3-03；T05；R10 |
| A07 | 两worker同时领取同task；旧lease回写 | 单有效领取，无重复业务提交；旧lease写回被拒，有审计 | M3-03/08；T05 |
| A08 | 创建/查询/持久化时断开数据库 | API503或阶段失败可解释；无静态假数据、无completed假成功；恢复后可追踪 | M3-03/11；T05/T11；R12 |
| A09 | 无可信题量，删最后题及映射仅剩24 | expected_count_missing；不能将24写为基准，不开放 | M3-01/07；T08/T10；R01 |
| A10 | 原卷可信25题，结果24；题组范围不全/重复题序 | 缺题/覆盖异常定位，最低检查不通过、不可见且不得整套PASS | M3-01/07；T08/T10；R02 |
| A11 | 文本PDF从管理员API完整启动 | 实际文本提取→核对原文/分句→强制对齐→用户确认→组装/标注→待审入库；保存独立初稿和字段质量，非工作簿转存 | M3-04/12；T06/T13/T14；R14/R15 |
| A12 | 同套扫描PDF或图片另启任务 | 实际PaddleOCR；保留页图/框/置信度和扫描条件；音频缓存可明确复用，文本提取产物不能替代OCR | M3-04/12；T06/T13/T14；R15 |
| A13 | 新环境、错误解释器、缺/错DLL和模型hash；原文模式无GPU、ASR模式GPU不可用 | 三环境必须3.13.16/x64/常规GIL；不符时安装/处理预检明确失败或阻塞；不偷用工具环境3.14、全局FFmpeg/latest模型；原文CPU对齐不要求GPU，ASR不可静默降级后冒充原GPU方法 | M3-04；T02/T07 |
| A14 | 真实原音规范化、分块后对齐；损坏/无效音频 | 有限float32/16k/mono，绝对ms和原音偏移正确；损坏不可解码阻止检查与开放 | M3-04/09；T02/T07/T10 |
| A15 | 空文本页/乱码/低清扫描、录音提问、WhisperX空字符/回退 | 路由和异常定位真实；body/question区分；回退/插值边界不可直接算成功，不平均切割 | M3-04；T06/T07/T08 |
| A16 | 正常DeepSeek真实候选，固定词典与模型方法 | 请求/原响应/用量可追溯；技能码映射真实ID；每题主要技能/技能证据/答案证据实际保存 | M3-05；T09；R11 |
| A17 | Mock429/5xx/超时/401/空内容/截断/超预算 | 每次attempt可查，最多额外2次；鉴权/预算不盲重试；未知消耗如实记录；不足不completed | M3-03/05；T09；R11 |
| A18 | 非法技能码、跨篇/跨批次/提问片段证据、虚构quote或时间 | 明确拒绝/待确认，错误定位关系及引用；无非法正式FK或伪时间 | M3-05/10；T09/T10；R09/R11 |
| A19 | 缺主要技能、技能无证据、缺答案证据；扩展项无依据为空 | 必交缺项阻止验收/激活；合法扩展空缺单列，不能强编候选错因 | M3-05/10；T09/T10；R09 |
| A20 | 七段＋新增证据关系临时ID，重复/悬空src | 统一映射生成正式ID，合法数据可回查；重复/悬空拒绝，整体不留半套 | M3-06；T03/T11 |
| A21 | 同code跨batch、同词典重复导入、跨batch FK及错误owner | 合法版本并存、不全局冲突；词典不重复；非法归属/owner失败 | M3-05/06；T03/T11 |
| A22 | A→Z、重复映射值、缺项或映射后选项空 | 明确检查失败，不能确认可见，定位题号 | M3-07；T08/T10；R03 |
| A23 | A/B合法交换，比较管理员和学生响应 | 展示文字/展示答案同步；correct_option_base不变；学生两种答案均不返回 | M3-07/11；T08/T12；R04 |
| A24 | 同原件/方法/有效结果重复；改词典/提示词/模型映射/校正重跑 | 前者新增task但复用batch、保留可见；后者指纹不同且新批次不自动current | M3-08；T11；R08 |
| A25 | 尚未完整入库即失败；草稿待审；重启服务后查询 | 无batch也能查失败task，草稿/异常/初稿持久；不混入学生当前内容 | M3-03/08；T05/T11；R10 |
| A26 | 新批次检查和复核齐备但未确认，再执行current-batch | 确认前旧current/音频/可见不变；确认后整体切换、默认隐藏并记操作人时间 | M3-08/11；T12；R16 |
| A27 | 新批次切换后confirm可见、cancel、再重启 | confirm/cancel持久；cancel无需检查通过；新的学生列表/详情/媒体不可访问该卷 | M3-08/11；T12；R10/R14 |
| A28 | 已有音频A，写B时注入中途写库/提交/文件发布失败 | 数据库旧快照、音频哈希/路径、可见性和HTTP旧流均不变；只清本次所有文件 | M3-09；T11；R05 |
| A29 | 模块二旧库副本upgrade；旧记录无可信题量来源 | 账号/角色/历史题库/审计不损坏；缺来源不沿用旧检查开放；补核后重检确认 | M3-06；T03；R13 |
| A30 | 复用既有带hash后缀版本B后提交失败；同audio_code变hash/路径/时长 | 不删已有B；身份冲突明确拒绝，无错误绑定或不可追溯文件 | M3-09；T11；R06/R07 |
| A31 | API触发真实处理，检查/复核/确认后读取同套整卷、配套和媒体 | PostgreSQL行和HTTP内容与task/batch匹配；全流200、合法Range206、越界416；下载流hash等于原音且固定解码器可解码；cancel后学生请求404 | M3-11/12；T12/T13/T14；R14 |
| A32 | 正文/题干/时间/标注人工修订，比较auto_draft和final | 初稿hash不变；校正前后、依据、操作者和时间可查；受影响检查/复核失效，新result_hash | M3-10/12；T10/T14；R09 |
| A33 | 逐题核对、整套核听、主要/辅助技能和证据语义复核 | 真实记录逐项存在、疑点闭环；初稿与最终指标独立；空模板和自动判定不能代替人工 | M3-05/10/12；T09/T10/T14 |
| A34 | 按已确认的起止分别≤300ms检查30正文句小样及正式整套 | 误差/覆盖分母与异常口径预先固定；缺真实人工参考或整套核听为BLOCKED；不以抽样代替整套；明确扫描生成和未覆盖条件 | M3-04/12；T01/T07/T14 |
| A35 | API/ASR/OCR均按3.13.16独立安装，Ruff目标适配py313后执行认证、迁移、题库、媒体及TestClient回归 | 三路径、profile和锁hash可查，模块一/二在新API环境实际通过；正确隔离库/媒体，无既有功能回退；解析记录/旧3.14测试不能替代，不预写通过数 | M3-06/11/12；T02/T03/T13 |
| A36 | 两管理员对不同目标同时确认、重放同一确认、检查后改结果 | 不同目标仅一个成功，另一409；重放当前确认不清可见性；旧check/review/result_hash失配拒绝 | M3-08/11；T10/T12 |
| A37 | 完整答案正文/提问走默认reference | ASR调用0；来源文字、ID、题号和页码保持，禁止识别或模型文字替换 | M3-04；T07；R17 |
| A38 | 缺原文或提供其他任务/不同哈希的来源 | REFERENCE_TEXT_REQUIRED待补充或来源冲突拒绝；不静默ASR | M3-01/03/04；T04/T07；R18 |
| A39 | 粗搜索范围、U.S./No.缩写、内部多段输出 | 实际对齐生成边界；归并回固定来源句，文字完整；无效边界不接受，不平均分配 | M3-04/09；T07；R19 |
| A40 | stop_after缺省/align到达对齐检查点 | await确认并释放租约；组装、DeepSeek、业务批次写入/切换/可见均不执行 | M3-03/04/08；T05/T07；R20 |
| A41 | 仅有合法时间但无人工参考，或原文/搜索范围变更 | 精度仍待核听；变更失效相应缓存、对齐及证据/复核；按已冻结300ms复验 | M3-04/10/12；T07/T10/T14；R21 |

## 7. 可复现执行约定（已实现入口与待完成验收分开）

### 7.1 环境和已有命令

以下命令不是本轮执行日志。工作目录统一为仓库 `backend/`，在已经确认的隔离测试环境中执行；凭据从受控环境提供，不在报告复制DATABASE_URL真实值。

```powershell
# 先固定并记录代码身份，工作区差异另存脱敏清单。
git rev-parse HEAD
git status --short

# 三个独立环境的解释器绝对路径由T02清单提供，版本均为3.13.16。
# 此为未来执行说明；本轮未运行下列环境命令。
foreach ($M3Python in @($ApiPython, $AsrPython, $OcrPython)) {
    & $M3Python -c 'import sys, sysconfig; assert sys.version_info[:3] == (3, 13, 16) and sys.maxsize > 2**32 and not sysconfig.get_config_var("Py_GIL_DISABLED"), sys.version; print(sys.executable, sys.version)'
    if ($LASTEXITCODE -ne 0) { throw '模块三解释器不符合3.13.16/x64/常规GIL要求' }
}
& $ApiPython -m pip check
& $AsrPython -m pip check
& $OcrPython -m pip check

# 以下为已有入口；实际执行前必须确认DATABASE_URL为专用库。
& $ApiPython -m alembic current
& $ApiPython -m alembic heads
& $ApiPython -m alembic upgrade head
& $ApiPython -m ruff check app tests

# pytest夹具会重建TEST_DATABASE_NAME的public schema。
# DATABASE_URL仍指向独立的测试管理基库，不能与目标测试库同名；
# 不以开发库/生产库承担该角色。AUDIO_STORAGE_DIR必须指向媒体副本。
$env:APP_ENV = 'test'
$env:TEST_DATABASE_NAME = 'shengshengruer_m3_acceptance'
& $ApiPython -m pytest tests/test_acceptance.py tests/test_security_edges.py tests/test_module2_listening.py tests/test_module2_recheck.py -q
```

`$ApiPython/$AsrPython/$OcrPython`为三个独立虚拟环境中的python.exe绝对路径，版本相同但依赖分别安装，不得将三个变量都绑定同一虚拟环境或系统python。执行Ruff前先完成T02的py313配置适配；旧py314配置不是已完成适配的证据。升级迁移旧库副本测试与pytest空schema测试分开，后者不能证明旧库升级安全。测试启动前校验实际engine绑定、隔离库标识和媒体根；测试夹具若失去隔离证明立即BLOCKED。

### 7.2 当前入口与后续验收步骤

以下命令入口已在独立开发目录存在。变量由受控配置提供；命令示例不是本次重新执行日志，输出目录必须是新的运行目录。

```powershell
# 默认原文路径：处理环境中核验CPU对齐/解码依赖，不要求GPU转写。
& $AsrPython -m app.module3.diagnostics --profile align --output $EvidenceDir
& $AsrPython -m app.module3.reference_review --reference $ReferenceManifest --output $NewRunDir

# 管理员先按API准备任务；原文缺省或stop_after缺省均采用reference/align。
& $AsrPython -m app.module3.worker --once

# 仅显式无原文ASR路线检查GPU及转写模型；OCR/API分别预检。
& $AsrPython -m app.module3.diagnostics --profile asr --output $EvidenceDir
& $ApiPython -m app.module3.diagnostics --profile api --output $EvidenceDir
& $OcrPython -m app.module3.diagnostics --profile ocr --output $EvidenceDir

# 先按7.1确认隔离数据库/媒体和实际engine，再运行自动测试。
& $ApiPython -m pytest tests -q
```

ReferenceManifest保存原件哈希、固定来源句子及其搜索范围；本套准备与原图核对记录见原文实跑证据。组件命令不创建管理员任务、不进行ASR/LLM或业务入库。完整HTTP串联工具及其场景证据仍为T13目标，不能将不存在的acceptance_module3.py写成已可运行。

每个命令记录工作目录、解释器路径/版本、完整去敏参数、开始/结束UTC时间、退出码、标准输出/错误及证据哈希。退出0也需核对断言和业务证据，不能只凭退出码评判内容。

T13为A01—A41维护用例/证据映射；现有tests/module3按功能命名，不能假定全部具有a01等函数名或用-k空选中冒充通过。未覆盖场景保留待验收，不以空测试占位PASS。fixture说明必须列出原输入、每一处故障注入位置（例如提交前抛错、发布前拒写、复用B后提交失败）、预期恢复点及失败前后SQL/文件/HTTP断言。涉及真实模型或人工核查的场景单独标记并输出所需外部证据，不让Mock测试自动通过这些子项。

HTTP验收工具须顺序执行：登录管理员/学生/另一管理员 → 登记材料 → 分别创建text/scan任务 → 启动worker并轮询（总超时可配置，超时明确BLOCKED/FAIL原因）→ 核对reference/align产物并停在对齐确认点 → 用户明确确认继续后组装/标注/待审入库 → 读取初稿/异常 → 提交有真实依据的修订及复核 → POST checks → POST current-batch → 既有visibility confirm → 查询既有整卷/companion/checks → 下载全音频及Range → 解码与hash核验 → cancel并重测学生访问。不能自动替真人编造review批准记录。

现有复用路由为：`GET /api/v1/listening-papers`、`GET /api/v1/listening-papers/{exam_paper_id}`、`GET /api/v1/listening-papers/{exam_paper_id}/audio`、管理员同卷 `/companion`、`/checks`，以及 `POST /api/v1/admin/listening-papers/{exam_paper_id}/visibility`。现有checks为读取已存检查，不能把GET当成重新检查；学生视角详情对管理员也走可见性判定，未开放内容应走管理员配套/任务结果接口。

### 7.3 质量统计与证据目录

正式测评前固定关键字段清单和分母，至少覆盖题号、篇章、题干、四选项、标准答案、解析忠实性/来源、body/question归属和句级边界；字段缺失计入分母。初稿正确率=初稿核对正确字段数/应核对字段数；最终正确率同分母另报。真实参考答案和参考边界的确认依据需可查，不能以自动输出自当标准。

关系最低覆盖按每题主要技能、该技能证据、答案证据分别统计；辅助技能若输出，也必须检查其证据。多条共同主要按实际应有关系计数，不能只按行数增大分子。报告同时给出存在性覆盖、有效正文引用覆盖和人工语义复核，不能用覆盖率100%推断关系正确。

句级误差分别统计start/end绝对误差、分位数/最大值、阈内覆盖及无法对齐句数；分母在正式测评前固定，可接受阈值按U02已确认的起止分别≤300ms执行，不能剔除失败句提高覆盖。人工修正题数按去重题目计，字段修改和标注修改分别说明；自动耗时按阶段、人工复核耗时按实际记录，不推测。无自动初稿最低率或人工修正比例新增硬门槛。

建议受控证据结构（开发后产生，不是本轮已存在证据）：

```text
module3-acceptance/<run_id>/
  manifest.json                  # code/env/input/profile/prompt/dictionary hashes
  commands/                      # 去敏命令、退出码、日志
  tasks/<task_id>/                # 状态、自动初稿、最终结果、差异、issues
  sources/                       # 原件引用、扫描生成条件；无权公开不复制入Git
  database/                      # revision、计数、ID/批次归属与失败前后快照
  http/                          # 去token请求响应、整卷/媒体hash、Range证据
  review/                        # 逐题、整套核听、标注语义真实记录
  quality/                       # text/scan各自初稿与最终统计
  report.md                      # 卡片与矩阵回填、未覆盖与阻塞
```

## 8. 验收回填模板

下列模板由后续实际实施/验收人员复制填写；预置BLOCKED表示本轮未执行，不表示任何运行测试已经失败。

### 8.1 任务卡执行记录

| 字段 | 回填内容 |
| --- | --- |
| 任务编号／对应需求／验收场景 | T__／M3-__／A__（原R__如适用） |
| 本次结论 | BLOCKED（待实际执行）；后续仅选PASS/PARTIAL/FAIL/BLOCKED |
| 实际改动 | 文件、函数、接口/表/配置变化；与设计的偏差及理由 |
| 代码版本 | 起点提交、最终提交、分支、PR及合并状态；未提交差异另记 |
| 环境版本 | OS、三个独立环境python.exe路径、各自3.13.16/x64/GIL信息、py313配置、各锁哈希、DB/迁移revision、驱动/DLL实际来源 |
| 方法版本 | profile、模型revision、提示词/schema/词典hash、DeepSeek请求与实际响应model |
| 输入 | 样例、原件hash、可信题量来源、扫描条件；任务ID/批次ID/result_hash |
| 测试命令 | 工作目录、解释器、完整去敏命令、真实执行起止时间 |
| 实际结果 | 退出码、实际用例统计、预期与实际差异；Mock/真实/人工分别记录 |
| 证据位置 | 受控相对路径或有效链接、SHA-256、对应对象/题号/时间范围 |
| 失败处理／复验 | 错误码、回滚/保留对象、重试task、修复提交及复验命令结果 |
| 未覆盖项 | 资源、输入条件、平台、精度、语义或回归缺口；不能写“无”而不给依据 |
| 后续工作 | 下一任务、解除阻塞条件和预计执行时点（未确认则待定） |
| 医疗声明 | `MEDICAL_VALIDATION=NOT_CLAIMED` |

### 8.2 验收矩阵逐项回填

| 场景／任务 | 实际输入与版本 | 实际操作或命令 | 预期 | 实际 | 结论 | 证据／hash | 未覆盖及后续 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A__／T__ | 待填 | 未执行 | 引用第6章 | 尚无运行结果 | BLOCKED | 待产生 | 列明确前提 |

同一场景多次运行分别编号run_id，不覆盖早期FAIL记录。技术子项PASS但真实内容未核对时，分列技术PASS与内容BLOCKED，整项不得自动PASS。

### 8.3 内容和质量回填

| 输入路径／任务／批次 | 阶段 | 应核对字段数 | 正确数／正确率 | 必交关系应有／有效／语义结论 | 修正题数及类型 | 自动／人工耗时 | 句级阈值、覆盖与异常 | 真实复核证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| text／待填 | auto_draft | 待填 | 待填 | 待填 | 不适用 | 待填 | 缺人工参考/整套核听则BLOCKED | 待填 |
| text／待填 | final | 同口径 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 |
| scan／待填 | auto_draft | 待填 | 待填 | 待填 | 不适用 | 待填 | 待填 | 待填 |
| scan／待填 | final | 同口径 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 |

### 8.4 整体交付结论

```text
报告版本／run_id：
代码提交／三环境Python3.13.16路径／py313配置／迁移版本：
技术冻结编号：M3-WIN64-1.1.0（实际降级另记profile）
输入与方法清单hash：
当前批次／可见性（与验收独立）：
技术场景结论：PASS / PARTIAL / FAIL / BLOCKED（选一）
真实逐题核对结论：PASS / PARTIAL / FAIL / BLOCKED（选一）
整套核听与句级精度结论：PASS / PARTIAL / FAIL / BLOCKED（选一）
标注及证据语义复核结论：PASS / PARTIAL / FAIL / BLOCKED（选一）
文本／扫描两路径覆盖与局限：
整体结论：BLOCKED（未实际实施和验收前保留）
证据索引与完整性hash：
未覆盖项、阻塞原因及解除条件：
后续任务与复验安排：
MEDICAL_VALIDATION=NOT_CLAIMED
```

本轮交付是开发设计和验收计划。后续只有在真实处理、实际入库、既有HTTP接口读取、受控媒体核验及规定内容复核均有证据后，才可回填整体PASS。
