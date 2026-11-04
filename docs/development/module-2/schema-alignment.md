# 模块二表结构与 16 表基线逐字段比对（2026-11-03）

- 基线文件：`schema_options_merged_16tables.json`（SHA-256 `6348030d2b5acb49e0cf036487f4ddd508428f33b0033e5cfb4261d40a986580`，318,618 字节，生成日期 2026-10-24）
- 采集试填：`2025年6月四级第一套_听力采集试填_16表版_20261024.xlsx`（SHA-256 `23b62693ef7df7a033bdd3f7b2d3c0f10c8f70d1c6cf4c5a75846daad9368118`，与本次导入所用的文件**完全一致**，数据无需重导）
- 实现：`backend/app/db/models_listening.py`、`backend/alembic/versions/0002_module2_listening_papers.py`
- 结论：**7 张业务表逐字段对齐完成**（字段名、类型、枚举取值全部沿用基线）；9 张词典/标注/关系表按「最小业务子集」审核意见不在本期建立，理由见第 4 节。

---

## 1. 表对应关系

| 基线表 | 本期表 | 说明 |
| --- | --- | --- |
| `exam_paper` | `exam_papers` | 表名复数遵循仓库 `docs/development/naming-conventions.md` |
| `audio` | `audio_files` | 同上；`audio` 是保留词，加 `_files` 更清晰 |
| `passage` | `passages` | |
| `transcript_segment` | `transcript_segments` | |
| `question` | `questions` | |
| `content_group` | `content_groups` | |
| `presentation` | `presentations` | |
| — | `import_batches` | 系统记录，基线无（批次/当前版本） |
| — | `content_checks` | 系统记录，基线无（最低内容检查） |
| — | `paper_visibility` | 系统记录，基线无（学生可见性） |
| — | `visibility_audit_logs` | 系统记录，基线无（可见性操作记录） |
| `skill` / `error_cause` / `evidence` / `classification_dict` / `language_item` | 未建 | 见第 4 节 |
| `07A`~`07D` 四张关系表 | 未建 | 见第 4 节 |

> **主键命名差异（有意为之）**：基线用 `question_id` / `audio_id` / `segment_id` 作为各自主键名；本仓库 `docs/development/naming-conventions.md` 统一要求主键叫 `id`、外键叫 `<实体>_id`。本期沿用仓库约定，因此 `transcript_segments` 的主键是 `id`，而 `questions.question_segment_id` 指向它——语义与基线的 `question_segment_id → transcript_segment.segment_id` 完全等价。

---

## 2. 逐字段比对结果

### 2.1 `exam_paper` → `exam_papers`（基线 22 字段）

| 基线字段 | 本期列 | 状态 |
| --- | --- | --- |
| `exam_paper_code` | `exam_paper_code` VARCHAR(64) | 一致 |
| `exam_level` | `exam_level` VARCHAR(32) | 类型已对齐（原 VARCHAR(16) 已放宽） |
| `exam_year` / `exam_month` / `paper_set` | 同名 INT | 一致 |
| `source` | `source` TEXT | **本次新增**，导入写入来源说明 |
| — | `expected_question_count` INT | **本期扩展（基线无）**：该套选定原卷的应有题量，首次导入固定，用于发现「末尾整题缺失」；见验收报告 F02 |
| `playback_audio_id` | `playback_audio_id` | 一致 |
| `mapping_source` | `mapping_source` TEXT | **本次新增**，导入写入原卷路径 |
| `collector` | `collector` VARCHAR(64) | **本次新增**，本套为 `ljt` |
| `review_status` | `review_status` VARCHAR(32)，CHECK 限定四值 | **本次新增**，本套为 `待审核` |
| `content_group_id` | 未建 | 见 2.8 |
| `binding_state` / `question_order_state` / `option_order_state` / `equivalence_basis` | 未建 | 试卷级绑定与顺序状态摘要，本期由 `presentations.option_mapping_state` + 检查结果表达；待多卷等价绑定需求出现时补 |
| `reviewer` / `reviewed_at` / `review_note` / `notes` | 未建 | 本期无人执行审核，只保留 `review_status` 状态位；人工审核落库随 B16 一起补 |
| `attributes_json` / `legacy_payload_json` | 未建 | 迁移审计包，采集阶段用；入库后不再需要 |

### 2.2 `audio` → `audio_files`（基线 21 字段）

| 基线字段 | 本期列 | 状态 |
| --- | --- | --- |
| `audio_code` / `storage_provider` / `storage_key` / `duration_ms` / `format` / `file_hash` / `is_current` | 同名 | 一致（`format` 取值 m4a 等，与基线枚举一致） |
| `version_no` | `version_no` INT 默认 1 | **本次新增**，本套 `1` |
| `variant_type` | `variant_type` VARCHAR(32) 默认 `原始` | **本次新增**，本套 `原始` |
| `collector` / `review_status` | 同名 + CHECK | **本次新增**，本套 `ljt` / `待审核` |
| — | `mime_type` VARCHAR(64) | **本期扩展**：基线靠 `format` 推断，接口要设 `Content-Type`，显式存 `audio/mp4` |
| `content_group_id` / `source_paper_id` / `derived_from_audio_id` | 未建 | 内容组共享与派生链，模块三多版本音频时补 |
| `reviewer` / `reviewed_at` / `review_note` / `notes` / `attributes_json` / `legacy_payload_json` | 未建 | 同 2.1 |

### 2.3 `passage` → `passages`（基线 24 字段）

| 基线字段 | 本期列 | 状态 |
| --- | --- | --- |
| `passage_code` / `passage_index` / `passage_type` / `start_ms` / `body_end_ms` / `end_ms` / `speaker_count` | 同名 | 一致（`passage_type` 取值沿用中文原值：短篇新闻/长对话/听力篇章…） |
| `topic` | `topic` TEXT | 类型已对齐（原 VARCHAR(255) 已放宽） |
| `scene` | `scene` TEXT | **本次新增**，本套「新闻播报」 |
| `accent` | `accent` VARCHAR(32) 默认 `未判定` | **本次新增**，本套「未判定」（未做口音标注就不猜） |
| `collector` / `review_status` | 同名 + CHECK | **本次新增** |
| — | `batch_id` / `exam_paper_id` / `audio_id` | **本期扩展**：内容随批次版本化（B09 需要） |
| `genre_id` / `genre_note` / `genre_confidence` / `genre_review_status` | 未建 | 依赖 `classification_dict` 体裁词典，随模块三标注一起建 |
| `reviewer` / `reviewed_at` / `review_note` / `notes` / `attributes_json` / `legacy_payload_json` | 未建 | 同 2.1 |

### 2.4 `transcript_segment` → `transcript_segments`（基线 16 字段）

| 基线字段 | 本期列 | 状态 |
| --- | --- | --- |
| `segment_index` / `text` / `segment_type` / `start_ms` / `end_ms` | 同名 | 一致（`segment_type` 为 body/question，与基线枚举一致） |
| `speaker_code` | `speaker_code` VARCHAR(64) | 类型已对齐（原 VARCHAR(8) 已放宽） |
| `collector` / `review_status` | 同名 + CHECK | **本次新增** |
| `passage_id` | `passage_id` | 一致（指向 `passages.id`） |
| — | `batch_id` | **本期扩展**：版本化 |
| `reviewer` / `reviewed_at` / `review_note` / `notes` / `attributes_json` / `legacy_payload_json` | 未建 | 同 2.1 |

### 2.5 `question` → `questions`（基线 22 字段）

| 基线字段 | 本期列 | 状态 |
| --- | --- | --- |
| `question_code` / `question_text` / `option_a`~`option_d` / `correct_option` / `explanation_text` / `passage_id` / `question_segment_id` | 同名 | 一致；`correct_option` 保留 A–D CHECK |
| `question_index` | `question_index` INT | **本次新增**，本套 1–25（来源卷全卷题号，与目标卷题号分开记） |
| `content_state` | `content_state` VARCHAR(32) 默认 `待补齐`，CHECK 限定 待补齐/可用/停用 | **本次新增**，本套 25 题全部 `可用`；已接入最低内容检查（非可用则拒绝确认可见） |
| `collector` / `review_status` | 同名 + CHECK | **本次新增**，本套 `待审核` |
| `source_paper_id` | 未建 | 与 `exam_papers` 一对一场景下冗余；多卷共享题目时再补 |
| — | `explanation_source` VARCHAR(255) | **本期扩展**：记录解析来自哪份答案解析 PDF |
| — | `batch_id` | **本期扩展**：版本化 |
| `reviewer` / `reviewed_at` / `review_note` / `notes` / `attributes_json` / `legacy_payload_json` | 未建 | 同 2.1 |

### 2.6 `content_group` → `content_groups`（基线 17 字段）

| 基线字段 | 本期列 | 状态 |
| --- | --- | --- |
| `content_group_code` / `group_name` / `exam_level_scope` / `content_fingerprint` | 同名 | 一致 |
| `collector` / `review_status` | 同名 + CHECK | **本次新增** |
| — | `batch_id` | **本期扩展**：内容组随批次记录 |
| `basis_paper_id` / `equivalence_basis` / `status` | 未建 | 多卷共享等价关系的判定依据，本期只有一套卷，无共享场景 |
| `reviewer` / `reviewed_at` / `review_note` / `notes` / `attributes_json` / `legacy_payload_json` | 未建 | 同 2.1 |

### 2.7 `presentation` → `presentations`（基线 17 字段）

| 基线字段 | 本期列 | 状态 |
| --- | --- | --- |
| `question_id` / `exam_paper_id` / `question_no` | 同名 | 一致 |
| `option_mapping_state` | 同名 VARCHAR(16)，默认 `未知`，取值 已知/部分已知/未知 | **取值已对齐**（原默认值误用英文 `unknown`，本次改为中文原值） |
| `mapping_source` | `mapping_source` TEXT | 类型已对齐（原 VARCHAR(255)） |
| `collector` / `review_status` | 同名 + CHECK | **本次新增** |
| — | `option_letter_mapping` JSONB | **本期扩展**：从 `attributes_json` 抽出的恒等映射，接口据此排选项 |
| — | `batch_id` | **本期扩展**：版本化 |
| `created_at` / `reviewer` / `reviewed_at` / `review_note` / `notes` / `attributes_json` / `legacy_payload_json` | 部分未建 | `created_at` 有；其余同 2.1 |

### 2.8 未建的外键关系（有意留空）

基线的内容组共享模型是：`audio.content_group_id` 与 `exam_paper.content_group_id` 都指向 `content_group`，一套听力内容可被多套卷复用。

本期只有一套卷、一个内容组，没有共享场景；而 `content_groups.batch_id → import_batches.exam_paper_id` 已经能定位归属。若此时再加 `exam_papers.content_group_id`，会形成 `exam_papers ↔ content_groups ↔ import_batches` 的循环外键，收益为零、删除顺序变复杂。

**结论**：内容组共享关系待模块三做「同内容多卷复用」时补齐，届时同时补 `equivalence_basis` 与 `basis_paper_id`。

---

## 3. 枚举取值对齐

| 字段 | 基线取值 | 本期实现 |
| --- | --- | --- |
| `exam_level` | CET4, CET6 | 一致 |
| `content_scope` | listening | 一致 |
| `segment_type` | body, question | 一致 |
| `correct_option` | A, B, C, D | 一致（CHECK） |
| `content_state` | 待补齐, 可用, 停用 | 一致（CHECK） |
| `review_status` | 待审核, 需修改, 待确认, 已通过 | 一致（CHECK） |
| `option_mapping_state` | 已知, 部分已知, 未知 | **本次由 `unknown` 改为 `未知`** |
| `passage_type` | 短篇新闻, 长对话, 听力篇章, 讲话, 报道, 讲座, 其他 | 存 String 不硬转英文，与基线中文原值一致 |
| `accent` | 英式, 美式, 混合, 其他, 未判定 | **本次新增**，本套未标注记 `未判定` |
| `variant_type` | 原始, 剪辑, 降噪, 转码 | **本次新增**，本套 `原始` |
| `status`（批次） | 基线无 | 本期自定义 `pending/active/failed`，属系统记录 |
| `action`（可见性） | 基线无 | 本期自定义 `confirm/cancel`，属系统记录 |

---

## 4. 未建的 9 张表及理由

| 表 | 为什么本期不建 |
| --- | --- |
| `skill`（技能节点，24 项三级技能） | 技能树是模块三标注与后续专项诊断的输入，展示链路不用；建了也没有可信数据可填 |
| `classification_dict`（体裁字典） | 同上，`passages.genre_id` 依赖它 |
| `error_cause`（三级错因树） | 错因标注属模块三 |
| `language_item`（语言点） | 同上 |
| `evidence`（原文证据） | 证据引用用于错因/技能标注，模块三产出 |
| `07A skill_error_relation` | 技能—错因关系，模块三 |
| `07B error_question_relation` | 错因—题目与证据关系，模块三 |
| `07C skill_question_relation` | 技能—题目与证据关系，模块三 |
| `07D other_relation` | 技能层级/先修/共现等关系，模块三 |

审核结论第 2 项已明确「本期只建最小业务子集」，以上 9 张表在模块三接入时按基线补齐，届时不改已建 7 张业务表的字段语义。

---

## 5. 本次比对带来的实际改动

1. **新增 14 个字段**：`exam_papers.source/mapping_source/collector/review_status`；`audio_files.version_no/variant_type/collector/review_status`；`passages.scene/accent/collector/review_status`；`transcript_segments.collector/review_status`；`questions.question_index/content_state/collector/review_status`；`content_groups.collector/review_status`；`presentations.collector/review_status`。
2. **类型放宽 5 处**：`exam_level` 16→32、`topic` 255→TEXT、`speaker_code` 8→64、`mapping_source` 255→TEXT、`segment_type` 16→32。
3. **枚举修正 1 处**：`option_mapping_state` 默认值 `unknown` → `未知`。
4. **新增 CHECK 7 个**：6 张内容表 + `questions.content_state` 的取值约束。
5. **业务规则收紧 1 条**：`content_state != '可用'` 的题目进入最低内容检查问题清单，`confirm` 直接 400 拒绝。实测：把第 1 题改为 `待补齐` → 确认可见返回 `400 最低内容检查未通过，不能确认可见：题目 CET4_2025_06_1_Q01 内容完整度为「待补齐」`；改回 `可用` → 200。
6. **数据诚实性固化**：导入工具把本套 25 题的 `review_status` 全部写为 `待审核`、`collector` 写为「人工整理导入（试填数据，未经人工核听）」。数据库里能直接看出这批数据**没有**经过人工审核，避免 B16 被误判为已通过。

## 6. 复验结果（改动后重跑）

| 项 | 结果 |
| --- | --- |
| 迁移 `upgrade head`（重建库） | 通过，11 张新表 16 张合计 |
| 导入 | 1 卷 / 1 音频 / 1 批次 / 1 内容组 / 8 篇章 / 165 片段 / 25 题 / 25 映射 |
| 新字段落库 | `content_state=可用`×25、`review_status=待审核`×25、`question_index` 1–25、`scene=新闻播报`、`accent=未判定`、`version_no=1`、`variant_type=原始`、`collector=ljt` |
| 模块二端到端验收 | 16/16 |
| pytest | 18 passed |
| 管理员配套接口 | 已返回 `review_status` / `content_state` / `question_index` / `scene` / `accent` |

## 题量来源扩展（0004）

新增 `exam_papers.expected_question_count_source`（JSONB，可空）保存独立原卷题量依据，与应有题量配套；基线16表无该字段，属于本期完整性检查系统扩展。无来源时不能开放。升级使0003按实际题数回填的基准失效，保留原内容、账号和操作历史。
