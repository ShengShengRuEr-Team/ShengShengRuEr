# 错题本 API

接口前缀为 `/api/v1/wrong-answers`。所有请求均需学生 Bearer token。未登录返回
401，非学生返回 403。试卷须在查询时满足模块二学生访问条件。下线试卷不参与列表
和总数，详情与状态操作统一返回 404。其他学生的记录也返回 404。错题本接口响应使用
`Cache-Control: no-store`。

| 方法 | 相对路径 | 行为 |
| --- | --- | --- |
| GET | 空 | 返回 `data.items`、`data.total` 和 `data.state_writes_enabled`。支持 `page`（默认 1）、`limit`（默认 20，范围 1–50）、`exam_paper_id`、`answer_type`（`incorrect` 或 `unanswered`）、`learning_status`（`pending` 或 `mastered`）及 `visibility`（`visible` 默认仅未隐藏，`hidden` 仅已隐藏，`all` 含两者）。按交卷时间倒序，同次按题号升序。总数和分页行使用同条 SQL、相同过滤条件。非法、重复或未知筛选参数返回 422。 |
| GET | `/{attempt_code}/{question_no}` | 仅查看本人未隐藏且当前可访问的错题。已隐藏时返回 404，恢复后按权限访问。详情门禁关闭时返回 503。获准开放后返回交卷时的题干、选项、作答、正确答案、获准的解析、快照提示、公开标注字段和可用的音频入口。 |
| PATCH | `/{attempt_code}/{question_no}` | 修改 `learning_status`、`is_hidden` 或两者。至少传一个字段。返回与列表同结构的更新结果。管理暂未开放时返回 503。 |

列表项和状态更新响应仅包含 `attempt_code`、`exam_paper_id`、`question_no`、
`paper_title`、`submitted_at`、`answer_type`、`learning_status`、`is_hidden`、
`updated_at` 和 `reviewed_at`。页面按卷名、原卷题号、作答类型和时间识别错题。
题干、选项、学生所选字母、正确答案、解析和标注只从获准的详情返回。

每条错题对应一次成功提交中的一题。错题存在性由提交事务保存的逐题判分快照直接派生。
客户端超时不影响事务结果，同键重试不重复归集，部署前的提交也可读取。未作答沿用
判分规则归集。每条记录初始为待复习、未隐藏。状态字段包含 `learning_status`、
`is_hidden`、`updated_at` 和 `reviewed_at`。首次标记已掌握写入 `reviewed_at`，
回到待复习时清空。隐藏和恢复保留掌握状态及掌握时间。只合并 PATCH 提供的字段，
实际状态变化才刷新 `updated_at`。同值更新不刷新时间。尚无状态变更时，`updated_at`
采用交卷时间。原始作答、成绩和判分快照继续保留。

## 详情与证据

题干、选项、正确答案和获准返回的解析使用原交卷快照。标注从原作答批次读取。有效标注须与
该批次的审核结果、规则版本和词典条目相符。候选错因按当次原卷选项映射至题库选项，
并以原卷字母显示。未作答时候选错因为空。个人错因确认状态为 `unconfirmed`。
前端使用 `annotation_source_note` 提示标注来源和时间，使用 `annotation_note`
区分候选错因与个人已确认的错因。

`annotation_reviewed_at` 是已展示标注对应审核会话的提交时间，采用带时区的 ISO 8601
字符串。没有可展示的标注或没有可核验的审核时间时为 `null`。页面展示实际审核时间，
审核人、审核会话 ID 和内部审核记录仅在服务端使用。

学生响应中的标注字段限公开编码、名称、技能角色或关联原卷选项，以及
技能词典 `definition` 或候选词典 `basis_summary`。只有通过证据规则的关联
才投影，`evidence_status` 固定为 `restricted`。无可展示的标注时，
详情 `evidence_access` 为 `none`，有标注为 `restricted`。原文、片段、
时间轴、逐题标注理由和内部备注均不返回。

### 历史解析

| `explanation_status` | `explanation_text` | `has_explanation` |
| --- | --- | --- |
| `available` | 原交卷解析正文，逐字保留 | `true` |
| `missing` | `null`（原值为空或仅含空白） | `false` |
| `restricted` | `null`（存在解析且缺少有效、精确匹配的放行） | `false` |

受保护详情开放后，服务按 `WRONG_ANSWERS_EXPLANATION_APPROVALS_FILE` 读取运营方
维护的 UTF-8 JSON 数组。配置采用只读绝对路径，批准记录来自内容治理负责人。
记录须包含以下字段：

- `purpose` 为 `student_wrong_answer_detail`，`field` 为 `explanation_text`。
- `import_batch_id`、`attempt_answer_id` 均为正整数，`sha256` 为原解析 UTF-8
  字节的 64 位小写十六进制哈希。
- `decision` 为 `approved`、`denied` 或 `revoked`。
- `reviewer` 和 `decision_ref` 分别记录签认人和可追溯审批出处。
- `decided_at` 为带时区的 ISO 8601 时间。`expires_at` 可省略或为同格式时间。

只有匹配来源批次、逐题快照身份及内容哈希的**唯一有效批准**返回正文。缺文件、
解析失败、审批冲突、未来生效、撤回、过期和哈希不匹配均不给出解析正文。现行题库
解析获批无法放行内容不同的旧快照。审批清单及哈希不进入学生响应或仓库。撤销时
由运营方原子替换清单或删除对应授权，新请求立即按更新后的记录校验。

### 受控音频

`audio` 包含 `status` 和 `url`。当前活动批次等于交卷来源、且批次音频绑定
及文件均可用时，`status=available`，`url` 为模块二学生音频相对地址并带
`expected_batch_id`。同批次无可用媒体时返回 `missing` 和空 URL。已经换批
或只剩来源无法确认的卷级回退绑定时返回 `batch_mismatch` 和空 URL。

音频接口实时校验准入和批次，支持 Range。详情打开后换批（409）或音频请求
返回 404 时，页面清空详情和播放资源，再重新核对详情。重新校验成功时显示
新结果或媒体不可用提示。卷已下线时显示错题不可查看。学生答题接口沿用模块二
原有音频契约。

## 发布与迁移

服务端开关默认关闭。在部署环境启用前核对对应的团队签认。

- `WRONG_ANSWERS_STATE_WRITES_ENABLED` 对应 WB-D02，控制复习状态、隐藏和恢复操作。
- `WRONG_ANSWERS_PROTECTED_DETAILS_ENABLED` 对应 WB-D05。启用前须具备正式签认，并确认 P1/P6 或等价放行条件。历史解析另按审批清单逐项核验。

`0012_wrong_answer_review_state` 将历史移出记录迁移为「已隐藏、待复习」。回退到
`0011_wrong_answer_notebook` 时保留已隐藏记录，复习状态及复习时间会丢失。回退前
应按照项目流程备份状态数据。

`0013_wrong_answer_state_times` 增加 `updated_at`。已有状态以创建时间和原复习
时间的较晚者回填，待复习记录的 `reviewed_at` 清空。降回 0012 会移除新增时间列，
保留已归一化的掌握状态、隐藏标志和原始作答。回退应用和迁移前保持受保护详情关闭。
