# 作答系统接口契约（API-1 / API-3）

> 版本：V1.1（2026-11-16，按 `main@846270b` 实际基线校正）  
> 依据：`作答系统完善与可扩展功能需求文档_V1.2_20261114.md`、`作答系统完善与可扩展功能开发文档_V1.1_20261114.md`  
> 实施基线：`main@846270b`（仓库 `D:\ssre_V1\ShengShengRuEr`），**API-1 与 `0005_attempt_system` 已在基线中**

## 0. 基线结论（重要）

- 基线已含 API-1、`attempts/attempt_answers/attempt_rejections` 三表与迁移 `0005_attempt_system`；本任务**未新增/修改迁移**。
- 本任务只新增 API-3 与前端作答域，并将 `services/attempts.py` 的私有汇总函数提取为公开 `attempt_summary_from_attempt`（同实现，API-1 行为不变）。
- 上一轮工区遗留的重复迁移 `0005_attempts.py` 与重复消息模块 `core/attempt_messages.py` 已删除，避免与基线冲突。
- 前端错误白名单按**基线真实** `HTTP status + msg` 对齐（见 §2.3）。

## 1. 通用约定

- 前缀 `/api/v1`；统一响应 `{code, msg, data}`；字段 `snake_case`。
- 鉴权：`Authorization: Bearer <JWT>`。
- 错误顺序：401（未登录/失效）→ 403（角色不符）→ 404（不可访问）→ 400/422 → 500。
- 不返回答案、解析、听力正文、题目身份 ID（API-3/结果响应）；API-1 请求的 `loaded_question_ids` 保持现契约。
- 不记录答案/payload 到日志。

## 2. API-1 提交整卷作答

`POST /api/v1/listening-papers/{exam_paper_id}/attempts`

### 2.1 请求

| 项 | 值 |
| --- | --- |
| 权限 | 仅 `student`；管理员 403；未登录 401 |
| Header | `Idempotency-Key: <UUIDv4>`（36 字符、版本位 4、变体位 8/9/a/b） |
| Body | `{"loaded_question_ids": [int...], "answers": [{"question_id": int, "selected_option": "A"|"B"|"C"|"D"}]}` |

- `loaded_question_ids`：详情全部题目 ID，按详情顺序；服务端按集合与当前批次比对（顺序不作为拒绝理由），不得为空。
- `answers`：只含已答题；字母必须大写 A–D；同一 `question_id` 不得重复；允许空数组（全部未答）。
- 路径 ID 必须为正整数且不超过 BIGINT；JSON 中的 ID 严格为整数（字符串/浮点/布尔 → 422）。
- `Idempotency-Key` 缺失/非法 → **400 E05**（不是 422）。
- 请求体类型/必填字段错误 → 422（统一文案「请求参数校验失败」，不回显字段值）。

### 2.2 成功

`200`，`msg="提交成功"`，`data` 为汇总（与 API-3 `latest_attempt` 同模型）：

```json
{
  "attempt_code": "uuid",
  "exam_paper_id": 1,
  "submitted_at": "2026-11-14T06:30:00Z",
  "question_count": 4,
  "correct_count": 3,
  "correct_rate": 75,
  "practice_score": {
    "available": true,
    "value": 30,
    "max": 40,
    "label": "练习估分，非官方成绩",
    "reason": null
  }
}
```

- `correct_rate = round(correct_count * 100 / question_count)`，整数 0–100；未答按错计。
- 练习估分由判分服务按原卷口径计算；`available=false` 时 `value=null` 并给 `reason`（`not_standard_25` / `question_type_missing` / `type_count_mismatch` / `unknown_type`），`max` 默认 249、`label` 固定。不是官方成绩。
- `attempt_code` 为服务端生成的 UUIDv4；`submitted_at` 为服务端真实提交时间（UTC）。

### 2.3 明确失败（错误身份 = HTTP status + msg 常量）

后端常量为 `backend/app/schemas_attempts.py` 的 `MSG_E03–E09`；前端 `frontend/src/attempt/errors.ts` 逐字匹配（E07 用固定前缀）。

| 标识 | HTTP | msg | 前端动作 |
| --- | --- | --- | --- |
| E03 | 404 | `资源不存在` | 保留答案；从 frozenPayload 重建草稿并读回成功→清旧信封、下次新键；与 API-3 404 分流 |
| E04 | 400 | `内容已更新，请重新作答` | 清答案/标记/信封；重载详情；下次新键 |
| E05 | 400 | `缺少或非法的提交键 Idempotency-Key` | 保留答案；重建草稿读回成功→清信封；下次新键 |
| E07 | 400 | `提交内容不合法：` + 固定后缀 | 同 E05；不循环 |
| E08 | 400 | `本轮同一试卷仅允许提交一次` | 终态只读；写 `source=e08, summary=null, submittedAt=null` 标记；查询 API-3 |
| E09 | 400 | `提交键已用于其他提交，请使用新键` | 保留信封；查 API-3；true 结束 / false 清后新键 / 失败保留 |
| E14 | 404 | `资源不存在` | 同 E03（内容/音频完整性失败，不写永久标记） |
| 422 | 422 | `请求参数校验失败` | 保留答案；重建草稿读回成功→清信封；下次新键 |
| 500 | 500 | `服务器内部错误` | 保留信封、state=unknown；同键手动重试 |
| 未知 400/4xx | 原状态 | 未列入文案 | 保留信封与 pending；不放开编辑；不自动新键 |

> E03/E14 对未认证学生统一返回 404 与同一文案，不区分「不存在/隐藏/下线」，避免泄露存在性；前端按同一 404 分支处理。

### 2.4 幂等、限次、并发

- 同一学生 + 同一试卷至多一条成功记录：`ATTEMPT_LIMIT_PER_PAPER = 1`，由「键级事务锁 + 学生×试卷锁 + 计数」保证（**没有** `(student_id, exam_paper_id)` 唯一约束）。
- 同一 `Idempotency-Key` + 同一 payload 指纹：回放原成功汇总（200），不新增记录。
- 同一 Key + 不同 payload：E09（400）。
- 不同 Key 已成功：E08（400）。
- 明确失败 E04/E03 写入 `attempt_rejections`（`rejection_kind` 仅两种）；同键重试保持同一结果。
- 两个标签页不同 Key：后端限次裁决；一成功一 E08；前端各自通过 API-3/E08 收敛。
- 成功写入 attempts + attempt_answers 为单事务，`commit` 一次；并发撞唯一约束（`attempt_code` / `(student_id, attempt_key)`）后回滚并重新判定（回放 / E09 / E08）。

### 2.5 版本校验（E04）

以当前批次（`is_current ∧ active`）题目集合为准：

1. 请求集合 == 当前集合 → 继续。
2. 请求集合 == 该试卷任一历史批次集合 → E04。
3. 其他不一致 → E07（固定前缀文案）。

换批后旧草稿/旧信封的 `loaded_question_ids` 命中历史批次，因此返回 E04。

## 3. API-3 本人本卷提交状态

`GET /api/v1/listening-papers/{exam_paper_id}/attempt-status`

### 3.1 权限与响应头

- 仅 `student`；管理员 403；未登录 401；不可访问 404（`资源不存在`，不泄露存在性）。
- 只读：不 `commit`、不写审计/拒绝表、不 join answers。
- 成功与 404 均返回 `Cache-Control: no-store`。

### 3.2 响应

```json
{
  "code": 200,
  "msg": "查询成功",
  "data": {
    "exam_paper_id": 1,
    "submitted": true,
    "attempt_count": 1,
    "latest_attempt": {
      "attempt_code": "uuid",
      "exam_paper_id": 1,
      "submitted_at": "2026-11-14T06:30:00Z",
      "question_count": 4,
      "correct_count": 3,
      "correct_rate": 75,
      "practice_score": { "available": true, "value": 30, "max": 40, "label": "练习估分，非官方成绩", "reason": null }
    }
  }
}
```

- 未提交：`submitted=false, attempt_count=0, latest_attempt=null`。
- `latest_attempt` 复用 API-1 的 `AttemptSubmitData`，字段完全一致；内层 `exam_paper_id` 必须与外壳一致。
- 不返回逐题/答案/解析/正文/题目 ID/`can_attempt`/`attempt_limit`。

### 3.3 语义不变量（后端 Schema 拒绝输出矛盾组合）

- `submitted === (attempt_count > 0)`；
- `submitted=false` → `attempt_count=0` 且 `latest_attempt=null`；
- `submitted=true` → `attempt_count>=1`；`latest_attempt` 允许为 `null`（确定已提交、仅汇总不可用）；
- 嵌套 `exam_paper_id` 与外壳一致。

### 3.4 单快照查询

count 与 latest 来自同一条 SQL（窗口计数），无两次查询回退：

```sql
SELECT a.*, count(*) OVER () AS attempt_count
FROM attempts a
WHERE a.student_id = :student_id AND a.exam_paper_id = :exam_paper_id
ORDER BY a.submitted_at DESC, a.id DESC
LIMIT 1;
```

- 无行 → count=0/latest=null；有行 → count 为该学生本卷成功总数，latest 为最新行。
- 走 `ix_attempts_student_paper`；不 join `attempt_answers`。
- 并发提交期间查询只可能返回 `false/0/null` 或 `true/1/latest`，不得出现 `count=0 + latest` 矛盾。
- 证据：`backend/tests/test_attempt_status_api.py::test_status_uses_single_window_statement` 监听 SQL，断言只发 1 条 `FROM attempts` 且含 `count(*) OVER` 与 `LIMIT`。

## 4. 数据表（基线迁移 0005_attempt_system）

| 表 | 关键列 | 约束/索引 |
| --- | --- | --- |
| `attempts` | id, attempt_code, student_id, exam_paper_id, import_batch_id, attempt_key, request_fingerprint, submitted_at, question_count, correct_count, correct_rate, practice_score, score_breakdown(JSONB) | 唯一 `attempt_code`、`(student_id, attempt_key)`；`ix_attempts_student_paper(student_id, exam_paper_id)`、`ix_attempts_paper`、`ix_attempts_submitted_at`；题量/正确数/正确率/估分 CHECK |
| `attempt_answers` | attempt_id, question_no, question_id, passage_type, question_text, option_a–d, correct_option, selected_option, is_correct, explanation_text | 唯一 `(attempt_id, question_no)`、`(attempt_id, question_id)`；正确性/字母/题号 CHECK；`ix_attempt_answers_attempt` |
| `attempt_rejections` | student_id, exam_paper_id, attempt_key, request_fingerprint, rejection_kind, detail(JSONB), created_at | 唯一 `(student_id, attempt_key)`；`rejection_kind ∈ {paper_not_accessible, content_version_mismatch}` |

无触发器、无服务端草稿、无逐题结果接口；不修改模块一/二既有表。

## 5. 兼容与回退

| 场景 | 处理 |
| --- | --- |
| API-3 未部署/不可达 | 前端按 404/网络降级；发布须前后端同批 |
| API-1 已有成功记录 | 新 Key → E08；同 Key 同 payload → 回放；同 Key 异 payload → E09 |
| 旧本机数据 | 不迁移；普通草稿忽略/删；信封损坏进入 `pending-unrecoverable` |
| 模块二接口 | 列表/详情/音频语义不变；管理员按原规则 |
| 数据库 | 无新增/修改迁移（基线 `0005_attempt_system`） |
