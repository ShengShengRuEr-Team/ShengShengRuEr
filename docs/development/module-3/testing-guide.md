# 模块三：拉取代码与测试整个链路

本分支包含纯后端模块三，并接入模块二的题库、配套内容、版本及音频接口。实际使用的材料为**2025年6月四级第1套听力，8篇25题**。原始材料包单独传递，包含原卷PDF、扫描答案解析PDF、M4A音频及测试扫描路径的派生原卷；无需将开发机数据库或历史处理结果作为新任务输入。

## 1. 拉取本次代码

在干净的仓库目录执行；已有同名本地分支时切换后使用`git pull --ff-only`。

```powershell
git fetch origin
git switch --track origin/feature/7-module3-auto-processing
cd backend
```

本次PR目标为`develop`。合并前须切到上述功能分支才能取得实现，直接拉取`develop`不会获得尚未合并的代码。

## 2. 准备环境和本地资源

当前冻结配置为Windows x64、常规GIL的**Python 3.13.16**。用该版本解释器分别创建`.venv-api`、`.venv-asr`、`.venv-ocr`，在各环境安装对应带哈希锁文件：

```powershell
# python须为已准备好的3.13.16解释器；不要用模块一、二历史3.14环境混装。
python -m venv .venv-api
python -m venv .venv-asr
python -m venv .venv-ocr
.\.venv-api\Scripts\python.exe -m pip install --require-hashes -r config/module3/requirements-api.lock.txt
.\.venv-asr\Scripts\python.exe -m pip install --require-hashes -r config/module3/requirements-asr.lock.txt
.\.venv-ocr\Scripts\python.exe -m pip install --require-hashes -r config/module3/requirements-ocr.lock.txt
```

模型按`config/module3/model-artifact-manifest.json`中的精确revision和SHA-256准备，目录布局为`M3_MODEL_ROOT/<repository中斜杠换成双连字符>/<revision>/<filename>`。FFmpeg使用`ffmpeg-artifact-manifest.json`列出的shared发行包，将`FFMPEG_DLL_DIR`指向其`bin`；NLTK的`punkt_tab`资源按`nltk-resource-manifest.json`校验并解压到`NLTK_DATA/tokenizers/punkt_tab/`。清单中的downloaded是开发时记录，接收方仍须自行准备实际文件。

本套默认从答案原文准备文字，以CPU执行声学定位和强制对齐，不走ASR；该路线用`align`环境诊断。明确选择`text_source=asr`才需faster-whisper大模型及CUDA诊断；不要为绕过诊断修改冻结profile或静默降级。

复制`.env.example`为`.env`，填写自己的PostgreSQL连接、至少32字符的JWT密钥、独立输出目录、模型根目录、ASR/OCR解释器绝对路径和本地资源路径。`DEEPSEEK_API_KEY`只在新标注时需要。配置和密钥不进入Git。相对材料、输出和模型目录均以`backend/`为根。

新建隔离的验收数据库，再初始化并启动两个终端（均在`backend/`）：

```powershell
.\.venv-api\Scripts\python.exe -m alembic upgrade head
.\.venv-api\Scripts\python.exe -m app.seed
.\.venv-api\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# 另一终端：使用同一份.env
.\.venv-asr\Scripts\python.exe -m app.module3.worker --poll-seconds 2
```

新增迁移revision为`0005_module3_processing`和`0006_module3_invariants`。验收时使用新的隔离库；旧库升级另按迁移流程处理。

可在启动任务前运行各环境诊断：

```powershell
.\.venv-api\Scripts\python.exe -m app.module3.diagnostics --profile api --output var/diagnostics
.\.venv-asr\Scripts\python.exe -m app.module3.diagnostics --profile align --output var/diagnostics
# OCR诊断的模型根通过环境变量显式传入；命令行不自动读取.env。
$env:M3_MODEL_ROOT = (Resolve-Path var/models).Path
.\.venv-ocr\Scripts\python.exe -m app.module3.diagnostics --profile ocr --output var/diagnostics
```

若模型目录不在`var/models`，最后一段换为实际绝对路径。缺包、版本不符、模型或DLL哈希不符会阻断处理。

## 3. 登录并登记三份原始材料

打开`http://127.0.0.1:8000/docs`，`POST /api/v1/login`使用开发种子管理员`admin/admin123`，在Authorize只粘贴返回的`data.token`。自写请求使用`Authorization: Bearer <token>`。种子学生为`student/student123`。

先把材料放进`M3_MATERIALS_DIR`。材料登记是服务器受控文件登记，不是上传文件接口。`storage_key`填该目录内相对文件名，`expected_sha256`填原始包清单中的SHA-256（也可用`Get-FileHash -Algorithm SHA256`重新核对并转小写）。三份文件使用同一试卷编码。例如：

```json
{
  "exam_paper_code": "CET4_2025_06_1_TEST",
  "source_kind": "paper_text",
  "storage_key": "CET4_2025年6月_第1套_真题.pdf",
  "expected_sha256": "2880977bc0a8b730800d310471a3120eb45e4a51d964dc97cb71c32ddf09ac08",
  "source_locator": "2025年6月四级第1套原卷，听力部分"
}
```

依次`POST /api/v1/admin/materials`登记：

| source_kind | 文件 | SHA-256 |
| --- | --- | --- |
| paper_text | CET4_2025年6月_第1套_真题.pdf | 2880977bc0a8b730800d310471a3120eb45e4a51d964dc97cb71c32ddf09ac08 |
| answer_explanation | CET4_2025年6月_第1套_答案解析.pdf | 1021d97c5326909346907c137e98d9a3ed7538b614117bcfb03c8b2d0db232f4 |
| audio | CET4_2025_06_1_听力.m4a | a23dc74f40f8b9806f52e6f8f0468423df5069afea5730c5f9ca3a8c2684864c |

保存返回的`data.id`；后续所有ID和结果哈希均使用当前服务实际返回值，不照抄开发机的任务UUID和数据库ID。

## 4. 从原始输入开始自动处理

`POST /api/v1/admin/processing-tasks`。下面`material_ids`的1/2/3须替换为上一步实际ID；答案PDF的2—9页包含本套听力原文及解析：

```json
{
  "exam_paper": {
    "exam_paper_code": "CET4_2025_06_1_TEST",
    "exam_level": "CET4",
    "exam_year": 2025,
    "exam_month": 6,
    "paper_set": 1
  },
  "material_ids": [1, 2, 3],
  "document_mode": "text",
  "text_source": "reference",
  "reference_preparation": "auto",
  "material_pages": {"2": [2, 3, 4, 5, 6, 7, 8, 9]},
  "dictionary_snapshot_sha256": "6348030d2b5acb49e0cf036487f4ddd508428f33b0033e5cfb4261d40a986580",
  "profile_version": "M3-WIN64-1.1.0",
  "stop_after": "align"
}
```

`material_pages`的键也须替换为解析实际ID。自动模式自行读取原卷题量及题组，不传人工逐句正文和旧时间戳。worker运行后，用`GET /api/v1/admin/processing-tasks/{task_id}`看状态，用`GET .../{task_id}/stages/{stage}`看reference、align等阶段产物。`awaiting_confirmation`可能是正常停止点，也可能有阻断问题；结合stage及issues判断，不能只看状态名认定通过。

对齐核听后逐阶段新建任务，保留相同考试身份、材料及页码参数，并增加下列绑定：

| stop_after | 额外参数与作用 |
| --- | --- |
| assemble | reuse_alignment_task_id：实际通过的align任务；从原卷及解析组装25题 |
| annotate_sample | 同上，加reuse_assembly_task_id：通过的组装或纠错任务；真实调用前5题 |
| annotate | 同上，加reuse_annotation_task_id和sample_review：已通过的5题小样及逐题复核 |
| completed | 再加reuse_full_annotation_task_id和annotation_review：整套已通过的标注及逐题复核；进入待审业务批次 |

小样和整套复核对象均包含`result_hash`、`decision`、真实`reviewer`、`reviewed_at`及`items`。每项使用当前草稿的`question_src_id`，填写`decision`、`support_reason`、`skill_reason`；小样完整覆盖5题，整套覆盖25题。需修复时整套decision/items使用`changes_required`并给出具体`repair_feedback`，建立新的annotate任务；通过项可核验复用。草稿及哈希由`GET .../{task_id}/result?view=final`取得。复核与候选契约详见[组装标注说明](assembly-annotation.md)及`app/module3/annotation_checks.py`。

原件字段有OCR错误时调用`POST .../{task_id}/corrections`，绑定`expected_result_hash`、来源、原因和具体entity/src_id/field/value。修订建立新任务并保留原auto_draft，后续绑定纠错后的任务。结构通过后仍须复核内容；不保证任何新运行都无需修改。

标注会产生实际DeepSeek费用，失败和重试也记入账本。预算上限为5题0.50美元、同套2美元、阶段5美元；不清空历史账本规避上限。

## 5. 入库、复核和学生可见性

`completed`是请求的停止目标。worker创建pending批次后，还需要实际检查和复核；它不会自动通过审核、切换当前版本或发布学生可见内容。

1. `POST /api/v1/admin/processing-tasks/{task_id}/checks`，请求`{"expected_result_hash":"当前结果哈希"}`。
2. 对同一任务分别`POST .../{task_id}/reviews`，scope为content、annotations、audio。按当前结果逐项覆盖，填写`entity`、`src_id`、`verdict=PASS`及实际`reference`，并提交evidence_refs/note；完整契约见Swagger及[全链路说明](full-pipeline.md)。音频默认itemized整套核听及正文句起止参考各≤300ms；已有用户明确批准时可用user_confirmation，绑定审批来源、当前结果及原音哈希，不填虚构的毫秒测量。
3. 三类审核及检查通过后，`POST /api/v1/admin/listening-papers/{exam_paper_id}/current-batch`，提交实际task_id、batch_id、check_id、result_hash及expected_current_batch_id（首次无当前版本时null）。
4. 再`POST /api/v1/admin/listening-papers/{exam_paper_id}/visibility`，提交`{"action":"confirm","reason":"独立链路验收"}`明确确认学生可见；切换当前版本后默认隐藏。撤销时action为cancel。
5. 用学生身份查`GET /api/v1/listening-papers`、`/{exam_paper_id}`和`/{exam_paper_id}/audio`；配套原文、答案解析用管理员`GET /api/v1/admin/listening-papers/{exam_paper_id}/companion`。

每题必有主要技能、技能证据及答案证据；错因候选只在来源充分时出现，不要求每题都有，也不是对某个真实学生的错因诊断。

## 6. 独立扫描路径与回归

扫描复跑使用新的exam_paper_code，登记原始文本卷作派生父来源，再登记`CET4_2025_06_1_paper_scan_300dpi.pdf`为paper_scan（SHA-256为`6739b7b5e7d4739210ec1fe737c11b9078baedda0d095cd68bdfe6d694d780f2`），填写derived_from_material_id及原始包scan-generation.json中的generation。解析和音频也按新编码登记。实际任务只选扫描卷、解析和音频三个ID，`document_mode=scan`；不选文本父卷。两路径使用同一套材料身份，派生扫描并非纸张实扫。

回归使用专用测试库，pytest会重建该库public schema：

```powershell
$env:TEST_DATABASE_NAME = 'm3_acceptance_test_local'
.\.venv-api\Scripts\python.exe -m pytest tests -q
.\.venv-asr\Scripts\python.exe -m unittest tests.module3.test_ctc_boundaries tests.module3.test_reference_locator -q
.\.venv-ocr\Scripts\python.exe -m unittest tests.module3.test_printed_ocr -q
```

历史开发检查：159项API、10项处理、7项OCR通过，去除3项重叠为173个不同用例；两路均完成真实TCP接口、独立worker、PostgreSQL、25题/100选项/165句回读、Range 206/416、重复导入、撤销恢复和重启持久性。音频是用户明确确认通过，未声称独立人工毫秒测量。适用范围为本套实际版式，接收方独立验收另行记录。

历史`review_module3_*`脚本含开发机路径和数据库名，用于保留实跑记录；另一台机器完整测试以本指南接口流程为入口。详细历史报告见[独立验收交接](independent-acceptance.md)，需求见[模块三V2.3](../../requirements/module-3/requirements.md)。

## 7. PR #8 后续技术复验与 CI

新增复验入口自动创建两个随机命名的隔离数据库，不接受已有业务库作为测试目标。它仅从受控 `DATABASE_URL` 取得连接凭据；账号须能创建和删除数据库。请使用专用本地验收 PostgreSQL 18.6 服务。输出目录必须尚不存在，避免覆盖旧证据。

在 `backend/` 执行：

```powershell
# API、迁移、真实 TCP 权限及空闲 Worker 启动检查
.\.venv-api\Scripts\python.exe -m scripts.verify_module3 --suite api
# 再运行 ASR 与 OCR 环境中的 CPU 单元测试
.\.venv-api\Scripts\python.exe -m scripts.verify_module3 --suite all
# 如环境不在默认目录，可传 --asr-python 和 --ocr-python 的绝对路径。
```

执行内容包括空库 `upgrade head → downgrade base`、模块二 `0004` 合成数据准备、升级至 head、回退至 `0004`、再升级；逐表比对原有列的行数与 SHA-256。模块三新增列不参与旧列比对。临时库在退出时清理；证据目录与合成音频保留在 `backend/var/verification/`。报告记录时间、提交及工作区状态、源码/锁文件哈希、依赖版本、每步退出码、原始日志、JUnit 结果和证据文件哈希。

API 环境的 pytest 会跳过依赖 torch/cv2 的用例；`--suite all` 随后在对应环境补跑。专用 unittest 入口遇到跳过、零用例、失败或解释器版本不符均返回非零，防止把缺失环境当作通过。

`.github/workflows/module3.yml` 对 develop/main 的 PR 及 develop/模块三功能分支推送执行 Windows API 检查，使用 Python 3.13.16、带哈希 API 锁文件和带哈希校验的 PostgreSQL 18.6 二进制包。ASR/OCR 完整锁文件体积较大，通过手动运行工作流并勾选 `processing_tests` 启用；不要求 GPU，不运行真实模型或付费调用。Actions 与 Windows 镜像能力依据 [GitHub 官方 Action 文档](https://github.com/actions/setup-python) 和 [Windows 镜像清单](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md) 配置。

CI 会保存日志/JSON/JUnit 为 artifact；工作流文件存在不等于远端运行已通过，应以对应提交的实际 Check Run 和 artifact 为准。`PASS_TECHNICAL` 只表示声明范围内的技术检查通过；TCP 检查验证登录权限，Worker 检查验证空队列独立进程启动，不代表真实材料端到端推理。真实文本/扫描件逐题质量、标注语义和整套人工核听继续按第 3—6 节单独执行。本次开发复验也不冒充接收方独立验收。
