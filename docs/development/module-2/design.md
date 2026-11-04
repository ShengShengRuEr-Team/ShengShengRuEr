# 模块二后端开发文档（V1.0 定版）

> 状态说明：本文保留开发方案与阶段记录；历史“完成”不等于当前验收通过，当前结论见 [验收索引](../../acceptance/README.md)。

- 状态：**V1.0 定版**。V0.1 草案经两位验收人独立审核，2026-11-03 汇总确认：第 2 项（本期只建最小业务子集）、第 12 项（Python 用 3.14.2）按审核意见裁定，其余条目按草案默认通过。审核结论见第 9 节。
- 基线：`develop` @ `6af6197`（已克隆核实，与需求文档 §1.1 记录一致）。
- 依据：模块二需求文档 V1.5、技术选型整合稿 V1.5、16 表逐表解释与采集试填报告、本仓库 `backend/` 实际代码与 `docs/` 规范。
- 标记说明：本文分「已核实的工程事实」与「建议方案（待确认）」两类。**所有标注「待确认」的条目，在双人审核与施博宇确认前不得作为实现依据**；确认后接口契约拆分到 `docs/development/module-2/api.md`，技术决策写入 `docs/decisions/`。

---

## 1. 现有工程调研结论（已核实，附路径）

| 事项 | 实际做法 | 模块二复用方式 |
| --- | --- | --- |
| 配置读取 | `backend/app/core/config.py`：`Settings(BaseSettings)`，读 `backend/.env`；`DATABASE_URL` 强制以 `postgresql+psycopg://` 开头；`APP_ENV` 枚举 `development/test/staging/production`；`JWT_SECRET_KEY` 少于 32 位或占位值则拒绝启动 | 沿用 `get_settings()`，新增配置项（音频目录等）按同样方式加入，不新建第二套配置 |
| 统一响应 | `backend/app/core/errors.py`：`ok()` 返回 `{"code":200,"msg":...,"data":...}`；`AppError` 经 `main.py` 异常处理器转成 `{"code":<HTTP状态>,"msg":...,"data":null}` | 模块二所有接口沿用同一外壳，不自定义响应结构 |
| 异常处理 | `main.py` 已注册 `AppError` / `RequestValidationError`(422，不回显请求值) / `StarletteHTTPException` / `Exception`(500) 四个处理器 | 复用 `unauthorized()`、`forbidden()`、`not_found()`、`bad_request()`，不新增异常体系 |
| 鉴权顺序 | `backend/app/api/deps.py`：`get_current_user` 先判 401（token、撤销表、账号状态、用户名一致性），`require_admin` 再判 403 | 管理员接口一律 `Depends(require_admin)`；学生接口用 `Depends(get_current_user)`；音频接口在依赖之后再做内容权限判断 |
| 当前用户 | `CurrentUser` dataclass：`id / username / nickname / roles / jti / expires_at`，带 `is_admin` 属性 | 操作日志记 `current_user.id`，不记用户名明文之外的新字段 |
| 角色 | `backend/app/core/permissions.py`：`ROLE_ADMIN="admin"`、`ROLE_STUDENT="student"`、`is_admin()` | 复用，不重建角色体系；本期所有管理员可管理全部题库，不加导入人归属限制 |
| 数据库会话 | `backend/app/db/base.py`：`Base(DeclarativeBase)` + `NAMING_CONVENTION`（ix/uq/ck/fk/pk）、`SessionLocal`、`get_db()`；engine 带 `pool_pre_ping=True`、`connect_args={"options":"-c timezone=UTC"}` | 新模型继承同一 `Base`，复用 `get_db`，不新建引擎 |
| 现有模型 | `backend/app/db/models.py`：4 张表 `users / roles / user_roles / token_revocations`；`BigInteger` 自增主键、`DateTime(timezone=True)`、`server_default=func.now()` | **不修改、不清空、不重建**这 4 张表及其数据 |
| 迁移 | `backend/alembic/versions/0001_initial_auth_only.py`，`down_revision=None`；`backend/alembic/env.py` 用 `Base.metadata`、`compare_type=True`，并对连接串中的 `%` 转义 | 新增一个 `0002_*` 迁移，`down_revision="0001_initial_auth_only"`，约束命名用 `op.f()` |
| 路由与 schema | `main.py` 以 `/api/v1` 挂载 router；`app/schemas.py` 用 Pydantic v2 泛型 `ApiResponse[T]` | 新增 `app/api/listening_papers.py`、`app/api/admin_listening_papers.py`，在 `main.py` 挂载 |
| 测试夹具 | `backend/tests/conftest.py`：自动建 `shengshengruer_test` 库 → `DROP SCHEMA public CASCADE` → `alembic upgrade head` → `seed()`；提供 `admin_token`、`student_token`、`auth_headers` | 模块二测试沿用该夹具，新增用例只加断言，不改夹具的建库逻辑 |
| 种子数据 | `backend/app/seed.py`：`admin/admin123`、`student/student123`，仅 `development/test` 可写 | 验收直接用这两个账号，不新增账号 |
| 验收脚本 | `backend/scripts/acceptance.py`：httpx 打真实服务，逐项打印 PASS/FAIL，退出码 0/1 | 新增 `scripts/acceptance_module2.py` 沿用同一风格 |
| 依赖 | `backend/requirements.txt` 锁定 fastapi 0.143.0 / SQLAlchemy 2.1.4 / alembic 1.20.0 / psycopg 3.3.6 / pytest 9.2.0 / httpx 0.28.1 等 | 本阶段**不新增第三方依赖**；音频读取用标准库 + FastAPI 响应类 |
| Redis | `README.md` 一期边界明确「不引入 Redis；退出失效写入 `token_revocations` 表」；`.env.example` 与 requirements 均无 Redis | **模块二不需要 Redis**，本地环境只需 PostgreSQL |
| 命名规范 | `docs/development/naming-conventions.md`：表名复数 `snake_case`、主键统一 `id`、外键 `<实体>_id`、时间 `created_at/updated_at` 且 UTC、布尔 `is_/has_/can_` 前缀、枚举小写 `snake_case`、API 路径复数 `kebab-case`、字段 `snake_case`、环境变量 `UPPER_SNAKE_CASE` | 全部沿用 |
| API 契约约定 | `docs/development/api-conventions.md` 要求每个接口写明 6 项，且「响应外壳、分页和错误码尚未决定，不在各模块中自行采用不同方案」 | 本文第 5 节给出冻结建议，须在审核时确认 |

> 更正：早期按 RuoYi-FastAPI 通用框架推断的「后端依赖 Redis」不适用于本项目，模块一是自建的最小 FastAPI 工程，已按实际代码更正。

---

## 2. 本阶段范围与边界

**目标**：复用模块一后端、身份权限与 PostgreSQL，完成业务模型与迁移，将一套真实完整听力试卷导入数据库，由接口实际查询试卷与题目、校验内容权限、读取真实音频并持久保存可见状态，为后续前端接入提供可用接口。

**本阶段不开发**（需求 §3.1）：模块二前端页面/组件/路由/播放器交互；模块三的材料上传、OCR、ASR、大模型标注、复核与自动入库；作答、提交、判分、成绩、错题本；题库在线编辑、波形编辑、逐句循环。

**样例与模块三边界**（需求 §3.2）：允许把核对过的一套真实材料整理为**结构化导入文件**，再用可重复执行的导入工具写入数据库；不要求自动识别。数据库记录必须完整可查，**不能只交付 JSON、Excel 或建表脚本**。本次人工整理导入不得表述为模块三自动处理成果。

**五条已确认业务规则落到实现的约束**（需求 §3.3）：

1. 验收样例优先 2025 年 6 月四级第一套完整听力材料；须先核查完整性，固定原卷、答案解析、原文、整套音频及来源清单，记录文件版本或哈希。材料未核查通过不得视为可验收样例。
2. 内容核对须指定负责人，逐题核对**全部**题干、选项、标准答案、解析与原文对应关系，并核听整套音频，保留真实核对人员、范围、结果和问题修正记录。历史试填中的自动转写、时间对齐及待审核记录**不**直接视为人工审核通过。
3. 提供管理员取消学生可见，持久保存状态与操作记录；取消后学生列表不再返回该卷，详情与音频请求均拒绝。已返回客户端的内容不属服务端可追回范围。
4. 新批次默认不可见；成为当前批次时不得继承旧批次的可见确认，须检查通过后由管理员重新确认。新批次导入失败时原当前批次及其可见状态保持有效；同一份材料幂等重复导入不得被误当作新批次切换。
5. 本期所有管理员均可管理全部题库（查询配套内容、确认可见、取消可见），不增加仅能管理本人导入试卷的归属限制。

---

## 3. 数据模型设计（建议方案，待确认）

### 3.1 原则

- 不动模块一 4 张表；新增表继承同一 `Base`，沿用 `NAMING_CONVENTION`。
- 主键 `id` 为 `BigInteger` 自增；外键 `<实体>_id`；时间字段 `DateTime(timezone=True)` + `server_default=func.now()`；布尔用 `is_` / `has_` 前缀。
- **16 表是采集与标注结构基线，不等于 16 项独立开发任务，也不是物理表数量上限**（整合稿 §7）。本阶段只建展示链路必需的最小子集，字段命名、枚举与主外键含义沿用字段表；其余词典与标注表在模块三接入时按基线补齐。差异须逐条记录理由并交审核确认。
- 不把现有 `review_status` 直接等同于学生可见性或模块三验收状态；**检查结果、学生可见、标注审核、模块三验收是四个独立维度**。

### 3.2 新增表清单（草案）

| 表名 | 用途 | 主要字段 | 关键约束 | 对应 16 表 |
| --- | --- | --- | --- | --- |
| `exam_papers` | 试卷身份与内容范围 | `exam_paper_code`, `exam_level`, `exam_year`, `exam_month`, `paper_set`, `content_scope`, `playback_audio_id`, `expected_question_count`, 时间戳 | `uq exam_paper_code`；`content_scope` 固定 `listening` | `01_exam_paper` |
| `audio_files` | 音频引用与校验 | `storage_provider`, `storage_key`, `duration_ms`, `file_hash`, `mime_type` | `uq storage_key`；`file_hash` 非空 | `02_audio` |
| `passages` | 篇章与题组顺序 | `exam_paper_id`, `batch_id`, `audio_id`, `passage_index`, `passage_type` | `uq (batch_id, passage_index)`；FK 到试卷/批次/音频 | `03_passage` |
| `transcript_segments` | 正文与录音问题片段 | `passage_id`, `batch_id`, `segment_index`, `segment_type`(`body`/`question`), `text`, `start_ms`, `end_ms` | `uq (passage_id, segment_index)`；时间落在篇章范围内 | `04_transcript_segment` |
| `questions` | 题干、选项、答案、解析 | `passage_id`, `batch_id`, `question_segment_id`, `question_text`, `option_a`~`option_d`, `correct_option`, `explanation_text`, `explanation_source` | `correct_option` 限 A–D；解析来源非空；FK 到篇章与问题片段 | `05_question` |
| `presentations` | 本套原卷题号与选项映射 | `exam_paper_id`, `batch_id`, `question_id`, `question_no`, `option_mapping_state`, `mapping_source` | `uq (batch_id, question_no)`；不混用其他套卷映射 | `13_presentation` |
| `content_groups` | 听力内容组（最小记录） | `batch_id`, `group_code`, `title` | `uq (batch_id, group_code)` | `12_content_group` |
| `import_batches` | 批次、来源与当前批次 | `exam_paper_id`, `batch_code`, `source_manifest_hash`, `source_manifest`, `status`(`pending`/`active`/`failed`), `is_current`, `imported_at` | `uq batch_code`；每套试卷至多一个 `is_current=true`（部分唯一索引） | 系统记录，新增 |
| `content_checks` | 最低内容检查结果 | `exam_paper_id`, `batch_id`, `is_passed`, `issues`, `checked_at` | 一次检查一行，`issues` 为可定位的问题清单 | 系统记录，新增 |
| `paper_visibility` | 学生可见状态 | `exam_paper_id`, `batch_id`, `is_visible`, `confirmed_by`, `confirmed_at`, `cancelled_by`, `cancelled_at` | 确认记录**绑定批次**，新批次不继承旧确认 | 系统记录，新增 |
| `visibility_audit_logs` | 可见性操作记录 | `exam_paper_id`, `batch_id`, `action`(`confirm`/`cancel`), `operator_user_id`, `reason`, `created_at` | 只追加，不修改 | 系统记录，新增 |

> 字段表比对已闭环：`schema_options_merged_16tables.json` 已到位，7 张业务表逐字段对齐，结论见 `docs/development/module-2/schema-alignment.md`。仍待确认：`issues` 用 JSONB 还是独立明细表；`source_manifest` 是否单独建表。

### 3.3 四个状态必须分离

- `import_batches.is_current` = 当前批次（数据版本）。
- `content_checks.is_passed` = 最低内容检查（可展示的技术条件）。
- `paper_visibility.is_visible` = 管理员确认学生可见（业务许可）。
- 标注审核 / 模块三验收 = 本阶段不实现，仅保留字段位，不联动修改。

**学生可访问 = 当前批次 ∧ 最低内容检查通过 ∧ 管理员确认可见**。三者分别持久化，服务重启后仍有效。

### 3.4 迁移策略（待确认）

单个 `0002_module2_listening_papers.py`，`down_revision="0001_initial_auth_only"`，`upgrade()` 建上述表与索引、`downgrade()` 逆序删表。迁移不触碰 `users/roles/user_roles/token_revocations` 及其数据。需提供 `downgrade` 可回退验证。

---

## 4. 「功能—来源表和字段—接口字段—角色可见范围」对照表（草案，待确认）

按需求 §5 末尾要求列出。来源字段依据需求 §5.1。

| 功能 | 来源表与字段 | 本阶段 DB 列 | 接口字段 | 管理员 | 学生 |
| --- | --- | --- | --- | --- | --- |
| 试卷身份 | `01_exam_paper`: `exam_paper_code`, `exam_level`, `exam_year`, `exam_month`, `paper_set` | `exam_papers.*` | `exam_paper_id`, `exam_paper_code`, `exam_level`, `exam_year`, `exam_month`, `paper_set`, `content_scope` | 全部 + 状态 | 全部（不含状态） |
| 音频绑定 | `01_exam_paper.playback_audio_id`；`02_audio`: `storage_key`, `duration_ms`, `file_hash` | `audio_files.*` | `audio_url`, `duration_ms`；`file_hash` 不对外 | 可查哈希 | 不返回哈希 |
| 篇章/题组顺序 | `03_passage`: `passage_index`, `passage_type` | `passages.*` | `passage_id`, `passage_index`, `passage_type` | 是 | 是 |
| 题干与选项 | `05_question`: `question_text`, `option_a`~`option_d`, `question_segment_id` | `questions.*` | `question_id`, `question_no`, `question_text`, `options` | 是 | 是 |
| 录音问题题干 | `04_transcript_segment` 中 `segment_type=question` 的 `text` | `transcript_segments.text` | 作为 `question_text` 返回 | 是 | 是 |
| 听力正文 | `04_transcript_segment` 中 `segment_type=body` 的 `text` | `transcript_segments.text` | 不出现在学生接口 | 是（配套内容） | **否** |
| 标准答案 | `05_question.correct_option` | `questions.correct_option` | `correct_option` | 是 | **否** |
| 解析 | `05_question.explanation_text` | `questions.explanation_text`, `explanation_source` | `explanation_text`, `explanation_source` | 是 | **否** |
| 原文片段与时间 | `04_transcript_segment`: `segment_index`, `start_ms`, `end_ms` | `transcript_segments.*` | `segments` | 是 | **否** |
| 原卷题号与映射 | `13_presentation`: `question_no`, `option_mapping_state`, `mapping_source` | `presentations.*` | `question_no`, `option_order` | 是 | 是（题号与选项顺序） |
| 内容组 | `12_content_group.content_group_id` | `content_groups.*` | 本阶段不单独暴露 | 是 | 否 |
| 当前批次 / 检查 / 可见 | 系统记录，新增 | `import_batches` / `content_checks` / `paper_visibility` | `batch_code`, `is_current`, `check_passed`, `is_visible`, `is_pending_confirmation` 等状态 | 是 | **否** |

**红线**：学生接口在服务端就剔除答案、解析、听力正文与状态字段，**不得先返回再交给前端隐藏**；不向学生提供含上述内容的原始资料下载。

---

## 5. 接口契约（建议方案，待确认）

### 5.1 通用约定

- 前缀 `/api/v1`，路径资源复数 `kebab-case`，路径参数 / JSON 字段 `snake_case`。
- 响应沿用模块一 `{"code","msg","data"}`，`code` 取 HTTP 状态码；**不引入第二套外壳**。本阶段数据量小，列表不分页（待确认）。
- 所有接口要求登录；管理员专属接口 `Depends(require_admin)`；鉴权顺序保持先 401 后 403。
- 枚举取值小写 `snake_case`，在契约中列举允许值（如 `option_mapping_state`: `identity`/`reviewed`/`unknown`）。

### 5.2 接口清单

| # | 方法与路径 | 权限 | 关联需求 |
| --- | --- | --- | --- |
| 1 | `GET /api/v1/listening-papers` | 登录；管理员看全部，学生仅看可展示试卷 | M2-B01, B06 |
| 2 | `GET /api/v1/listening-papers/{exam_paper_id}` | 登录 + 内容权限 | M2-B01, B02, B04 |
| 3 | `GET /api/v1/listening-papers/{exam_paper_id}/audio` | 登录 + 与试卷相同的内容权限 | M2-B05 |
| 4 | `GET /api/v1/admin/listening-papers/{exam_paper_id}/companion` | 仅管理员 | M2-B03, B04 |
| 5 | `POST /api/v1/admin/listening-papers/{exam_paper_id}/visibility` | 仅管理员 | M2-B06 |
| 6 | `GET /api/v1/admin/listening-papers/{exam_paper_id}/checks` | 仅管理员 | M2-B06 |

**接口 1/2 成功响应（学生）**：试卷信息 + 题组列表 + 题目列表（题号、题干、A–D 选项、选项顺序）+ `audio_url` + `duration_ms`。**不含**答案、解析、原文、批次与状态字段。

**接口 4 成功响应（管理员）**：接口 2 的全部内容，加 `correct_option`、`explanation_text`、`explanation_source`、正文片段与时间、`batch_code`、`is_current`、`check_passed`、`is_visible`、`is_pending_confirmation`、`mapping_source`。

**接口 5 请求**：`{"action":"confirm"|"cancel","reason":"..."}`。确认前须做最低内容检查，未通过返回具体问题（缺题、题序错误、选项映射异常、音频不可用）；取消可见**不以检查通过为前提**。每次操作写 `paper_visibility` 与 `visibility_audit_logs`。

**接口 3 音频**：按 `storage_key` 在受控目录读取文件，返回可解码的音频流（`Content-Type` 依 `mime_type`，支持 Range 待确认）。读取前复用身份与内容权限判断；文件缺失、不可读、绑定错误返回明确结果。音频文件本体不入库。

### 5.3 错误响应（沿用现有处理器）

| 场景 | HTTP / `code` | `msg` 方向 |
| --- | --- | --- |
| 无 token / token 失效 | 401 | 沿用 `unauthorized()` |
| 学生调管理员接口 | 403 | 沿用 `forbidden("管理员")` |
| 试卷不存在 / 学生访问不可见试卷 | 404 | 「资源不存在」或等价明确文案，不泄露是否存在该卷（待确认口径） |
| 参数校验失败 | 422 | 沿用现有处理器，不回显请求值 |
| 检查未通过仍确认可见 | 400 | 返回具体问题清单 |
| 音频文件缺失 / 不可读 / 绑定错误 | 404 / 500 | 区分「文件不可用」与「服务器内部错误」 |
| 数据库不可用 | 500 | 明确报错，**不回退到写死样例伪装成功**（B14） |

> 待确认：404 统一文案是否会与「资源不存在」冲突、是否需要细分错误码、音频是否支持 Range 与缓存头。

---

## 6. 样例材料与导入工具（建议方案，待确认）

### 6.1 材料清单与来源固定

材料已于 2026-11-03 到位并逐文件核对哈希，全部放入**本机受控目录**（不进 Git）：原卷 PDF、答案解析 PDF、原始音频（`.mp3` 后缀，实为 AAC/M4A 容器）、听力时间校对稿、字段结构 `schema_options_merged_16tables.json`，以及来源清单 `source_manifest`。逐文件版本与 SHA-256 见来源清单；仓库内不存放这些原件。

试填记录（16 表报告）：25 题、8 篇章、165 条转写片段、100 个选项、音频 AAC 44100Hz 双声道 1416.046 秒、哈希已留；但英文转写与时间沿用自动对齐结果，**本次没有重新逐句人工核听**，新标注均为试标且保留待审核。因此不能作为人工审核通过的验收依据。

### 6.2 内容核对（需求 §3.3 第 2 条，负责人待指定）

- **负责人**：待施博宇在审核时指定（本文不填虚构人名）。
- **范围**：25 题逐题核对题干、A–D 选项、标准答案、解析、原文对应关系；核听整套约 23.6 分钟音频；核对题序与选项映射。
- **记录**：每题一行，含核对人、核对日期、原卷页码/解析页码、发现的问题、修正内容、修正后复核结论；附件保留来源清单与音频哈希。
- **判定**：`content_state=可用` 仅表示字段齐全，不代表审核通过；历史待审核试标不自动转为通过。

### 6.3 结构化导入文件

建议单一 JSON（或 JSON + 受控音频目录），顶层含 `exam_paper`、`audio`、`passages`、`transcript_segments`、`questions`、`presentations`、`content_groups`、`source_manifest`。字段与第 3.2 节表结构一一对应；`question_no` 与 `option_order` 必须来自本套原卷映射，不默认恒等、不复用其他套卷答案字母。

### 6.4 导入工具

- 命令（建议）：`python -m app.import_module2 --input <结构化文件> --audio-dir <受控目录>`；输出导入摘要与校验结果。
- **幂等**：以来源清单 + 文件内容哈希计算 `batch_code`；同一 `batch_code` 已存在且状态 `active` 时直接返回「已导入，无变更」，不新增试卷/题目/关系，**不切换批次、不清除已有可见确认**。
- **事务与回滚**：新批次先写 `pending` 草稿，全部校验通过后在单事务内建表记录、绑定音频、置 `active` 并切换 `is_current`；任一步失败整体回滚，原当前批次及其可见状态保持有效，不留下半套试卷。
- **批次切换**：切换到不同新批次后，旧 `paper_visibility` 确认对新批次无效，须重新检查并由管理员重新确认可见。
- **校验**：字段缺失、外键错误、映射异常、文件缺失须给出可定位信息；**禁止用占位答案、虚构解析或虚构原文通过验收**。
- **音频**：文件放受控目录，DB 存 `storage_key`、`file_hash`、`duration_ms` 及与试卷的绑定；导入时校验文件存在、可读取、哈希与时长与来源清单一致。

---

## 7. 验证方法（对齐验收 B01–B16）

| 编号 | 验证动作 | 期望结果 |
| --- | --- | --- |
| B01 | 查 `main.py` 挂载与 `deps.py` 复用情况 | 未重做登录体系 |
| B02 | 在空库执行 `alembic upgrade head` + 导入，`psql` 查业务表；再在第二套库重跑 | 接口结果与数据库一致，静态响应无法替代 |
| B03 | 对照原卷逐题比对题组、题号、题干、选项顺序 | 25 题完整，映射正确 |
| B04 | 管理员调接口 4 | 返回答案、解析、原文及必要状态 |
| B05 | 学生调接口 1/2，检查响应原文串 | 无 `correct_option` / `explanation_text` / body 片段；录音问题题干正常 |
| B06 | 学生调接口 4/5/6、改可见性、读不可见试卷 | 403 / 404；管理员管理全部题库 |
| B07 | 用播放工具核听接口 3 返回的音频；学生绕过试卷权限直读 | 可解码、绑定正确；绕过被拒 |
| B08 | 确认 → 取消 → 重启后端 → 再查；检查未通过时尝试确认 | 状态与记录持久；未通过则拒绝确认并说明原因；取消不需要检查通过 |
| B09 | 导入失败注入、重复导入、切换到新批次 | 原当前批次及可见状态有效；无重复记录；新批次须重新确认 |
| B10 | 不存在、无权、空数据、音频缺失等请求 | 均有明确响应 |
| B11 | 对照第 4 节字段表与接口文档 | 来源字段、接口字段、类型、角色范围对应明确，足以支持前端对接 |
| B12 | 两名验收人员分别出具记录 | 均通过后才提交施博宇 |
| B13 | 同一材料重复导入；可控错误导入 | 幂等无重复；失败不留半套试卷 |
| B14 | 重启后端后重查；断开数据库后请求 | 数据仍在；断库明确报错，不回退写死样例 |
| B15 | 跑模块一 `pytest -v` 与 `scripts/acceptance.py` | 11 passed / 8 of 8，通过，账号与鉴权未破坏 |
| B16 | 查内容核对记录与来源清单 | 逐题核对与整套核听完成，附真实人员、范围、结果、修正记录 |

新增 `scripts/acceptance_module2.py` 用 httpx 打真实服务，逐项打印 PASS/FAIL 并以退出码表示结果，风格与模块一验收脚本一致。

---

## 8. 交付顺序与依赖

按任务卡 `docs/development/module-2/tasks.md` 执行，顺序为：迁移与模型 → 材料核对与结构化文件 → 导入工具 → 数据访问层 → 列表/详情接口 → 管理员配套与权限 → 可见性与检查 → 受控音频 → 端到端验证与文档。每张卡一人开发、两人独立验收，均通过后提交施博宇决定是否合并。

---

## 9. 审核结论（2026-11-03 定版）

V0.1 提出的 13 条待确认事项，逐条裁定如下。**「已确认」条目即为实现依据，实现成果见第 11 节。**

| # | 事项 | 结论 | 落地方式 |
| --- | --- | --- | --- |
| 1 | 表名字段与 16 表字段表逐字段比对 | **已闭环（2026-11-03 补做）** | `schema_options_merged_16tables.json` 已到位，7 张业务表逐字段比对完成并补齐字段、类型与枚举，详见 `docs/development/module-2/schema-alignment.md` |
| 2 | 本期只建最小业务子集，还是一次建齐 16 表 | **只建最小业务子集** | 建 11 张表（第 3.2 节），不建 `06_skill`、`07A~07D`、`08_evidence` 等词典与标注表 |
| 3 | 接口 URL、结构、状态码、404 口径、音频 Range | 已确认 | 按第 5 节实现；音频接口支持 Range（206） |
| 4 | 音频受控目录、`mime_type`、哈希算法 | 已确认 | `AUDIO_STORAGE_DIR`（默认 `var/audio`，相对 `backend/` 解析）；`mime_type` 由 `format` 映射，`m4a→audio/mp4`；哈希 SHA-256 |
| 5 | `batch_code` 规则、`is_current` 唯一索引 | 已确认 | `batch_code` = 试卷编码 + `-` + 来源清单哈希前 12 位；`is_current` 用部分唯一索引 `WHERE is_current` |
| 6 | 幂等判定粒度 | 已确认 | 整份来源清单哈希，同一 `batch_code` 重复导入直接返回无变更 |
| 7 | `issues` 用 JSONB 还是明细表 | 已确认 | JSONB（`content_checks.issues`），本阶段不建明细表 |
| 8 | 内容核对负责人与记录位置 | 已确认（负责人待施博宇指定） | 记录模板在仓库 `docs/acceptance/module-2/content-check-record.md`；填写后的实际记录放受控目录，不进 Git |
| 9 | 枚举最终取值 | 已确认 | `content_scope=listening`；批次 `pending/active/failed`；动作 `confirm/cancel`；`segment_type=body/question`；内容枚举保留中文原值 |
| 10 | 列表是否分页 | 已确认 | 本阶段不分页，返回全量 |
| 11 | 本地 PostgreSQL 版本与两套库 | 已确认 | 锁定 PostgreSQL 18.6，`shengshengruer` / `shengshengruer_test` 两套库（见第 11.3 节环境说明） |
| 12 | Python 版本 | **用 3.14.2** | 本地虚拟环境与依赖均按 3.14 系安装 |
| 13 | 真实 `.env`、音频原件、真题 PDF 的存放 | 已确认 | 全部在本机受控目录，`.gitignore` 已覆盖 `*.m4a` / `*.mp3` / `.env` / `venv`；仓库只留 `.env.example` |

**资料与人工核对状态**（更新于 2026-11-04）：

- `schema_options_merged_16tables.json` 已到位，字段表比对见 [表结构比对](schema-alignment.md)；旧采集表仍缺，仅影响历史追溯。
- 内容核对负责人未指定，25 题逐题核对与整套音频核听尚未由人完成。

---

## 10. 禁止事项（写进 AI 编码提示词的红线）

- 不得写死响应、用本地 JSON / Excel / 内存数据冒充 PostgreSQL 查询成果。
- 不得把答案、解析、听力正文返回给学生后再交给前端隐藏；不得向学生提供含上述内容的原始资料下载。
- 不得用占位答案、虚构解析或虚构原文通过验收。
- 不得修改或清空模块一 4 张表及其账号、角色、登录数据。
- 不得混用其他套卷的题号、选项顺序或答案字母；不得在映射不明时默认恒等。
- 不得把可见性、检查结果、标注审核、模块三验收合并为一个「完成」状态。
- 不得把本次人工整理导入表述为模块三自动处理成果。
- 不得提交 API Key、数据库密码、真实 `.env`、真题原件、整套题库或音频到仓库。

---

## 11. 实现成果与验证证据（2026-11-03）

### 11.1 代码产物

| 文件 | 作用 |
| --- | --- |
| `backend/app/db/models_listening.py` | 11 张业务表模型（试卷、音频、批次、内容组、篇章、片段、题目、映射、检查、可见性、操作记录） |
| `backend/alembic/versions/0002_module2_listening_papers.py` | 迁移，`down_revision="0001_initial_auth_only"`，可 `downgrade` 回退 |
| `backend/app/schemas_listening.py` | 学生/管理员请求与响应模型，学生结构不含受限字段 |
| `backend/app/repositories/listening.py` | 数据访问层：可见性判定、学生详情组装、管理员配套组装 |
| `backend/app/services/content_check.py` | 最低内容检查（缺题、题序、选项映射、音频可用性） |
| `backend/app/services/visibility.py` | 确认/取消可见，写 `paper_visibility` 与 `visibility_audit_logs` |
| `backend/app/core/audio_response.py` | 音频 Range 响应（206/416/200），`Content-Disposition` 按 RFC 5987 处理中文文件名 |
| `backend/app/api/listening_papers.py` | 学生接口 1–3 |
| `backend/app/api/admin_listening_papers.py` | 管理员接口 4–6 |
| `backend/app/import_module2.py` | 导入工具：幂等、单事务、失败整体回滚、音频校验与复制 |
| `backend/scripts/acceptance_module2.py` | 端到端验收脚本（16 项，退出码表示结果） |
| `backend/tests/test_module2_listening.py` | 7 个 pytest 用例（自包含样例） |
| `scripts/prepare_module2_materials.py` | 从试填 xlsx 生成结构化导入文件与自动预检报告 |

### 11.2 与草案的偏差（均已在审核结论内）

1. **字段表比对已闭环**：`schema_options_merged_16tables.json` 于 2026-11-03 到位，7 张业务表逐字段对齐（补齐 14 个字段、放宽 5 处类型、修正 1 处枚举默认值、新增 7 个 CHECK），逐字段结论见 `docs/development/module-2/schema-alignment.md`；未建的 9 张词典/标注/关系表按「最小业务子集」留待模块三。
2. **`audio_files` 增加 `format` 与 `mime_type`**：源材料 `02_audio` 只有 `format="m4a"` 没有 `mime_type`，接口要设 `Content-Type`，故保留 `format` 并显式存 `audio/mp4`。
3. **`passages` / `questions` 增加 `*_code` 列**：对应源表业务编码，便于导入重映射与排错，不改变业务语义。
4. **`content_groups` 字段命名对齐源表**：用 `content_group_code` / `group_name` / `exam_level_scope` / `content_fingerprint`，不是草案里的 `group_code` / `title`。
5. **新增 `connect_timeout=5`**（`backend/app/db/base.py`）：验收 B14 要求断库时明确报错，实测无该参数会长时间挂起；加上后断库 5.1 秒返回 500，不影响模块一行为。
6. **主键命名**：基线用 `question_id` / `segment_id` 作主键名，本仓库 `docs/development/naming-conventions.md` 统一要求主键 `id`、外键 `<实体>_id`，本期沿用仓库约定，语义等价（对照见 alignment 文档第 1 节）。

### 11.3 验证证据（实际执行结果）

| 验收项 | 执行动作 | 实际结果 |
| --- | --- | --- |
| B02 | 开发库 `alembic upgrade head` + 导入 | 16 张表；1 卷 / 1 音频 / 1 批次 / 8 篇章 / 165 片段 / 25 题 / 25 映射 |
| B02 | 第二套库 `shengshengruer_test` 重置后重跑 | 16 张表；导入结果与开发库完全一致（25 题 / 165 片段） |
| B02 | `downgrade 0001` → `downgrade base` → `upgrade head` | 全部成功，表数恢复 16 |
| B03/B04 | 管理员配套接口 | 25 题，含 `correct_option`、`explanation_text`、`segments` |
| B05 | 学生详情响应文本检查 | 不含 `correct_option` / `explanation_text` / `explanation_source` / `segments`；25 题题干与 A–D 齐全 |
| B06 | 越权与可见性 | 学生调管理员接口 403；无 token 401；取消可见后列表不含、详情与音频 404 |
| B07 | 音频 Range 与完整下载 | `bytes=0-1023` → 206 `bytes 0-1023/4169648`；完整下载 200 / 4169648 字节 / `audio/mp4` |
| B08 | 确认 → 取消 → 重启后端 | 状态与操作记录持久；重启后可见性、检查结果不变 |
| B09/B13 | 重复导入、哈希不符、事务中途失败 | 重复导入 `noop`；两类失败均整体回滚，批次/题目/试卷计数不变 |
| B14 | 重启后端、断开数据库 | 重启后 25 题与音频仍可查；断库 5.1 秒返回 `{"code":500,"msg":"服务器内部错误"}`，无写死样例；恢复后自动重连成功 |
| B15 | `pytest` + 模块一验收脚本 | `18 passed`（模块一 11 + 模块二 7）；模块一验收 8/8 |
| B16 | 逐题核对与整套核听 | **未完成**，须真实人员按 `docs/acceptance/module-2/content-check-record.md` 执行 |

### 11.4 本机环境搭建记录（可复现）

- Python **3.14.10** + `backend/.venv`，`requirements.txt` 全部依赖有 3.14 wheel。
- PostgreSQL **18.6**（EDB 免安装二进制，`initdb` 到纯 ASCII 路径，未注册系统服务）。
- **踩坑与解决**：`initdb` 在 post-bootstrap 阶段反复 `0xC0000005`。事件日志显示故障模块是本机 **Java JRE 目录下的旧版 `MSVCP140.dll`（14.16.27033）**——该目录在 PATH 中先于系统目录，PG 18 加载了它。系统未安装 VC++ 运行时；把 **14.44.35211** 的 `msvcp140.dll` / `vcruntime140.dll` / `vcruntime140_1.dll` 放进 `pgsql/bin`（DLL 优先同目录）后 `initdb` 一次成功。这不是 PG 版本问题，**换 PG 17/16 无效**，其它机器遇到同样崩溃可按此排查。
- 连接串：`postgresql+psycopg://postgres:<密码>@127.0.0.1:5432/shengshengruer`；测试库 `shengshengruer_test` 由 `tests/conftest.py` 自动创建。
- 音频受控目录：`backend/var/audio/`（`.gitignore` 已忽略音频扩展名与 `.env`）。

### 11.5 验收报告整改（2026-11-04，对应 PR #5 首轮验收）

首轮验收提出 5 类代码缺陷，逐条修复并补回归用例（`tests/test_module2_listening.py`，用例数 7 → 12，全量 23 passed）。

| 编号 | 问题 | 修复方式 | 回归用例 |
| --- | --- | --- | --- |
| F01 | 失败导入会覆盖仍在使用的旧音频 | 音频先写 `.incoming-*` 临时文件，全部写入成功后在提交前原子移入；内容不同时不复用原文件名，改存 `<名>-<hash8><后缀>`，旧文件原样保留；异常分支同时清理数据库事务与本次新建文件 | `test_failed_import_keeps_existing_audio` |
| F02 | 末尾整题一起缺失仍能通过完整题量检查 | 新增 `exam_papers.expected_question_count`（迁移 `0003`），首次导入固定、后续批次不得改写；检查改为「题目数 == 应有题量」且题号必须覆盖 1—应有题量 | `test_missing_questions_against_expected_count` |
| F03 | 非法选项映射仍可开放，学生收到空选项 | 映射键与值都必须是 A–D 的一一排列，并按映射组装后校验四项文本非空；新增 `option_mapping_invalid`、`option_display_empty` 问题种类 | `test_invalid_option_mapping_blocks_confirm` |
| F04 | 选项重排后管理员答案字母未换算 | 管理员配套接口按本套映射把题库字母换算为本套展示字母，返回 `correct_option`（本套）+ `correct_option_base`（题库） | `test_admin_answer_follows_option_mapping` |
| F05 | 同一 `audio_code` 的新文件元数据被静默忽略 | 复用已有音频记录前核对哈希、`storage_key`、时长，任一不符即拒绝并给出可操作提示，要求内容变更使用新 `audio_code` | `test_audio_code_conflict_is_rejected` |

另按 B11 统一配置名：文档中误写的 `LISTENING_AUDIO_DIR` 更正为实际的 `AUDIO_STORAGE_DIR`。

实测复现（真实服务 + 真实库）：

- 删除第 25 题与映射后确认可见 → `400 题目数(24)与选定原卷应有题量(25)不一致；原卷题号应为 1—25`
- 映射改成 `A→Z` 后确认可见 → `400 …选项映射值非法`
- A/B 互换后管理员配套 → `correct_option=B`、`correct_option_base=A`，B 对应文本为正确项
- 失败导入后旧音频 SHA-256 不变，无 `.incoming-*` 残留


## 11.6 扩展复验修复（2026-11-04）

本节对应本地 `fix/module2-recheck-20261104`，取代 §11.5 中 F01/F02 的首次修复方案。验证结果见 [修复验证记录](../../acceptance/module-2/fix-20261104.md)。

- 最终版本路径也校验已有文件哈希；相同内容直接复用，短哈希碰撞时尝试完整哈希路径。数据库写入完成后暂存音频，以排他硬链接发布，禁止覆盖已有目标。只有本次实际新建的正式文件会在回滚时被清理，临时文件在成功和失败后均清理。
- `exam_papers.expected_question_count_source` 使用 JSONB 保存题量来源，含 `document`、`sha256`、`locator`。应有题量为正整数，来自管理员对独立原卷的核对申报；输入格式校验不等于自动证明原卷语义正确，不能把待校验题数当基准。
- 题量与来源一起提供；未提供基准的材料可导入为待核对批次，但检查报告 `expected_count_missing`，不能确认开放。后续批次不得改写已有题量或来源。批次 `source_manifest` 同时记录该依据。
- 迁移 `0004_expected_count_source` 使旧无来源基准失效，保留历史检查并追加失败检查。升级后先核对原卷、补录来源，再重新检查与确认；不修改历史 `0003` 迁移，也不删除认证记录。迁移应在维护时段执行，旧版应用须停止后再切换新版。
- 发布文件与数据库不能跨进程实现单个原子事务；本次覆盖可捕获的写入、复制与提交失败，不声称提供进程崩溃恢复或生产并发保证。
