# 听力试卷接口契约（模块二）

- 状态：**V1.0 已实现**。对应开发文档 `docs/development/module-2/design.md` V1.0 第 5 节、任务卡 T04–T08。
- 实现位置：`backend/app/api/listening_papers.py`、`backend/app/api/admin_listening_papers.py`。
- 需求编号：M2-B01（试卷与题目可查）、M2-B03/B04（管理员配套内容与权限）、M2-B05（真实音频）、M2-B06（可见性）、M2-B10（异常处理）。
- 兼容性：本次为模块二首批业务接口，无历史版本，无破坏性变更。

## 0. 通用约定

- 前缀 `/api/v1`；路径资源复数 `kebab-case`；JSON 字段与查询参数 `snake_case`。
- 登录要求：全部接口都需要 `Authorization: Bearer <access_token>`（复用模块一登录，不新增登录流程）。
- 响应外壳沿用模块一 `app/core/errors.py`：

```json
{"code": 200, "msg": "OK", "data": {}}
```

- 失败响应同一外壳，`code` 取 HTTP 状态码，`data` 为 `null`，`msg` 为中文说明。
- 鉴权顺序固定：先 401（无 token / token 失效 / 账号停用 / 已撤销），再 403（非管理员调管理接口）。
- **学生接口在服务端组装阶段即剔除**答案、解析、听力正文、批次与状态字段，不存在"先返回再让前端隐藏"。
- 列表本阶段不分页，一次返回全部；数据量增大后再引入分页（需版本化变更）。

### 状态口径

三个维度独立，**不得合并为一个"完成"状态**：

| 字段 | 含义 | 存储位置 |
| --- | --- | --- |
| `is_current` | 该批次是否为该试卷的当前数据版本 | `import_batches.is_current` |
| `check_passed` | 最低内容检查是否通过（技术可展示条件） | `content_checks.is_passed` |
| `is_visible` | 管理员是否确认学生可见（业务许可） | `paper_visibility.is_visible` |

学生可访问 = `is_current` ∧ `check_passed` ∧ `is_visible`。

---

## 1. 获取试卷列表

1. **场景与路径**：学生端和管理员端共用的试卷入口。`GET /api/v1/listening-papers`
2. **权限**：登录即可。管理员返回全部试卷；学生只返回**满足可访问三条件**的试卷。
3. **参数**：无路径参数、无查询参数。
4. **成功响应**（`200`）：

```json
{
  "code": 200,
  "msg": "OK",
  "data": {
    "items": [
      {
        "exam_paper_id": 1,
        "exam_paper_code": "CET4-2025-06-1",
        "exam_level": "CET4",
        "exam_year": 2025,
        "exam_month": 6,
        "paper_set": 1,
        "content_scope": "listening",
        "audio_url": "/api/v1/listening-papers/1/audio",
        "duration_ms": 1416046
      }
    ]
  }
}
```

无可见试卷时 `items` 为 `[]`，不是错误。

5. **失败**：`401` 未登录或 token 失效；`500` 数据库不可用时明确报错，**不回退到写死样例**。
6. **关联**：M2-B01 / B06；实现状态已交付。

---

## 2. 获取整卷详情（学生视角）

1. **场景与路径**：学生打开一套听力试卷。`GET /api/v1/listening-papers/{exam_paper_id}`
2. **权限**：登录 + 内容权限。学生须满足可访问三条件；管理员也可调用本接口（返回相同的学生视角结构）。
3. **参数**：`exam_paper_id`（path，整数，试卷主键）。
4. **成功响应**（`200`）：只含题组、题号、题干、A–D 选项与选项顺序，**不含** `correct_option`、`explanation_text`、`explanation_source`、`segment_type=body` 的正文与起止时间。

```json
{
  "code": 200,
  "msg": "OK",
  "data": {
    "exam_paper_id": 1,
    "exam_paper_code": "CET4-2025-06-1",
    "exam_level": "CET4",
    "exam_year": 2025,
    "exam_month": 6,
    "paper_set": 1,
    "content_scope": "listening",
    "audio_url": "/api/v1/listening-papers/1/audio",
    "duration_ms": 1416046,
    "passages": [
      {
        "passage_id": 1,
        "passage_index": 1,
        "passage_type": "短篇新闻",
        "topic": "News report 1",
        "questions": [
          {
            "question_no": 1,
            "question_id": 1,
            "question_text": "What is the news report mainly about?",
            "options": [
              {"label": "A", "text": "..."},
              {"label": "B", "text": "..."},
              {"label": "C", "text": "..."},
              {"label": "D", "text": "..."}
            ]
          }
        ]
      }
    ]
  }
}
```

题号取本套原卷映射（`presentations.question_no`），**不默认恒等、不复用其他套卷**。

5. **失败**：`401`；`404` 试卷不存在**或学生无权访问**（两种情况同一响应，不泄露是否存在该卷）；`500` 数据库不可用。
6. **关联**：M2-B01 / B02 / B04 / B05；实现状态已交付。

---

## 3. 获取试卷音频

1. **场景与路径**：播放器加载真实音频。`GET /api/v1/listening-papers/{exam_paper_id}/audio`
2. **权限**：与接口 2 同一套内容权限。学生须满足可访问三条件；管理员可读全部。**不提供绕过试卷权限的直读路径**。
3. **参数**：`exam_paper_id`（path）；可选标准请求头 `Range: bytes=0-`（音频拖动进度条）。
4. **成功响应**：
   - 无 `Range`：`200`，`Content-Type` 取音频记录的 `mime_type`（本套为 `audio/mp4`），`Accept-Ranges: bytes`，`Content-Length` 为文件字节数，响应体为文件流。
   - 带 `Range`：`206 Partial Content`，附 `Content-Range: bytes <start>-<end>/<total>`。
   - 音频文件本体不入库，数据库只存 `storage_key`、`file_hash`（SHA-256）、`duration_ms`；`file_hash` 不对外返回。
5. **失败**：`401`；`404` 试卷不可访问 / 试卷未绑定音频 / 音频文件缺失或不可读（`msg` 区分，如"音频文件不可用"）；`416` `Range` 越界；`500` 服务器内部错误。
6. **关联**：M2-B05 / B07；实现状态已交付。

---

## 4. 获取试卷配套内容（管理员）

1. **场景与路径**：管理员核对答案、解析与原文对应关系。`GET /api/v1/admin/listening-papers/{exam_paper_id}/companion`
2. **权限**：仅管理员（`require_admin`）。本期所有管理员可管理全部题库，**不按导入人限制**。
3. **参数**：`exam_paper_id`（path）。
4. **成功响应**（`200`）：接口 2 的全部内容，追加：

| 追加字段 | 说明 |
| --- | --- |
| `correct_option` | **本套原卷展示下的**正确答案字母（已按 `option_letter_mapping` 换算；学生看到的就是这个字母） |
| `correct_option_base` | 题库侧的原始答案字母；与 `correct_option` 不同即说明本套做过选项重排 |
| `explanation_text` / `explanation_source` | 解析文本与来源 |
| `segments` | 原文片段：`segment_index`、`segment_type`(`body`/`question`)、`text`、`speaker_code`、`start_ms`、`end_ms` |
| `start_ms` / `body_end_ms` / `end_ms` | 篇章时间范围 |
| `batch_code` / `is_current` | 批次标识与是否当前批次 |
| `check_passed` / `is_visible` / `is_pending_confirmation` | 三个独立状态 |
| `mapping_source` | 题号与选项映射来源 |
| `review_status` | 试卷级审核状态（待审核/需修改/待确认/已通过），与可见性、检查结果互不等价 |
| `passages[].scene` / `passages[].accent` | 场景与口音标注；未标注时 `accent` 为 `未判定` |
| `passages[].review_status` | 篇章级审核状态 |
| `questions[].question_index` | 来源卷全卷题号（与 `question_no` 目标卷题号分开记录） |
| `questions[].content_state` | 内容完整度（待补齐/可用/停用）；非 `可用` 时该卷无法被确认可见 |
| `questions[].review_status` | 题目级审核状态 |

```json
{
  "code": 200,
  "msg": "OK",
  "data": {
    "exam_paper_id": 1,
    "exam_paper_code": "CET4-2025-06-1",
    "batch_code": "3f2a9c1d8b7e4a60",
    "is_current": true,
    "check_passed": true,
    "is_visible": true,
    "is_pending_confirmation": false,
    "mapping_source": "原卷题号映射（恒等）",
    "passages": [
      {
        "passage_id": 1,
        "passage_index": 1,
        "passage_type": "短篇新闻",
        "start_ms": 0,
        "body_end_ms": 42000,
        "end_ms": 58000,
        "segments": [
          {"segment_id": 1, "segment_index": 1, "segment_type": "body", "text": "...", "speaker_code": "S1", "start_ms": 0, "end_ms": 3200}
        ],
        "questions": [
          {"question_no": 1, "question_id": 1, "question_text": "...", "options": [], "correct_option": "B", "explanation_text": "...", "explanation_source": "答案解析 PDF 第 2 页"}
        ]
      }
    ]
  }
}
```

当前无批次时 `batch_code` 为 `null`，状态字段全部为 `false`，`passages` 为空数组。

5. **失败**：`401`；`403` 学生调用；`404` 试卷不存在；`500` 数据库不可用。
6. **关联**：M2-B03 / B04 / B06；实现状态已交付。

---

## 5. 设置学生可见性（管理员）

1. **场景与路径**：确认可见 / 取消可见。`POST /api/v1/admin/listening-papers/{exam_paper_id}/visibility`
2. **权限**：仅管理员。
3. **请求结构**：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `action` | string | 必填，取值 `confirm` 或 `cancel` |
| `reason` | string | 可选，最长 255，默认空串 |

```json
{"action": "confirm", "reason": "25 题逐题核对与整套核听已完成"}
```

`confirm` 前**必须**先通过最低内容检查（缺题、题序错误、选项映射异常、音频不可用等），未通过返回 `400` 并带具体问题；`cancel` **不以检查通过为前提**。每次操作写 `paper_visibility` 与 `visibility_audit_logs`（只追加）。确认记录**绑定当前批次**，切到新批次后不继承旧确认。

4. **成功响应**（`200`）：

```json
{
  "code": 200,
  "msg": "操作成功",
  "data": {
    "exam_paper_id": 1,
    "batch_code": "3f2a9c1d8b7e4a60",
    "is_visible": true,
    "check_passed": true,
    "action": "confirm"
  }
}
```

5. **失败**：`400` 检查未通过（回传问题清单，含 `content_state_not_usable`、`option_empty`、`audio_missing` 等 `kind`）或当前无可用批次；`401`；`403`；`404` 试卷不存在；`422` 请求体校验失败（沿用模块一处理器，不回显请求值）；`500`。
6. **关联**：M2-B06 / B08；实现状态已交付。

---

## 6. 获取最低内容检查结果（管理员）

1. **场景与路径**：确认可见前查看检查结论。`GET /api/v1/admin/listening-papers/{exam_paper_id}/checks`
2. **权限**：仅管理员。
3. **参数**：`exam_paper_id`（path）。
4. **成功响应**（`200`）：

```json
{
  "code": 200,
  "msg": "OK",
  "data": {
    "exam_paper_id": 1,
    "batch_code": "3f2a9c1d8b7e4a60",
    "is_passed": true,
    "issues": [],
    "checked_at": "2026-11-03T14:20:11+00:00"
  }
}
```

`issues` 每项为 `{"kind": "...", "message": "..."}`。当前实现的 `kind`：

| kind | 触发条件 |
| --- | --- |
| `missing_questions` | 当前批次没有任何题目 |
| `expected_count_missing` | 试卷未建立具备原卷来源依据的应有题量，无法校验整卷完整性 |
| `question_count_mismatch` | 题目数与应有题量不符，或题目数与映射数不符 |
| `question_no_not_sequential` | 原卷题号不是 1—应有题量的连续序列（含末尾整题缺失） |
| `question_text_empty` / `option_empty` | 题干或选项为空 |
| `correct_option_invalid` | 答案字母不是 A–D |
| `content_state_not_usable` | 题目内容完整度不是「可用」 |
| `presentation_missing` | 题目缺少原卷映射 |
| `option_mapping_incomplete` | 映射未覆盖 A–D |
| `option_mapping_invalid` | 映射值不是 A–D 的一一排列（会导致空选项或重复选项） |
| `option_display_empty` | 按本套映射组装后仍存在空选项 |
| `question_passage_missing` | 题目所属篇章不存在 |
| `audio_unbound` / `audio_missing` | 试卷未绑定音频 / 音频文件不存在 |

无批次或无检查记录时 `is_passed=false`、`issues=[]`、`checked_at=null`。

5. **失败**：`401`；`403`；`404` 试卷不存在；`500`。
6. **关联**：M2-B06 / B08；实现状态已交付。

---

## 附：错误响应样例

```json
{"code": 401, "msg": "未登录或登录已过期", "data": null}
{"code": 403, "msg": "需要管理员权限", "data": null}
{"code": 404, "msg": "资源不存在", "data": null}
{"code": 400, "msg": "内容检查未通过，不能确认可见", "data": null}
```

题量依据属于受控导入数据，不由学生接口提供。修复版的字段格式及升级后重新确认步骤见 [验收指南](../../acceptance/module-2/guide.md#扩展复验修复版建立原卷题量基准)。
