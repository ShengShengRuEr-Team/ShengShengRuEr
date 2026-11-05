# 模块三逐字段实施映射

> 更新日期：2026-11-04；同步开发文档V1.2、需求V1.7和技术基线V1.1／`M3-WIN64-1.1.0`；配套[开发文档](development-plan.md)。这是待实现的字段设计，不是迁移已执行或字段已齐全的报告。
> 当前列通过固定提交 `b965a0f3771c9f6212be29b65fda326ce0307b11` 的SQLAlchemy模型逐项读取；不使用本机旧分支推断集成现状。
> 业务基线SHA-256：`6348030d2b5acb49e0cf036487f4ddd508428f33b0033e5cfb4261d40a986580`。`MEDICAL_VALIDATION=NOT_CLAIMED`。

## 使用规则

- 每行“现有”仅说明代码中存在列，不证明数据库已迁移、数据已正确或数据库已具备全部基线约束；列类型展示是模型声明。
- 本次技术更新只将API目标解释器从3.14.10统一到3.13.16，三个环境仍独立；16表JSON哈希及304个字段定义未改变，因此不为解释器变更重建业务表或修改字段语义。迁移、模型导入和读写约束须在Python3.13.16 API环境复验，旧Python3.14证据保留历史效力但不代替新目标通过结论。
- 主键均映射物理 `id BIGINT`，由数据库生成；基线整数、显示码和旧码不能直接充当新外键。
- 基线的“条件必填”按输入题型、关系种类和正文/选项位置执行；不得因为数据库列可空就跳过业务必填。基线可空但模块三要求更严者，以开发文档的必交检查为准。
- `attributes_json`从基线TEXT解析为JSONB，保留原始来源哈希与文本；模型/schema/方法/复核不能只存无校验的大JSON。关系attributes按rulesByKind白名单检查。
- 新表字段类型按基线映射PostgreSQL：BIGINT/INT→BIGINT/INTEGER，TEXT/VARCHAR保留语义，BOOLEAN→BOOLEAN，时间→TIMESTAMPTZ UTC。现有列长度较小处见逐行目标说明，必要时增量扩展，不做整库重建。
- `reviewer/reviewed_at/review_note`采用独立processing_reviews承载，绑定实体、批次或词典快照、result_hash和真实操作者；旧数据未知保持待审，禁止伪填“已通过”。各表review_status枚举须分别取基线values，不能把体裁词典的复核状态套进既有通用CHECK。
- 当前批次关系均加batch_id；共享词典及其目录/技能错因关系加snapshot_id。物理表数可超过16；新增辅助表见主文档§3.3及本文件末尾。
- 下列基线规则中涉及跨卷共享、派生音频链的能力保留原定义，但不列为本期实现范围；本期以同套、批次内绑定满足必交关系。词典原ID和显示码通过映射保留，不要求新数据库自增ID等于采集表ID。
- 现有 `format VARCHAR(16)`、`exam_level_scope VARCHAR(16)`、`option_mapping_state VARCHAR(16)` 足以容纳当前确认枚举，本期保留容量并说明与基线VARCHAR(32)的差异；不宣称物理类型逐字一致。`duration_ms BIGINT`比基线INT容量更大，保留。超长自由文本按逐行指定扩展，不截断。
- 音频 `storage_key`目标TEXT，但写入服务限制为受控相对路径、最长512个Unicode码点，并验证实际文件系统可用；既有短键兼容。稳定试卷的source/mapping_source等若被本次修订影响，先保存到批次产物/metadata，激活事务才同步当前表示，不能待审时覆盖旧状态。

## 01_exam_paper → `exam_papers`

当前已建子集，T03按下表增量扩展。

| 基线字段 | 基线类型／必填 | 当前代码 | 目标承载与实施处置 |
| --- | --- | --- | --- |
| `exam_paper_id` | BIGINT／必填 | 现有 `id BigInteger`（源码L82） | 复用 `exam_papers.id BIGINT`；数据库生成，临时ID统一映射 |
| `exam_paper_code` | VARCHAR(64)／必填 | 现有 `exam_paper_code String(64)`（源码L83） | 复用 `exam_papers.exam_paper_code`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `exam_level` | VARCHAR(32)／必填 | 现有 `exam_level String(32)`（源码L84） | 复用 `exam_papers.exam_level`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `exam_year` | INT／必填 | 现有 `exam_year Integer`（源码L85） | 复用 `exam_papers.exam_year`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `exam_month` | INT／必填 | 现有 `exam_month Integer`（源码L86） | 复用 `exam_papers.exam_month`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `paper_set` | INT／必填 | 现有 `paper_set Integer`（源码L87） | 复用 `exam_papers.paper_set`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `source` | TEXT／必填 | 现有 `source Text`（源码L99） | 复用 `exam_papers.source`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `content_group_id` | BIGINT／可空 | 未建 | 新增 `batch_paper_metadata.content_group_id`；按batch版本化，content_group_id引用同批次内容组；未确认等价不伪填 |
| `playback_audio_id` | BIGINT／可空 | 现有 `playback_audio_id BigInteger`（源码L91） | 复用 `exam_papers.playback_audio_id`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `binding_state` | VARCHAR(32)／可空 | 未建 | 新增 `batch_paper_metadata.binding_state`；按batch版本化，content_group_id引用同批次内容组；未确认等价不伪填 |
| `question_order_state` | VARCHAR(32)／可空 | 未建 | 新增 `batch_paper_metadata.question_order_state`；按batch版本化，content_group_id引用同批次内容组；未确认等价不伪填 |
| `option_order_state` | VARCHAR(32)／可空 | 未建 | 新增 `batch_paper_metadata.option_order_state`；按batch版本化，content_group_id引用同批次内容组；未确认等价不伪填 |
| `equivalence_basis` | TEXT／可空 | 未建 | 新增 `batch_paper_metadata.equivalence_basis`；按batch版本化，content_group_id引用同批次内容组；未确认等价不伪填 |
| `mapping_source` | TEXT／可空 | 现有 `mapping_source Text`（源码L100） | 复用 `exam_papers.mapping_source`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `collector` | VARCHAR(64)／必填 | 现有 `collector String(64)`（源码L101） | 复用 `exam_papers.collector`；补基线枚举/必填/来源检查，保持既有接口字段语义；系统生成如实记方法/进程来源，不伪填人工姓名 |
| `review_status` | VARCHAR(32)／必填 | 现有 `review_status String(32)`（源码L104） | 复用 `exam_papers.review_status`；补基线枚举/必填/来源检查，保持既有接口字段语义；自动结果默认待审，词典历史审核状态仅按实际来源继承并留痕 |
| `reviewer` | VARCHAR(64)／可空 | 未建 | `processing_reviews.operator_user_id/operator_label`；登录用户由服务端记录，历史来源标签另存，不假造用户 |
| `reviewed_at` | TIMESTAMP／可空 | 未建 | `processing_reviews.reviewed_at TIMESTAMPTZ`；UTC，绑定被审核内容hash |
| `review_note` | TEXT／可空 | 未建 | `processing_reviews.note TEXT`；保存决定、依据引用及真实核查范围 |
| `notes` | TEXT／可空 | 未建 | 新增 `exam_papers.notes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `attributes_json` | TEXT／可空 | 未建 | 新增 `exam_papers.attributes_json JSONB`；按表/关系种类校验，原始字符串留产物 |
| `legacy_payload_json` | TEXT／可空 | 未建 | `processing_artifacts`的受控原始行JSON＋hash；迁移输入快照，非业务唯一查询来源 |

该表基线规则（必须落实或明确本期边界）：

- exam_paper_code唯一；考试级别、年份、月份、套别组合唯一。
- 独立内容或确认等价时，content_group_id必填；playback_audio_id须属于同一内容组。
- 内容是否相同与题号、选项顺序是否已知分别记录；未知映射不默认一致。
- 原卷身份保留，听力相同的试卷通过第12表共享内容。

## 02_audio → `audio_files`

当前已建子集，T03按下表增量扩展。

| 基线字段 | 基线类型／必填 | 当前代码 | 目标承载与实施处置 |
| --- | --- | --- | --- |
| `audio_id` | BIGINT／必填 | 现有 `id BigInteger`（源码L45） | 复用 `audio_files.id BIGINT`；数据库生成，临时ID统一映射 |
| `audio_code` | VARCHAR(64)／必填 | 现有 `audio_code String(64)`（源码L46） | 复用 `audio_files.audio_code`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `content_group_id` | BIGINT／必填 | 未建 | 新增 `batch_audio_groups(batch_id,audio_id,content_group_id)`；本期每批次原音需绑定本套内容组；避免稳定音频指向单一版本内容组 |
| `source_paper_id` | BIGINT／可空 | 未建 | 新增 `audio_files.source_paper_id` 可空FK；表示首次来源，本期不用作独占或跨卷共享判定 |
| `storage_provider` | VARCHAR(32)／必填 | 现有 `storage_provider String(32)`（源码L47） | 复用 `audio_files.storage_provider`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `storage_key` | TEXT／必填 | 现有 `storage_key String(255)`（源码L50） | 现有VARCHAR(255)目标扩展为TEXT并保留唯一索引；受控相对路径、不截断；编码冲突拒绝 |
| `duration_ms` | INT／必填 | 现有 `duration_ms BigInteger`（源码L51） | 复用 `audio_files.duration_ms`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `format` | VARCHAR(32)／必填 | 现有 `format String(16)`（源码L52） | 复用 `audio_files.format`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `version_no` | INT／必填 | 现有 `version_no Integer`（源码L59） | 复用 `audio_files.version_no`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `variant_type` | VARCHAR(32)／必填 | 现有 `variant_type String(32)`（源码L60） | 复用 `audio_files.variant_type`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `derived_from_audio_id` | BIGINT／可空 | 未建 | 本期不建设派生音频链；原输入值保存在原始产物，提供非空派生引用时报范围不支持，不能静默丢弃后宣称完成 |
| `is_current` | BOOLEAN／必填 | 现有 `is_current Boolean`（源码L55） | 保留既有列兼容；待审新音频不得提前标当前；激活事务更新，权威读取按当前batch.audio_id及paper绑定 |
| `file_hash` | VARCHAR(64)／可空 | 现有 `file_hash String(64)`（源码L54） | 复用 `audio_files.file_hash`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `collector` | VARCHAR(64)／必填 | 现有 `collector String(64)`（源码L63） | 复用 `audio_files.collector`；补基线枚举/必填/来源检查，保持既有接口字段语义；系统生成如实记方法/进程来源，不伪填人工姓名 |
| `review_status` | VARCHAR(32)／必填 | 现有 `review_status String(32)`（源码L66） | 复用 `audio_files.review_status`；补基线枚举/必填/来源检查，保持既有接口字段语义；自动结果默认待审，词典历史审核状态仅按实际来源继承并留痕 |
| `reviewer` | VARCHAR(64)／可空 | 未建 | `processing_reviews.operator_user_id/operator_label`；登录用户由服务端记录，历史来源标签另存，不假造用户 |
| `reviewed_at` | TIMESTAMP／可空 | 未建 | `processing_reviews.reviewed_at TIMESTAMPTZ`；UTC，绑定被审核内容hash |
| `review_note` | TEXT／可空 | 未建 | `processing_reviews.note TEXT`；保存决定、依据引用及真实核查范围 |
| `notes` | TEXT／可空 | 未建 | 新增 `audio_files.notes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `attributes_json` | TEXT／可空 | 未建 | 新增 `audio_files.attributes_json JSONB`；按表/关系种类校验，原始字符串留产物 |
| `legacy_payload_json` | TEXT／可空 | 未建 | `processing_artifacts`的受控原始行JSON＋hash；迁移输入快照，非业务唯一查询来源 |

该表基线规则（必须落实或明确本期边界）：

- audio_code唯一；同一内容组内version_no唯一。
- duration_ms必须大于0；同组至多一份is_current=1。
- 派生音频须保留来源，禁止自引用与循环；派生不等于替代原文件。
- 剪辑改变时间轴后，重新核对该音频版本对应的篇章、转写和材料证据定位。

## 03_passage → `passages`

当前已建子集，T03按下表增量扩展。

| 基线字段 | 基线类型／必填 | 当前代码 | 目标承载与实施处置 |
| --- | --- | --- | --- |
| `passage_id` | BIGINT／必填 | 现有 `id BigInteger`（源码L193） | 复用 `passages.id BIGINT`；数据库生成，临时ID统一映射 |
| `passage_code` | VARCHAR(64)／必填 | 现有 `passage_code String(64)`（源码L203） | 复用 `passages.passage_code`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `audio_id` | BIGINT／必填 | 现有 `audio_id BigInteger`（源码L200） | 复用FK；模块三必须非空、等于批次audio_id，不能只凭单列FK证明音频一致 |
| `passage_index` | INT／必填 | 现有 `passage_index Integer`（源码L204） | 复用 `passages.passage_index`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `passage_type` | VARCHAR(32)／必填 | 现有 `passage_type String(32)`（源码L205） | 复用 `passages.passage_type`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `start_ms` | INT／必填 | 现有 `start_ms BigInteger`（源码L212） | 复用 `passages.start_ms`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `body_end_ms` | INT／必填 | 现有 `body_end_ms BigInteger`（源码L213） | 复用现有可空列以兼容旧记录；模块三正式检查必须非空且start<body_end<=end<=duration，新增profile规则 |
| `end_ms` | INT／必填 | 现有 `end_ms BigInteger`（源码L214） | 复用现有可空列以兼容旧记录；模块三正式检查必须非空且start<body_end<=end<=duration，新增profile规则 |
| `topic` | TEXT／可空 | 现有 `topic Text`（源码L206） | 复用 `passages.topic`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `scene` | TEXT／可空 | 现有 `scene Text`（源码L208） | 复用 `passages.scene`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `accent` | VARCHAR(32)／必填 | 现有 `accent String(32)`（源码L209） | 复用 `passages.accent`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `speaker_count` | INT／可空 | 现有 `speaker_count Integer`（源码L215） | 复用 `passages.speaker_count`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `genre_id` | BIGINT／可空 | 未建 | 新增 `passages.genre_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `genre_note` | TEXT／可空 | 未建 | 新增 `passages.genre_note`，按基线类型/枚举；条件必填由该对象规则检查 |
| `genre_confidence` | VARCHAR(32)／可空 | 未建 | 新增 `passages.genre_confidence`，按基线类型/枚举；条件必填由该对象规则检查 |
| `genre_review_status` | VARCHAR(32)／必填 | 未建 | 新增 `passages.genre_review_status`，按基线类型/枚举；条件必填由该对象规则检查 |
| `collector` | VARCHAR(64)／必填 | 现有 `collector String(64)`（源码L216） | 复用 `passages.collector`；补基线枚举/必填/来源检查，保持既有接口字段语义；系统生成如实记方法/进程来源，不伪填人工姓名 |
| `review_status` | VARCHAR(32)／必填 | 现有 `review_status String(32)`（源码L219） | 复用 `passages.review_status`；补基线枚举/必填/来源检查，保持既有接口字段语义；自动结果默认待审，词典历史审核状态仅按实际来源继承并留痕 |
| `reviewer` | VARCHAR(64)／可空 | 未建 | `processing_reviews.operator_user_id/operator_label`；登录用户由服务端记录，历史来源标签另存，不假造用户 |
| `reviewed_at` | TIMESTAMP／可空 | 未建 | `processing_reviews.reviewed_at TIMESTAMPTZ`；UTC，绑定被审核内容hash |
| `review_note` | TEXT／可空 | 未建 | `processing_reviews.note TEXT`；保存决定、依据引用及真实核查范围 |
| `notes` | TEXT／可空 | 未建 | 新增 `passages.notes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `attributes_json` | TEXT／可空 | 未建 | 新增 `passages.attributes_json JSONB`；按表/关系种类校验，原始字符串留产物 |
| `legacy_payload_json` | TEXT／可空 | 未建 | `processing_artifacts`的受控原始行JSON＋hash；迁移输入快照，非业务唯一查询来源 |

该表基线规则（必须落实或明确本期边界）：

- 同音频内passage_index唯一。
- 0 <= start_ms < body_end_ms <= end_ms <= audio.duration_ms。
- genre_id仅引用第09表启用试标的GENRE分类项；当前可选ID为1、2、3、6，暂不启用类别不进入下拉。无法确定时留空并保留待确认状态。
- 一篇材料一个主体裁；正文结束时间与随后录音问题结束时间分开。

## 04_transcript_segment → `transcript_segments`

当前已建子集，T03按下表增量扩展。

| 基线字段 | 基线类型／必填 | 当前代码 | 目标承载与实施处置 |
| --- | --- | --- | --- |
| `segment_id` | BIGINT／必填 | 现有 `id BigInteger`（源码L237） | 复用 `transcript_segments.id BIGINT`；数据库生成，临时ID统一映射 |
| `passage_id` | BIGINT／必填 | 现有 `passage_id BigInteger`（源码L241） | 复用 `transcript_segments.passage_id`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `segment_index` | INT／必填 | 现有 `segment_index Integer`（源码L244） | 复用 `transcript_segments.segment_index`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `start_ms` | INT／必填 | 现有 `start_ms BigInteger`（源码L248） | 复用 `transcript_segments.start_ms`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `end_ms` | INT／必填 | 现有 `end_ms BigInteger`（源码L249） | 复用 `transcript_segments.end_ms`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `text` | TEXT／必填 | 现有 `text Text`（源码L246） | 复用 `transcript_segments.text`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `speaker_code` | VARCHAR(64)／可空 | 现有 `speaker_code String(64)`（源码L247） | 复用 `transcript_segments.speaker_code`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `segment_type` | VARCHAR(32)／必填 | 现有 `segment_type String(32)`（源码L245） | 复用 `transcript_segments.segment_type`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `collector` | VARCHAR(64)／必填 | 现有 `collector String(64)`（源码L250） | 复用 `transcript_segments.collector`；补基线枚举/必填/来源检查，保持既有接口字段语义；系统生成如实记方法/进程来源，不伪填人工姓名 |
| `review_status` | VARCHAR(32)／必填 | 现有 `review_status String(32)`（源码L253） | 复用 `transcript_segments.review_status`；补基线枚举/必填/来源检查，保持既有接口字段语义；自动结果默认待审，词典历史审核状态仅按实际来源继承并留痕 |
| `reviewer` | VARCHAR(64)／可空 | 未建 | `processing_reviews.operator_user_id/operator_label`；登录用户由服务端记录，历史来源标签另存，不假造用户 |
| `reviewed_at` | TIMESTAMP／可空 | 未建 | `processing_reviews.reviewed_at TIMESTAMPTZ`；UTC，绑定被审核内容hash |
| `review_note` | TEXT／可空 | 未建 | `processing_reviews.note TEXT`；保存决定、依据引用及真实核查范围 |
| `notes` | TEXT／可空 | 未建 | 新增 `transcript_segments.notes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `attributes_json` | TEXT／可空 | 未建 | 新增 `transcript_segments.attributes_json JSONB`；按表/关系种类校验，原始字符串留产物 |
| `legacy_payload_json` | TEXT／可空 | 未建 | `processing_artifacts`的受控原始行JSON＋hash；迁移输入快照，非业务唯一查询来源 |

该表基线规则（必须落实或明确本期边界）：

- 同篇章内segment_index唯一；片段顺序不等于题号。
- start_ms < end_ms，且时间落在所属篇章范围。
- body片段落在正文范围，question片段位于正文后且不超出本篇结束。
- 原文如实采集；说话角色未知时留空，不仅凭文本猜测。

## 05_question → `questions`

当前已建子集，T03按下表增量扩展。

| 基线字段 | 基线类型／必填 | 当前代码 | 目标承载与实施处置 |
| --- | --- | --- | --- |
| `question_id` | BIGINT／必填 | 现有 `id BigInteger`（源码L273） | 复用 `questions.id BIGINT`；数据库生成，临时ID统一映射 |
| `question_code` | VARCHAR(64)／必填 | 现有 `question_code String(64)`（源码L280） | 复用 `questions.question_code`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `passage_id` | BIGINT／必填 | 现有 `passage_id BigInteger`（源码L277） | 复用 `questions.passage_id`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `source_paper_id` | BIGINT／可空 | 未建 | 通过 `questions.passage_id → passages.exam_paper_id`提供本期来源卷；输入非空值必须与该来源一致；不引入跨卷题库共享 |
| `question_index` | INT／可空 | 现有 `question_index Integer`（源码L285） | 复用 `questions.question_index`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `question_text` | TEXT／必填 | 现有 `question_text Text`（源码L286） | 复用 `questions.question_text`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `question_segment_id` | BIGINT／可空 | 现有 `question_segment_id BigInteger`（源码L281） | 复用 `questions.question_segment_id`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `option_a` | TEXT／条件必填 | 现有 `option_a Text`（源码L287） | 复用 `questions.option_a`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `option_b` | TEXT／条件必填 | 现有 `option_b Text`（源码L288） | 复用 `questions.option_b`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `option_c` | TEXT／条件必填 | 现有 `option_c Text`（源码L289） | 复用 `questions.option_c`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `option_d` | TEXT／条件必填 | 现有 `option_d Text`（源码L290） | 复用 `questions.option_d`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `correct_option` | VARCHAR(1)／条件必填 | 现有 `correct_option String(1)`（源码L291） | 复用 `questions.correct_option`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `explanation_text` | TEXT／必填 | 现有 `explanation_text Text`（源码L292） | 复用 `questions.explanation_text`；补基线枚举/必填/来源检查，保持既有接口字段语义；原解析/页码/变换另存provenance，摘要不得冒称逐字原文 |
| `content_state` | VARCHAR(32)／必填 | 现有 `content_state String(32)`（源码L296） | 复用 `questions.content_state`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `collector` | VARCHAR(64)／必填 | 现有 `collector String(64)`（源码L299） | 复用 `questions.collector`；补基线枚举/必填/来源检查，保持既有接口字段语义；系统生成如实记方法/进程来源，不伪填人工姓名 |
| `review_status` | VARCHAR(32)／必填 | 现有 `review_status String(32)`（源码L302） | 复用 `questions.review_status`；补基线枚举/必填/来源检查，保持既有接口字段语义；自动结果默认待审，词典历史审核状态仅按实际来源继承并留痕 |
| `reviewer` | VARCHAR(64)／可空 | 未建 | `processing_reviews.operator_user_id/operator_label`；登录用户由服务端记录，历史来源标签另存，不假造用户 |
| `reviewed_at` | TIMESTAMP／可空 | 未建 | `processing_reviews.reviewed_at TIMESTAMPTZ`；UTC，绑定被审核内容hash |
| `review_note` | TEXT／可空 | 未建 | `processing_reviews.note TEXT`；保存决定、依据引用及真实核查范围 |
| `notes` | TEXT／可空 | 未建 | 新增 `questions.notes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `attributes_json` | TEXT／可空 | 未建 | 新增 `questions.attributes_json JSONB`；按表/关系种类校验，原始字符串留产物 |
| `legacy_payload_json` | TEXT／可空 | 未建 | `processing_artifacts`的受控原始行JSON＋hash；迁移输入快照，非业务唯一查询来源 |

该表基线规则（必须落实或明确本期边界）：

- question_code唯一；question_index保留来源卷全卷题号，目标原卷题号由第13表记录。
- question_segment_id如有值，须属于同篇且segment_type=question。
- 题目与技能通过07C_skill_question中的QUESTION_SKILL直接关联，填写question_id、skill_id与主辅角色。
- option_a、option_b、option_c、option_d保存基准来源卷的四个英文选项；correct_option为A/B/C/D。
- 可用四选一题须四项均完整且有且仅有一个正确答案；资料缺失时标待补齐，不猜选项字母或答案。
- 选项由question_id与字母共同定位；原卷选项重排仍由第13表现有attributes_json.option_letter_mapping记录。

## 06_skill → `skills`

当前未建，T03新增。

| 基线字段 | 基线类型／必填 | 当前代码 | 目标承载与实施处置 |
| --- | --- | --- | --- |
| `skill_id` | BIGINT／必填 | 未建 | 新增 `skills.id BIGINT`；数据库生成，临时ID统一映射 |
| `skill_code` | VARCHAR(64)／必填 | 未建 | 新增 `skills.skill_code`，按基线类型/枚举；条件必填由该对象规则检查 |
| `display_code` | VARCHAR(64)／必填 | 未建 | 新增 `skills.display_code`，按基线类型/枚举；条件必填由该对象规则检查 |
| `legacy_codes` | VARCHAR(64)／可空 | 未建 | 新增 `skills.legacy_codes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `skill_level` | INT／必填 | 未建 | 新增 `skills.skill_level`，按基线类型/枚举；条件必填由该对象规则检查 |
| `skill_name` | TEXT／必填 | 未建 | 新增 `skills.skill_name`，按基线类型/枚举；条件必填由该对象规则检查 |
| `definition` | TEXT／必填 | 未建 | 新增 `skills.definition`，按基线类型/枚举；条件必填由该对象规则检查 |
| `observable_behavior` | TEXT／条件必填 | 未建 | 新增 `skills.observable_behavior`，按基线类型/枚举；条件必填由该对象规则检查 |
| `counter_example` | TEXT／可空 | 未建 | 新增 `skills.counter_example`，按基线类型/枚举；条件必填由该对象规则检查 |
| `usage_scope` | VARCHAR(32)／必填 | 未建 | 新增 `skills.usage_scope`，按基线类型/枚举；条件必填由该对象规则检查 |
| `exam_level_scope` | VARCHAR(32)／必填 | 未建 | 新增 `skills.exam_level_scope`，按基线类型/枚举；条件必填由该对象规则检查 |
| `status` | VARCHAR(32)／必填 | 未建 | 新增 `skills.status`，按基线类型/枚举；条件必填由该对象规则检查 |
| `collector` | VARCHAR(64)／必填 | 未建 | 新增 `skills.collector`，按基线类型/枚举；条件必填由该对象规则检查；系统生成如实记方法/进程来源，不伪填人工姓名 |
| `review_status` | VARCHAR(32)／必填 | 未建 | 新增 `skills.review_status`，按基线类型/枚举；条件必填由该对象规则检查；自动结果默认待审，词典历史审核状态仅按实际来源继承并留痕 |
| `reviewer` | VARCHAR(64)／可空 | 未建 | `processing_reviews.operator_user_id/operator_label`；登录用户由服务端记录，历史来源标签另存，不假造用户 |
| `reviewed_at` | TIMESTAMP／可空 | 未建 | `processing_reviews.reviewed_at TIMESTAMPTZ`；UTC，绑定被审核内容hash |
| `review_note` | TEXT／可空 | 未建 | `processing_reviews.note TEXT`；保存决定、依据引用及真实核查范围 |
| `notes` | TEXT／可空 | 未建 | 新增 `skills.notes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `attributes_json` | TEXT／可空 | 未建 | 新增 `skills.attributes_json JSONB`；按表/关系种类校验，原始字符串留产物 |
| `legacy_payload_json` | TEXT／可空 | 未建 | `processing_artifacts`的受控原始行JSON＋hash；迁移输入快照，非业务唯一查询来源 |

该表基线规则（必须落实或明确本期边界）：

- 三级结构为5个一级目录、10个二级目录、24个三级技能；展示顺序严格沿用确认稿。
- skill_code与skill_id为稳定身份；display_code只作树内展示；合并项在legacy_codes保留全部旧码。
- 一级、二级仅作目录；父子分类放07D_other_relation中的SKILL_TAXONOMY，一条非根记录恰有一个主分类父节点。
- S07熟悉词汇的词义识别、S13句子主干与成分关系理解主要用于专项诊断；日常题目标注不默认添加。
- S16条件与假设、S26跨句指代保留，并填写判定条件与误标反例。
- 原S01—S06、S36退出；S37—S42属于后续过程用途，不加入本次采集标注表。
- 条目设计确认不等于已完成测量验证；审核人、时间与审核状态按真实情况填写。

## 07A_skill_error → `skill_error_relations`

当前未建，T03新增。

| 基线字段 | 基线类型／必填 | 当前代码 | 目标承载与实施处置 |
| --- | --- | --- | --- |
| `relation_id` | BIGINT／必填 | 未建 | 新增 `skill_error_relations.id BIGINT`；数据库生成，临时ID统一映射 |
| `relation_code` | VARCHAR(64)／必填 | 未建 | 新增 `skill_error_relations.relation_code`，按基线类型/枚举；条件必填由该对象规则检查 |
| `revision_no` | INT／必填 | 未建 | 新增 `skill_error_relations.revision_no`，按基线类型/枚举；条件必填由该对象规则检查 |
| `is_current` | BOOLEAN／必填 | 未建 | 新增 `skill_error_relations.is_current`，按基线类型/枚举；条件必填由该对象规则检查 |
| `skill_id` | BIGINT／必填 | 未建 | 新增 `skill_error_relations.skill_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `error_cause_id` | BIGINT／必填 | 未建 | 新增 `skill_error_relations.error_cause_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `relation_nature` | TEXT／必填 | 未建 | 新增 `skill_error_relations.relation_nature`，按基线类型/枚举；条件必填由该对象规则检查 |
| `rationale` | TEXT／必填 | 未建 | 新增 `skill_error_relations.rationale`，按基线类型/枚举；条件必填由该对象规则检查 |
| `candidate_scope` | TEXT／必填 | 未建 | 新增 `skill_error_relations.candidate_scope`，按基线类型/枚举；条件必填由该对象规则检查 |
| `selection_rule` | TEXT／必填 | 未建 | 新增 `skill_error_relations.selection_rule`，按基线类型/枚举；条件必填由该对象规则检查 |
| `collector` | VARCHAR(64)／必填 | 未建 | 新增 `skill_error_relations.collector`，按基线类型/枚举；条件必填由该对象规则检查；系统生成如实记方法/进程来源，不伪填人工姓名 |
| `review_status` | VARCHAR(32)／必填 | 未建 | 新增 `skill_error_relations.review_status`，按基线类型/枚举；条件必填由该对象规则检查；自动结果默认待审，词典历史审核状态仅按实际来源继承并留痕 |
| `reviewer` | VARCHAR(64)／可空 | 未建 | `processing_reviews.operator_user_id/operator_label`；登录用户由服务端记录，历史来源标签另存，不假造用户 |
| `reviewed_at` | TIMESTAMP／可空 | 未建 | `processing_reviews.reviewed_at TIMESTAMPTZ`；UTC，绑定被审核内容hash |
| `review_note` | TEXT／可空 | 未建 | `processing_reviews.note TEXT`；保存决定、依据引用及真实核查范围 |
| `notes` | TEXT／可空 | 未建 | 新增 `skill_error_relations.notes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `legacy_payload_json` | TEXT／可空 | 未建 | `processing_artifacts`的受控原始行JSON＋hash；迁移输入快照，非业务唯一查询来源 |

该表基线规则（必须落实或明确本期边界）：

- 本组仅保存ERROR_SKILL，省略重复的relation_kind列；所有记录均为条件检查或补练候选。
- skill_id与error_cause_id均必填，引用三级具体技能与错因；相同当前错因、技能组合去重。
- 关系性质、适用条件与边界、可检查范围和选用规则从原attributes_json拆成四个直接可读字段。
- 候选关系不表示所有技能同时成立，不由题目对错推定个人错因。语音错因不强行对应当前技能树。

## 07B_error_question → `error_question_relations`

当前未建，T03新增。

| 基线字段 | 基线类型／必填 | 当前代码 | 目标承载与实施处置 |
| --- | --- | --- | --- |
| `relation_id` | BIGINT／必填 | 未建 | 新增 `error_question_relations.id BIGINT`；数据库生成，临时ID统一映射 |
| `relation_kind` | VARCHAR(32)／必填 | 未建 | 新增 `error_question_relations.relation_kind`，按基线类型/枚举；条件必填由该对象规则检查 |
| `relation_code` | VARCHAR(64)／必填 | 未建 | 新增 `error_question_relations.relation_code`，按基线类型/枚举；条件必填由该对象规则检查 |
| `revision_no` | INT／必填 | 未建 | 新增 `error_question_relations.revision_no`，按基线类型/枚举；条件必填由该对象规则检查 |
| `is_current` | BOOLEAN／必填 | 未建 | 新增 `error_question_relations.is_current`，按基线类型/枚举；条件必填由该对象规则检查 |
| `question_id` | BIGINT／可空 | 未建 | 新增 `error_question_relations.question_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `error_cause_id` | BIGINT／可空 | 未建 | 新增 `error_question_relations.error_cause_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `option_letter` | VARCHAR(1)／可空 | 未建 | 新增 `error_question_relations.option_letter`，按基线类型/枚举；条件必填由该对象规则检查；表示题库底层选项字母，展示时按本套映射转换 |
| `owner_relation_id` | BIGINT／可空 | 未建 | 新增 `error_question_relations.owner_relation_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `evidence_id` | BIGINT／可空 | 未建 | 新增 `error_question_relations.evidence_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `sort_order` | INT／可空 | 未建 | 新增 `error_question_relations.sort_order`，按基线类型/枚举；条件必填由该对象规则检查 |
| `attributes_json` | TEXT／可空 | 未建 | 新增 `error_question_relations.attributes_json JSONB`；按表/关系种类校验，原始字符串留产物 |
| `collector` | VARCHAR(64)／必填 | 未建 | 新增 `error_question_relations.collector`，按基线类型/枚举；条件必填由该对象规则检查；系统生成如实记方法/进程来源，不伪填人工姓名 |
| `review_status` | VARCHAR(32)／必填 | 未建 | 新增 `error_question_relations.review_status`，按基线类型/枚举；条件必填由该对象规则检查；自动结果默认待审，词典历史审核状态仅按实际来源继承并留痕 |
| `reviewer` | VARCHAR(64)／可空 | 未建 | `processing_reviews.operator_user_id/operator_label`；登录用户由服务端记录，历史来源标签另存，不假造用户 |
| `reviewed_at` | TIMESTAMP／可空 | 未建 | `processing_reviews.reviewed_at TIMESTAMPTZ`；UTC，绑定被审核内容hash |
| `review_note` | TEXT／可空 | 未建 | `processing_reviews.note TEXT`；保存决定、依据引用及真实核查范围 |
| `notes` | TEXT／可空 | 未建 | 新增 `error_question_relations.notes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `legacy_payload_json` | TEXT／可空 | 未建 | `processing_artifacts`的受控原始行JSON＋hash；迁移输入快照，非业务唯一查询来源 |

该表基线规则（必须落实或明确本期边界）：

- QUESTION_ERROR_CANDIDATE行填写question_id、error_cause_id；可选本题干扰项option_letter，owner_relation_id与evidence_id留空。
- CANDIDATE_EVIDENCE行仅填写owner_relation_id、evidence_id、sort_order；owner指向本表QUESTION_ERROR_CANDIDATE行。
- 候选仅选三级错因；证据须为该题同篇正文原文；同候选同证据及链内顺序去重。
- 一条候选可对应多条证据，每条证据单独一行；题目候选机制不等于个人实际错因。

## 07C_skill_question → `skill_question_relations`

当前未建，T03新增。

| 基线字段 | 基线类型／必填 | 当前代码 | 目标承载与实施处置 |
| --- | --- | --- | --- |
| `relation_id` | BIGINT／必填 | 未建 | 新增 `skill_question_relations.id BIGINT`；数据库生成，临时ID统一映射 |
| `relation_kind` | VARCHAR(32)／必填 | 未建 | 新增 `skill_question_relations.relation_kind`，按基线类型/枚举；条件必填由该对象规则检查 |
| `relation_code` | VARCHAR(64)／必填 | 未建 | 新增 `skill_question_relations.relation_code`，按基线类型/枚举；条件必填由该对象规则检查 |
| `revision_no` | INT／必填 | 未建 | 新增 `skill_question_relations.revision_no`，按基线类型/枚举；条件必填由该对象规则检查 |
| `is_current` | BOOLEAN／必填 | 未建 | 新增 `skill_question_relations.is_current`，按基线类型/枚举；条件必填由该对象规则检查 |
| `question_id` | BIGINT／可空 | 未建 | 新增 `skill_question_relations.question_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `skill_id` | BIGINT／可空 | 未建 | 新增 `skill_question_relations.skill_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `owner_relation_id` | BIGINT／可空 | 未建 | 新增 `skill_question_relations.owner_relation_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `evidence_id` | BIGINT／可空 | 未建 | 新增 `skill_question_relations.evidence_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `role` | VARCHAR(64)／可空 | 未建 | 新增 `skill_question_relations.role`，按基线类型/枚举；条件必填由该对象规则检查 |
| `sort_order` | INT／可空 | 未建 | 新增 `skill_question_relations.sort_order`，按基线类型/枚举；条件必填由该对象规则检查 |
| `attributes_json` | TEXT／可空 | 未建 | 新增 `skill_question_relations.attributes_json JSONB`；按表/关系种类校验，原始字符串留产物 |
| `collector` | VARCHAR(64)／必填 | 未建 | 新增 `skill_question_relations.collector`，按基线类型/枚举；条件必填由该对象规则检查；系统生成如实记方法/进程来源，不伪填人工姓名 |
| `review_status` | VARCHAR(32)／必填 | 未建 | 新增 `skill_question_relations.review_status`，按基线类型/枚举；条件必填由该对象规则检查；自动结果默认待审，词典历史审核状态仅按实际来源继承并留痕 |
| `reviewer` | VARCHAR(64)／可空 | 未建 | `processing_reviews.operator_user_id/operator_label`；登录用户由服务端记录，历史来源标签另存，不假造用户 |
| `reviewed_at` | TIMESTAMP／可空 | 未建 | `processing_reviews.reviewed_at TIMESTAMPTZ`；UTC，绑定被审核内容hash |
| `review_note` | TEXT／可空 | 未建 | `processing_reviews.note TEXT`；保存决定、依据引用及真实核查范围 |
| `notes` | TEXT／可空 | 未建 | 新增 `skill_question_relations.notes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `legacy_payload_json` | TEXT／可空 | 未建 | `processing_artifacts`的受控原始行JSON＋hash；迁移输入快照，非业务唯一查询来源 |

该表基线规则（必须落实或明确本期边界）：

- QUESTION_SKILL行填写question_id、skill_id、role，role为PRIMARY/AUXILIARY；owner_relation_id与evidence_id留空。
- SKILL_EVIDENCE行仅填写owner_relation_id、evidence_id、sort_order；owner指向本表QUESTION_SKILL行。
- 技能只选三级；S07和S13主要用于专项诊断，用于题目标注时需说明适用证据。默认一个主要技能，共同主要需说明理由。
- 证据须为该题同篇正文；同技能标注同证据和链内顺序去重。多处证据逐条记录，不在一格拼接证据ID。

## 07D_other_relation → `other_relations`

当前未建，T03新增。

| 基线字段 | 基线类型／必填 | 当前代码 | 目标承载与实施处置 |
| --- | --- | --- | --- |
| `relation_id` | BIGINT／必填 | 未建 | 新增 `other_relations.id BIGINT`；数据库生成，临时ID统一映射 |
| `relation_kind` | VARCHAR(32)／必填 | 未建 | 新增 `other_relations.relation_kind`，按基线类型/枚举；条件必填由该对象规则检查 |
| `relation_code` | VARCHAR(64)／必填 | 未建 | 新增 `other_relations.relation_code`，按基线类型/枚举；条件必填由该对象规则检查 |
| `revision_no` | INT／必填 | 未建 | 新增 `other_relations.revision_no`，按基线类型/枚举；条件必填由该对象规则检查 |
| `is_current` | BOOLEAN／必填 | 未建 | 新增 `other_relations.is_current`，按基线类型/枚举；条件必填由该对象规则检查 |
| `from_skill_id` | BIGINT／可空 | 未建 | 新增 `other_relations.from_skill_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `to_skill_id` | BIGINT／可空 | 未建 | 新增 `other_relations.to_skill_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `question_id` | BIGINT／可空 | 未建 | 新增 `other_relations.question_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `language_item_id` | BIGINT／可空 | 未建 | 新增 `other_relations.language_item_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `option_letter` | VARCHAR(1)／可空 | 未建 | 新增 `other_relations.option_letter`，按基线类型/枚举；条件必填由该对象规则检查；表示题库底层选项字母，展示时按本套映射转换 |
| `segment_id` | BIGINT／可空 | 未建 | 新增 `other_relations.segment_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `evidence_id` | BIGINT／可空 | 未建 | 新增 `other_relations.evidence_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `role` | VARCHAR(64)／可空 | 未建 | 新增 `other_relations.role`，按基线类型/枚举；条件必填由该对象规则检查 |
| `sort_order` | INT／可空 | 未建 | 新增 `other_relations.sort_order`，按基线类型/枚举；条件必填由该对象规则检查 |
| `attributes_json` | TEXT／可空 | 未建 | 新增 `other_relations.attributes_json JSONB`；按表/关系种类校验，原始字符串留产物 |
| `collector` | VARCHAR(64)／必填 | 未建 | 新增 `other_relations.collector`，按基线类型/枚举；条件必填由该对象规则检查；系统生成如实记方法/进程来源，不伪填人工姓名 |
| `review_status` | VARCHAR(32)／必填 | 未建 | 新增 `other_relations.review_status`，按基线类型/枚举；条件必填由该对象规则检查；自动结果默认待审，词典历史审核状态仅按实际来源继承并留痕 |
| `reviewer` | VARCHAR(64)／可空 | 未建 | `processing_reviews.operator_user_id/operator_label`；登录用户由服务端记录，历史来源标签另存，不假造用户 |
| `reviewed_at` | TIMESTAMP／可空 | 未建 | `processing_reviews.reviewed_at TIMESTAMPTZ`；UTC，绑定被审核内容hash |
| `review_note` | TEXT／可空 | 未建 | `processing_reviews.note TEXT`；保存决定、依据引用及真实核查范围 |
| `notes` | TEXT／可空 | 未建 | 新增 `other_relations.notes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `legacy_payload_json` | TEXT／可空 | 未建 | `processing_artifacts`的受控原始行JSON＋hash；迁移输入快照，非业务唯一查询来源 |

该表基线规则（必须落实或明确本期边界）：

- 包含技能分类、前置、协同、支撑、题目语言点和答案证据六种类型；按类型填写允许字段，其他对象字段留空。
- SKILL_TAXONOMY只用from_skill_id、to_skill_id、role和sort_order；层级相邻、无环，非根节点一个主分类路径。
- 技能前置与支撑为有方向关系；协同按来源ID小于目标ID去重；保留任务条件与理由。三类目前无数据，可以暂不填写。
- QUESTION_LANGUAGE_ITEM填写question_id、language_item_id；正文位置用同篇body segment_id，选项位置用本题option_letter，题干两者均空。
- ANSWER_EVIDENCE填写question_id、evidence_id、sort_order，证据须为同篇正文；同题同证据和链内顺序去重。

## 08_evidence → `evidence_items`

当前未建，T03新增。

| 基线字段 | 基线类型／必填 | 当前代码 | 目标承载与实施处置 |
| --- | --- | --- | --- |
| `evidence_id` | BIGINT／必填 | 未建 | 新增 `evidence_items.id BIGINT`；数据库生成，临时ID统一映射 |
| `passage_id` | BIGINT／必填 | 未建 | 新增 `evidence_items.passage_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `segment_id` | BIGINT／可空 | 未建 | 新增 `evidence_items.segment_id`，按基线类型/枚举；条件必填由该对象规则检查；单句可用该FK，多句用evidence_segments完整有序保存，均限同篇body |
| `start_ms` | INT／必填 | 未建 | 新增 `evidence_items.start_ms`，按基线类型/枚举；条件必填由该对象规则检查 |
| `end_ms` | INT／必填 | 未建 | 新增 `evidence_items.end_ms`，按基线类型/枚举；条件必填由该对象规则检查 |
| `evidence_text` | TEXT／必填 | 未建 | 新增 `evidence_items.evidence_text`，按基线类型/枚举；条件必填由该对象规则检查 |
| `evidence_type` | VARCHAR(32)／必填 | 未建 | 新增 `evidence_items.evidence_type`，按基线类型/枚举；条件必填由该对象规则检查 |
| `source` | VARCHAR(64)／必填 | 未建 | 新增 `evidence_items.source`，按基线类型/枚举；条件必填由该对象规则检查 |
| `created_at` | TIMESTAMP／可空 | 未建 | 新增 `evidence_items.created_at`，按基线类型/枚举；条件必填由该对象规则检查 |
| `collector` | VARCHAR(64)／条件必填 | 未建 | 新增 `evidence_items.collector`，按基线类型/枚举；条件必填由该对象规则检查；系统生成如实记方法/进程来源，不伪填人工姓名 |
| `review_status` | VARCHAR(32)／条件必填 | 未建 | 新增 `evidence_items.review_status`，按基线类型/枚举；条件必填由该对象规则检查；自动结果默认待审，词典历史审核状态仅按实际来源继承并留痕 |
| `reviewer` | VARCHAR(64)／可空 | 未建 | `processing_reviews.operator_user_id/operator_label`；登录用户由服务端记录，历史来源标签另存，不假造用户 |
| `reviewed_at` | TIMESTAMP／可空 | 未建 | `processing_reviews.reviewed_at TIMESTAMPTZ`；UTC，绑定被审核内容hash |
| `review_note` | TEXT／可空 | 未建 | `processing_reviews.note TEXT`；保存决定、依据引用及真实核查范围 |
| `notes` | TEXT／可空 | 未建 | 新增 `evidence_items.notes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `attributes_json` | TEXT／可空 | 未建 | 新增 `evidence_items.attributes_json JSONB`；按表/关系种类校验，原始字符串留产物 |
| `legacy_payload_json` | TEXT／可空 | 未建 | `processing_artifacts`的受控原始行JSON＋hash；迁移输入快照，非业务唯一查询来源 |

该表基线规则（必须落实或明确本期边界）：

- 材料篇章、开始结束时间、英文摘录、推理类型和取得方式必填。
- start_ms < end_ms，时间落在正文范围，不把录音问题作为答案正文依据。
- segment_id如有值，须为同篇body片段；不连续的原文拆成多条证据。
- 答案、技能和候选机制对证据的引用分别通过对应关联分表保存。

## 09_classification_dict → `classification_dicts`

当前未建，T03新增。

| 基线字段 | 基线类型／必填 | 当前代码 | 目标承载与实施处置 |
| --- | --- | --- | --- |
| `classification_id` | BIGINT／必填 | 未建 | 新增 `classification_dicts.id BIGINT`；数据库生成，临时ID统一映射 |
| `dict_kind` | VARCHAR(32)／必填 | 未建 | 新增 `classification_dicts.dict_kind`，按基线类型/枚举；条件必填由该对象规则检查 |
| `classification_code` | VARCHAR(64)／必填 | 未建 | 新增 `classification_dicts.classification_code`，按基线类型/枚举；条件必填由该对象规则检查 |
| `classification_name` | TEXT／必填 | 未建 | 新增 `classification_dicts.classification_name`，按基线类型/枚举；条件必填由该对象规则检查 |
| `definition` | TEXT／必填 | 未建 | 新增 `classification_dicts.definition`，按基线类型/枚举；条件必填由该对象规则检查 |
| `decision_rule` | TEXT／可空 | 未建 | 新增 `classification_dicts.decision_rule`，按基线类型/枚举；条件必填由该对象规则检查 |
| `exclude_rule` | TEXT／可空 | 未建 | 新增 `classification_dicts.exclude_rule`，按基线类型/枚举；条件必填由该对象规则检查 |
| `typical_example` | TEXT／可空 | 未建 | 新增 `classification_dicts.typical_example`，按基线类型/枚举；条件必填由该对象规则检查 |
| `status` | VARCHAR(32)／必填 | 未建 | 新增 `classification_dicts.status`，按基线类型/枚举；条件必填由该对象规则检查 |
| `collector` | VARCHAR(64)／必填 | 未建 | 新增 `classification_dicts.collector`，按基线类型/枚举；条件必填由该对象规则检查；系统生成如实记方法/进程来源，不伪填人工姓名 |
| `review_status` | VARCHAR(32)／必填 | 未建 | 新增 `classification_dicts.review_status`，按基线类型/枚举；条件必填由该对象规则检查；自动结果默认待审，词典历史审核状态仅按实际来源继承并留痕 |
| `reviewer` | VARCHAR(64)／可空 | 未建 | `processing_reviews.operator_user_id/operator_label`；登录用户由服务端记录，历史来源标签另存，不假造用户 |
| `reviewed_at` | TIMESTAMP／可空 | 未建 | `processing_reviews.reviewed_at TIMESTAMPTZ`；UTC，绑定被审核内容hash |
| `review_note` | TEXT／可空 | 未建 | `processing_reviews.note TEXT`；保存决定、依据引用及真实核查范围 |
| `notes` | TEXT／可空 | 未建 | 新增 `classification_dicts.notes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `attributes_json` | TEXT／可空 | 未建 | 新增 `classification_dicts.attributes_json JSONB`；按表/关系种类校验，原始字符串留产物 |
| `legacy_payload_json` | TEXT／可空 | 未建 | `processing_artifacts`的受控原始行JSON＋hash；迁移输入快照，非业务唯一查询来源 |

该表基线规则（必须落实或明确本期边界）：

- GENRE保留6类；叙事、说明、议论、事务交际为启用试标，描写与指导暂不启用。
- GENRE的日常可选值仅含启用试标且非存在分歧的条目；未完成审核应按试标处理。
- 每篇原则上一个主要体裁，按整篇目的与组织方式判断；混合情况、依据、置信程度放第03表。
- 定义与判定条件分别填写；表达目的并入definition，删除重复purpose列。
- typical_example只填已核验真题与原文依据；本次尚未提供该类样本，保持为空。
- 当前字典只保留6种体裁，原细节信息、原因、目的、观点态度、数字整合五项任务分类已删除。
- 保留现有体裁ID、代码和启用状态，审核仍为待复核/存在分歧/已复核。

## 10_error_cause → `error_causes`

当前未建，T03新增。

| 基线字段 | 基线类型／必填 | 当前代码 | 目标承载与实施处置 |
| --- | --- | --- | --- |
| `error_cause_id` | BIGINT／必填 | 未建 | 新增 `error_causes.id BIGINT`；数据库生成，临时ID统一映射 |
| `error_cause_code` | VARCHAR(64)／必填 | 未建 | 新增 `error_causes.error_cause_code`，按基线类型/枚举；条件必填由该对象规则检查 |
| `display_code` | VARCHAR(64)／必填 | 未建 | 新增 `error_causes.display_code`，按基线类型/枚举；条件必填由该对象规则检查 |
| `legacy_codes` | VARCHAR(64)／可空 | 未建 | 新增 `error_causes.legacy_codes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `cause_level` | INT／必填 | 未建 | 新增 `error_causes.cause_level`，按基线类型/枚举；条件必填由该对象规则检查 |
| `parent_error_cause_id` | BIGINT／可空 | 未建 | 新增 `error_causes.parent_error_cause_id`，按基线类型/枚举；条件必填由该对象规则检查 |
| `cause_name` | TEXT／必填 | 未建 | 新增 `error_causes.cause_name`，按基线类型/枚举；条件必填由该对象规则检查 |
| `definition` | TEXT／必填 | 未建 | 新增 `error_causes.definition`，按基线类型/枚举；条件必填由该对象规则检查 |
| `confirmation_rule` | TEXT／条件必填 | 未建 | 新增 `error_causes.confirmation_rule`，按基线类型/枚举；条件必填由该对象规则检查 |
| `display_mapping` | VARCHAR(32)／条件必填 | 未建 | 新增 `error_causes.display_mapping`，按基线类型/枚举；条件必填由该对象规则检查 |
| `boundary_rule` | TEXT／条件必填 | 未建 | 新增 `error_causes.boundary_rule`，按基线类型/枚举；条件必填由该对象规则检查 |
| `remedy_hint` | TEXT／可空 | 未建 | 新增 `error_causes.remedy_hint`，按基线类型/枚举；条件必填由该对象规则检查 |
| `maturity` | VARCHAR(32)／必填 | 未建 | 新增 `error_causes.maturity`，按基线类型/枚举；条件必填由该对象规则检查 |
| `status` | VARCHAR(32)／必填 | 未建 | 新增 `error_causes.status`，按基线类型/枚举；条件必填由该对象规则检查 |
| `collector` | VARCHAR(64)／必填 | 未建 | 新增 `error_causes.collector`，按基线类型/枚举；条件必填由该对象规则检查；系统生成如实记方法/进程来源，不伪填人工姓名 |
| `review_status` | VARCHAR(32)／必填 | 未建 | 新增 `error_causes.review_status`，按基线类型/枚举；条件必填由该对象规则检查；自动结果默认待审，词典历史审核状态仅按实际来源继承并留痕 |
| `reviewer` | VARCHAR(64)／可空 | 未建 | `processing_reviews.operator_user_id/operator_label`；登录用户由服务端记录，历史来源标签另存，不假造用户 |
| `reviewed_at` | TIMESTAMP／可空 | 未建 | `processing_reviews.reviewed_at TIMESTAMPTZ`；UTC，绑定被审核内容hash |
| `review_note` | TEXT／可空 | 未建 | `processing_reviews.note TEXT`；保存决定、依据引用及真实核查范围 |
| `notes` | TEXT／可空 | 未建 | 新增 `error_causes.notes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `attributes_json` | TEXT／可空 | 未建 | 新增 `error_causes.attributes_json JSONB`；按表/关系种类校验，原始字符串留产物 |
| `legacy_payload_json` | TEXT／可空 | 未建 | `processing_artifacts`的受控原始行JSON＋hash；迁移输入快照，非业务唯一查询来源 |

该表基线规则（必须落实或明确本期边界）：

- 三级结构为4个一级问题领域、6个二级分组、12个三级具体错因；父关系只允许1→2、2→3且无环。
- 一级、二级只作目录，候选错因关联仅使用三级节点，不重复选择目录。
- error_cause_code与ID为稳定身份；display_code只作树内展示，合并项保留全部legacy_codes。
- 4.1.1规范名称为题目要求理解偏差；与4.1.2含义匹配偏差、3.1.1信息来源混淆按边界区分。
- 原E2.1/E2.2/E2.3合为语音信息识别困难，仍保留；当前技能树无语音解码，不强配技能。
- E5.3并入E5.1；常识替代只作为经证据支持的具体方式。
- E4.1、E6.1—E6.3、E7.2、E7.3退出主表，去向在说明中保留；当前不新增过程或诊断记录表。
- 本表保存错因定义、条件和边界；题库候选不等于已确认个人错因，无法判断时不强行选择。

## 11_language_item → `language_items`

当前未建，T03新增。

| 基线字段 | 基线类型／必填 | 当前代码 | 目标承载与实施处置 |
| --- | --- | --- | --- |
| `language_item_id` | BIGINT／必填 | 未建 | 新增 `language_items.id BIGINT`；数据库生成，临时ID统一映射 |
| `item_code` | VARCHAR(64)／必填 | 未建 | 新增 `language_items.item_code`，按基线类型/枚举；条件必填由该对象规则检查 |
| `item_type` | VARCHAR(32)／必填 | 未建 | 新增 `language_items.item_type`，按基线类型/枚举；条件必填由该对象规则检查 |
| `item_text` | TEXT／必填 | 未建 | 新增 `language_items.item_text`，按基线类型/枚举；条件必填由该对象规则检查 |
| `lemma` | TEXT／可空 | 未建 | 新增 `language_items.lemma`，按基线类型/枚举；条件必填由该对象规则检查 |
| `sense` | TEXT／必填 | 未建 | 新增 `language_items.sense`，按基线类型/枚举；条件必填由该对象规则检查 |
| `status` | VARCHAR(32)／必填 | 未建 | 新增 `language_items.status`，按基线类型/枚举；条件必填由该对象规则检查 |
| `collector` | VARCHAR(64)／必填 | 未建 | 新增 `language_items.collector`，按基线类型/枚举；条件必填由该对象规则检查；系统生成如实记方法/进程来源，不伪填人工姓名 |
| `review_status` | VARCHAR(32)／必填 | 未建 | 新增 `language_items.review_status`，按基线类型/枚举；条件必填由该对象规则检查；自动结果默认待审，词典历史审核状态仅按实际来源继承并留痕 |
| `reviewer` | VARCHAR(64)／可空 | 未建 | `processing_reviews.operator_user_id/operator_label`；登录用户由服务端记录，历史来源标签另存，不假造用户 |
| `reviewed_at` | TIMESTAMP／可空 | 未建 | `processing_reviews.reviewed_at TIMESTAMPTZ`；UTC，绑定被审核内容hash |
| `review_note` | TEXT／可空 | 未建 | `processing_reviews.note TEXT`；保存决定、依据引用及真实核查范围 |
| `notes` | TEXT／可空 | 未建 | 新增 `language_items.notes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `attributes_json` | TEXT／可空 | 未建 | 新增 `language_items.attributes_json JSONB`；按表/关系种类校验，原始字符串留产物 |
| `legacy_payload_json` | TEXT／可空 | 未建 | `processing_artifacts`的受控原始行JSON＋hash；迁移输入快照，非业务唯一查询来源 |

该表基线规则（必须落实或明确本期边界）：

- item_code唯一；同一词语的不同语境义项允许分行。
- 词、短语、表达、句子与通用技能分别组织；义项不明先待确认。
- 题目与语言点通过07D_other_relation中的QUESTION_LANGUAGE_ITEM关联，正文、题干、选项位置分别记录。

## 12_content_group → `content_groups`

当前已建子集，T03按下表增量扩展。

| 基线字段 | 基线类型／必填 | 当前代码 | 目标承载与实施处置 |
| --- | --- | --- | --- |
| `content_group_id` | BIGINT／必填 | 现有 `id BigInteger`（源码L165） | 复用 `content_groups.id BIGINT`；数据库生成，临时ID统一映射 |
| `content_group_code` | VARCHAR(64)／必填 | 现有 `content_group_code String(64)`（源码L169） | 复用 `content_groups.content_group_code`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `group_name` | TEXT／必填 | 现有 `group_name String(255)`（源码L170） | 现有VARCHAR(255)目标扩展TEXT；模块三group_name非空字符串 |
| `exam_level_scope` | VARCHAR(32)／必填 | 现有 `exam_level_scope String(16)`（源码L171） | 复用 `content_groups.exam_level_scope`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `basis_paper_id` | BIGINT／可空 | 未建 | 新增 `content_groups.basis_paper_id` 可空FK，本期有值须为本套来源卷 |
| `equivalence_basis` | TEXT／可空 | 未建 | 新增 `content_groups.equivalence_basis`，按基线类型/枚举；条件必填由该对象规则检查 |
| `content_fingerprint` | VARCHAR(64)／可空 | 现有 `content_fingerprint String(64)`（源码L172） | 复用 `content_groups.content_fingerprint`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `status` | VARCHAR(32)／必填 | 未建 | 新增 `content_groups.status`，按基线类型/枚举；条件必填由该对象规则检查 |
| `collector` | VARCHAR(64)／必填 | 现有 `collector String(64)`（源码L173） | 复用 `content_groups.collector`；补基线枚举/必填/来源检查，保持既有接口字段语义；系统生成如实记方法/进程来源，不伪填人工姓名 |
| `review_status` | VARCHAR(32)／必填 | 现有 `review_status String(32)`（源码L176） | 复用 `content_groups.review_status`；补基线枚举/必填/来源检查，保持既有接口字段语义；自动结果默认待审，词典历史审核状态仅按实际来源继承并留痕 |
| `reviewer` | VARCHAR(64)／可空 | 未建 | `processing_reviews.operator_user_id/operator_label`；登录用户由服务端记录，历史来源标签另存，不假造用户 |
| `reviewed_at` | TIMESTAMP／可空 | 未建 | `processing_reviews.reviewed_at TIMESTAMPTZ`；UTC，绑定被审核内容hash |
| `review_note` | TEXT／可空 | 未建 | `processing_reviews.note TEXT`；保存决定、依据引用及真实核查范围 |
| `notes` | TEXT／可空 | 未建 | 新增 `content_groups.notes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `attributes_json` | TEXT／可空 | 未建 | 新增 `content_groups.attributes_json JSONB`；按表/关系种类校验，原始字符串留产物 |
| `legacy_payload_json` | TEXT／可空 | 未建 | `processing_artifacts`的受控原始行JSON＋hash；迁移输入快照，非业务唯一查询来源 |

该表基线规则（必须落实或明确本期边界）：

- content_group_code唯一；一个内容组代表一整套可共享听力内容。
- 多套原卷可引用同组，basis_paper_id只记录来源线索。
- 内容等价须有真实依据；不单凭文件名或文件哈希判断语义相同。

## 13_presentation → `presentations`

当前已建子集，T03按下表增量扩展。

| 基线字段 | 基线类型／必填 | 当前代码 | 目标承载与实施处置 |
| --- | --- | --- | --- |
| `presentation_id` | BIGINT／必填 | 现有 `id BigInteger`（源码L319） | 复用 `presentations.id BIGINT`；数据库生成，临时ID统一映射 |
| `question_id` | BIGINT／必填 | 现有 `question_id BigInteger`（源码L326） | 复用 `presentations.question_id`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `exam_paper_id` | BIGINT／必填 | 现有 `exam_paper_id BigInteger`（源码L323） | 复用 `presentations.exam_paper_id`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `question_no` | INT／可空 | 现有 `question_no Integer`（源码L329） | 复用 `presentations.question_no`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `option_mapping_state` | VARCHAR(32)／可空 | 现有 `option_mapping_state String(16)`（源码L330） | 复用 `presentations.option_mapping_state`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `mapping_source` | TEXT／可空 | 现有 `mapping_source Text`（源码L333） | 复用 `presentations.mapping_source`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `created_at` | TIMESTAMP／可空 | 现有 `created_at DateTime(timezone=True)`（源码L341） | 复用 `presentations.created_at`；补基线枚举/必填/来源检查，保持既有接口字段语义 |
| `collector` | VARCHAR(64)／必填 | 现有 `collector String(64)`（源码L335） | 复用 `presentations.collector`；补基线枚举/必填/来源检查，保持既有接口字段语义；系统生成如实记方法/进程来源，不伪填人工姓名 |
| `review_status` | VARCHAR(32)／必填 | 现有 `review_status String(32)`（源码L338） | 复用 `presentations.review_status`；补基线枚举/必填/来源检查，保持既有接口字段语义；自动结果默认待审，词典历史审核状态仅按实际来源继承并留痕 |
| `reviewer` | VARCHAR(64)／可空 | 未建 | `processing_reviews.operator_user_id/operator_label`；登录用户由服务端记录，历史来源标签另存，不假造用户 |
| `reviewed_at` | TIMESTAMP／可空 | 未建 | `processing_reviews.reviewed_at TIMESTAMPTZ`；UTC，绑定被审核内容hash |
| `review_note` | TEXT／可空 | 未建 | `processing_reviews.note TEXT`；保存决定、依据引用及真实核查范围 |
| `notes` | TEXT／可空 | 未建 | 新增 `presentations.notes`，按基线类型/枚举；条件必填由该对象规则检查 |
| `attributes_json` | TEXT／可空 | 未建 | 现有 `option_letter_mapping JSONB`承载A—D映射；其余白名单属性新增 `attributes_json JSONB`，解析并校验 |
| `legacy_payload_json` | TEXT／可空 | 未建 | `processing_artifacts`的受控原始行JSON＋hash；迁移输入快照，非业务唯一查询来源 |

该表基线规则（必须落实或明确本期边界）：

- exam_paper_id与question_id组合唯一；已知的question_no在同卷唯一。
- 原卷与题目必须属于同一听力内容组。
- 题号或选项顺序未知时如实留空或标未知，不复制基准卷顺序充当目标卷事实。
- 保留原卷题号及选项顺序状态；重排对应关系放本表现有attributes_json.option_letter_mapping，键为该原卷A—D，值为题目表基准A—D。
- 例如原卷A对应题目表C，记录{"option_letter_mapping":{"A":"C"}}；未知字母映射不填，不默认相同。已知的完整映射应覆盖A—D且值不重复。

## 系统增量、约束与审计承载

| 增量对象 | 关键字段和约束 | 对应任务／验收 |
| --- | --- | --- |
| batch_paper_metadata | batch_id唯一FK；本套content_group_id、绑定/题号/选项状态、等价依据；不得待审时写稳定试卷当前元数据 | T03/T11/T12；A20/A25/A26 |
| batch_audio_groups | (batch_id,audio_id,content_group_id)唯一；同批次组归属，原音和组均真实存在；不展开跨卷共享 | T03/T11；A20/A21 |
| dictionary_snapshots | 固定schema及数据hash；稳定码与旧码映射；词典重新导入幂等 | T01/T03；A20/A21 |
| material_sources及batch_source_refs | 来源登记；按task/batch和对象src_id保存材料、页码、框/字符、原解析文本及转换hash；新来源只追加 | T04/T08/T11；A01/A15/A32 |
| processing_tasks/artifacts | 独立持久任务、租约、阶段结果、异常及hash；失败可无业务batch | T05/T11；A05—A08/A25 |
| evidence_segments | evidence、batch、passage、segment、sort_order、字符范围；复合FK和连续body句规则 | T03/T09/T10；A18/A19/A21 |
| processing_reviews/corrections | 每次修订/复核对象、前后内容、result_hash、真实操作者、UTC时间与来源；初稿不可改 | T10；A32/A33/A36 |
| batch_activation_logs | 旧/新batch、目标task/check/result_hash、操作者和时间；切换与visibility审计分开 | T12；A26/A36 |
| import_batches增量 | 完整result_fingerprint及同卷唯一、profile/check版本；保留one_current部分唯一索引 | T03/T11/T12；A24/A26/A36 |
| content_checks增量 | result_hash、规则版本、检查profile；新修订必须重新检查，旧检查不能批准不同hash；读请求按同batch一致取数 | T03/T10/T12；A26/A32/A36 |

关系类表另加：同批次/快照内relation_code与revision_no唯一；同一逻辑relation_code至多一条is_current；owner证据关系同owner/evidence与sort_order分别去重。新增关系的当前修订不能与试卷当前批次混为一谈。07A导入仅复用既有ERROR_SKILL，非模型逐卷重建。

## 按关系种类冻结条件检查

以下直接列出确认JSON的rulesByKind。每种关系必须同时检查必填、允许对象字段、属性白名单、对应字典和批次/篇章归属；其余对象字段必须为空。

| relation_kind | 必需字段 | 允许对象字段 | 允许属性 |
| --- | --- | --- | --- |
| `SKILL_TAXONOMY` | `from_skill_id`, `to_skill_id`, `role`, `sort_order` | `from_skill_id`, `to_skill_id` | `display_path`, `rationale` |
| `SKILL_PREREQUISITE` | `from_skill_id`, `to_skill_id` | `from_skill_id`, `to_skill_id` | `condition_key`, `task_condition`, `rationale`, `strength`, `source`, `valid_from`, `valid_to` |
| `SKILL_CO_USE` | `from_skill_id`, `to_skill_id` | `from_skill_id`, `to_skill_id` | `condition_key`, `task_condition`, `rationale`, `strength`, `source`, `valid_from`, `valid_to` |
| `SKILL_SUPPORT` | `from_skill_id`, `to_skill_id` | `from_skill_id`, `to_skill_id` | `condition_key`, `task_condition`, `rationale`, `strength`, `source`, `valid_from`, `valid_to` |
| `QUESTION_SKILL` | `question_id`, `skill_id`, `role` | `question_id`, `skill_id` | `annotation_reason`, `annotation_source`, `confidence`, `legacy_tag_code` |
| `ERROR_SKILL` | `error_cause_id`, `skill_id` | `error_cause_id`, `skill_id` | `relation_nature`, `rationale`, `candidate_scope`, `selection_rule` |
| `QUESTION_ERROR_CANDIDATE` | `question_id`, `error_cause_id` | `question_id`, `error_cause_id`, `option_letter` | `trigger_mechanism`, `annotation_source`, `candidate_priority` |
| `QUESTION_LANGUAGE_ITEM` | `question_id`, `language_item_id` | `question_id`, `language_item_id`, `segment_id`, `option_letter` | `location_type`, `context_text`, `note` |
| `ANSWER_EVIDENCE` | `question_id`, `evidence_id`, `sort_order` | `question_id`, `evidence_id` | `support_note` |
| `SKILL_EVIDENCE` | `owner_relation_id`, `evidence_id`, `sort_order` | `owner_relation_id`, `evidence_id` | `relation_type`, `support_note` |
| `CANDIDATE_EVIDENCE` | `owner_relation_id`, `evidence_id`, `sort_order` | `owner_relation_id`, `evidence_id` | `support_note` |

## 差异验收与回填

本文件覆盖16张业务表，共304个基线字段条目；同名字段在不同表分别核对。当前列判断来自源码静态比对；新增设计尚未建表。

T03实施后逐行回填物理列/审计对象、Alembic revision、真实DDL类型/约束、读写入口、空值/枚举/归属测试和证据路径。原有同名列也要检查数据库类型/长度/约束与业务读取行为，不能只凭名称判断全部对齐。验收状态只用PASS/PARTIAL/FAIL/BLOCKED；本轮运行结论为BLOCKED（仅文档）。
