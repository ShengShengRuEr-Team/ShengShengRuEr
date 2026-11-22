# 错题本 API

接口前缀为 `/api/v1/wrong-answers`。所有请求均需学生 Bearer token。未登录返回
401，非学生返回 403。试卷须在查询时满足模块二学生访问条件。下线试卷不参与列表
和总数，详情与状态操作统一返回 404。其他学生的记录也返回 404。错题本接口响应使用
`Cache-Control: no-store`。

| 方法 | 相对路径 | 行为 |
| --- | --- | --- |
| GET | 空 | 返回 `data.items`、`data.total` 和 `data.state_writes_enabled`。支持 `page`、`limit`（默认 20，最大 100）、`exam_paper_id`、`answer_type`（`incorrect` 或 `unanswered`）、`learning_status`（`pending` 或 `mastered`）和 `visibility`（默认 `visible`，`hidden` 查已隐藏）。按交卷时间倒序，同次按题号升序。 |
| GET | `/{attempt_code}/{question_no}` | 只允许查看本人可见错题。详情暂未开放时返回 503。获准开放后返回交卷时的题干、选项、作答、正确答案、解析、快照提示、公开标注字段和可用的音频入口。 |
| PATCH | `/{attempt_code}/{question_no}` | 修改 `learning_status`、`is_hidden` 或两者。至少传一个字段。返回更新后的列表项。管理暂未开放时返回 503。 |

每条错题对应一次成功提交中的一题。列表从已保存的逐题判分快照实时派生，同时覆盖
功能上线前的提交。未作答沿用判分规则归集，并可按作答类型筛选。列表项包含
`exam_paper_id`、`learning_status`、`is_hidden`、`reviewed_at`，初始状态为待复习。
仅隐藏或恢复会保留上次复习状态。原始作答、成绩和判分快照继续保留。

## 详情与证据

题干、选项、正确答案和解析使用原交卷快照。标注从原作答批次读取。有效标注须与
该批次的审核结果、规则版本和词典条目相符。候选错因按当次原卷选项映射至题库选项，
并以原卷字母显示。未作答时候选错因为空。个人错因确认状态为 `unconfirmed`。

学生响应中的标注字段限公开编码、名称、技能角色或关联原卷选项，以及
`has_restricted_evidence`。该布尔值只表示存在受限依据。原文、片段、时间轴、
理由和内部备注均不返回。音频使用模块二学生接口及当前整卷绑定，带当前批次参数以
避免访问返回详情之后发生换批的音频。

## 发布与迁移

服务端开关默认关闭。在部署环境启用前核对对应的团队签认。

- `WRONG_ANSWERS_STATE_WRITES_ENABLED` 对应 WB-D02，控制复习状态、隐藏和恢复操作。
- `WRONG_ANSWERS_PROTECTED_DETAILS_ENABLED` 对应 WB-D05。启用前需确认受保护详情及解析内容的 P1/P6 或等价放行条件。

`0012_wrong_answer_review_state` 将历史移出记录迁移为「已隐藏、待复习」。回退到
`0011_wrong_answer_notebook` 时保留已隐藏记录，复习状态及复习时间会丢失。回退前
应按照项目流程备份状态数据。
