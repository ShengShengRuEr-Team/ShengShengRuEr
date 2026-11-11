# 模块二后端验收指南（给验收人）

- 被验收分支：`feature/m2-backend-listening-papers`（基于 `develop` @ `6af6197`，提交数不写死，以 `git log --oneline develop..HEAD` 实际结果为准）
- 验收依据：`docs/development/module-2/design.md` V1.0 第 7 节、需求文档验收项 B01–B16
- 流程要求（需求 §2）：**一人开发、两人独立验收**；两人均通过后由开发提交施博宇决定合并。
- 本指南目标：你不需要问开发者任何问题，也不需要读全部源码，就能把可自动验证的部分跑完并留下记录。

---

## 1. 先明确：这次验收覆盖什么、不覆盖什么

| 覆盖 | 不覆盖 |
| --- | --- |
| 迁移可在空库重建、可在第二套库复现 | **B16 内容核对**：25 题逐题比对原卷与答案解析、整套 1416 秒音频核听——必须真人做，见第 7 节 |
| 6 个接口的返回结构、权限、字段裁剪 | 前端页面与播放器交互（本阶段不开发） |
| 学生可见性三态与取消后拒绝访问 | 模块三的上传/OCR/ASR/自动标注 |
| 音频 Range 分段与完整下载 | 词典与标注表（`skill`、`error_cause`、`evidence`、07A–07D 等 9 张） |
| 导入幂等、失败整体回滚、批次切换 | 真实高并发与生产级压测 |
| 重启持久化、断库明确报错、模块一无回归 | 部署到服务器（本期只要求本地可运行） |

**已声明不做、不算缺陷的**（详见开发文档 §11.2 与 `docs/development/module-2/schema-alignment.md`）：

1. 学生详情里**没有**答案、解析、原文片段——这是设计要求，服务端组装时已剔除，不是漏字段。
2. 学生访问不可见试卷统一返回 **404**（不区分"不存在"和"无权"），避免泄露是否存在。
3. 音频 `Content-Type` 是 `audio/mp4` 而文件后缀是 `.mp3`——源文件本身是 AAC/M4A 容器、只是后缀错，导入时未转码，哈希与来源清单一致。
4. 主键统一叫 `id`、外键 `<实体>_id`，与 16 表字段表的 `question_id` / `segment_id` 命名不同，是仓库 `docs/development/naming-conventions.md` 的约定，语义等价。
5. 9 张词典/标注/关系表本期未建，按审核结论"只建最小业务子集"。
6. 25 题的 `review_status` 全部是 `待审核`——数据来自试填工作簿，**没有**经过人工审核，这是有意保留的真实状态。

---

## 2. 拿到代码

### 方式 A：分支已推到远端（推荐）

```bash
git fetch origin
git switch -c feature/m2-backend-listening-papers origin/feature/m2-backend-listening-papers
```

### 方式 B：用离线包（开发者给你 `m2-review.bundle`）

离线包是**自包含**的，不需要联网、也不需要先有 `develop`，直接克隆即可：

```bash
git clone -b feature/m2-backend-listening-papers m2-review.bundle ShengShengRuEr
cd ShengShengRuEr
git log --oneline -5      # 确认能看到模块二的提交
```

> 如果 `git clone` 报 `Repository lacks these prerequisite commits`，说明拿到的是增量包而不是自包含包，请找开发者重新打包（命令：`git bundle create m2-review.bundle feature/m2-backend-listening-papers`）。

验收时请记下实际 commit：

```bash
git log --oneline -2
```

---

## 3. 准备环境

### 3.1 Python 3.14

```bash
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe --version     # 应为 3.14.x
```

### 3.2 PostgreSQL 18.6

任选一种装法，**只要求 18.6、监听 127.0.0.1:5432**：

- 官方安装包（EDB installer），或
- EDB 免安装 zip：解压后 `initdb` 到一个**纯英文路径**（中文路径会让 `initdb` 找不到 `share/postgres.bki`），再 `postgres -D <pgdata> -p 5432` 启动。

> **已知坑（Windows）**：如果 `initdb` 在 `performing post-bootstrap initialization` 阶段报 `0xC0000005`，用事件查看器看"应用程序错误"里的**故障模块**。若指向某个软件目录下的旧版 `MSVCP140.dll`（如 Java JRE 自带的 14.16），说明 PATH 里该目录先于系统目录，PostgreSQL 加载了旧版 VC++ 运行时。解决办法：把 14.40+ 的 `msvcp140.dll`、`vcruntime140.dll`、`vcruntime140_1.dll` 复制到 `pgsql/bin/`（DLL 优先同目录）。**换 PostgreSQL 版本解决不了这个问题。**

建两套库：

```bash
psql -h 127.0.0.1 -U postgres -c "CREATE DATABASE shengshengruer;"
psql -h 127.0.0.1 -U postgres -c "CREATE DATABASE shengshengruer_test;"
```

### 3.3 本机配置

复制 `backend/.env.example` 为 `backend/.env`，改这三项：

```text
DATABASE_URL=postgresql+psycopg://postgres:<你的密码>@127.0.0.1:5432/shengshengruer
JWT_SECRET_KEY=<至少 32 位随机串>
AUDIO_STORAGE_DIR=var/audio
```

> `.env` 已被 `.gitignore` 忽略，**不要提交**。

---

## 4. 导入样例数据

材料在开发者给你的 `materials/` 目录（**不进 Git**，真题与音频不得入仓）：

| 文件 | 用途 | SHA-256（前 16 位） |
| --- | --- | --- |
| `CET4_2025_06_1_听力.m4a` | 导入与核听 | `a23dc74f40f8b980` |
| `2025年6月四级第一套_听力采集试填_16表版_20261024.xlsx` | 结构化导入的源 | `23b62693ef7df7a0` |
| `schema_options_merged_16tables.json` | 16 表字段基线 | `6348030d2b5acb49` |
| `import_payload.json` | 已生成的结构化导入文件 | 见文件内 `meta.source_xlsx_sha256` |

先核哈希（防止材料在传递中损坏）：

```bash
python -c "import hashlib,sys;[print(hashlib.sha256(open(f,'rb').read()).hexdigest()[:16], f) for f in sys.argv[1:]]" ../materials/*
```

然后迁移 + 种子 + 导入：

```bash
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m app.seed
.venv/Scripts/python.exe -m app.import_module2 \
  --input  ../materials/import_payload.json \
  --audio-file ../materials/CET4_2025_06_1_听力.m4a
```

期望输出：`"status": "imported"`，计数 `passages=8, transcript_segments=165, questions=25, presentations=25`。

---

## 5. 一键自检（先跑这个）

```bash
.venv/Scripts/python.exe -m scripts.verify_module2_all
```

它会自己起一个临时服务（8010 端口），依次检查环境、数据、pytest、模块一验收、模块二验收，最后打印汇总。

**期望退出码为 0，全部已执行项目通过。总项数随提交变化，记录实际输出；历史提交曾输出 17/17。**

如果有 FAIL，把该行原文和完整输出发给开发者，不要自己改代码。

---

## 6. 逐项核查（B01–B16，与需求文档验收表逐条对应）

下表"通过标准"一列取自需求文档第 6 节验收表原文，"操作"是达成该标准的可执行步骤，"手/自"列标 ✅ 的项可由第 5 节脚本自动覆盖（仍建议抽验一次），标"手工"/"流程"的必须人工执行并留证据。

| 编号 | 通过标准（需求原文摘要） | 操作 | 手/自 |
| --- | --- | --- | --- |
| B01 | 复用模块一后端与认证权限，不重做登录 | `git diff develop -- backend/app/main.py backend/app/api/deps.py backend/app/api/auth.py`：只应看到模块二路由挂载与依赖新增；用 `admin/admin123`、`student/student123` 调模块一登录接口仍成功 | 手工 |
| B02 | 在开发或测试 PostgreSQL 执行迁移与导入，能查到真实业务记录；接口查询结果与数据库一致，不由静态响应替代 | ① 第 4 节在新库执行迁移+导入，`psql` 查 `questions`/`passages`/`presentations` 有 25/8/25 行；② 取接口返回的第 3 题题干，与 `psql` 查出的同题题干逐字比对；③ 对 `shengshengruer_test` 重复①②；④ `alembic downgrade 0001` → `downgrade base` → `upgrade head` | 手工 |
| B03 | 对照选定原卷，**全部**题组和题目完整，题干、题号及选项顺序对应 | 调管理员配套接口取 25 题，**逐题**（不得抽样）与原卷 PDF 比对：题干、A–D 四项的文字与顺序、题号 1–25 连续、8 个篇章归属 | 手工 |
| B04 | 管理员可查询标准答案、解析、听力原文及必要状态 | `GET /api/v1/admin/listening-papers/1/companion`（admin token）：25 题均含 `correct_option`、`explanation_text`、`explanation_source`；`passages[].segments` 含正文与起止时间；含 `is_current`、`check_passed`、`is_visible`、`review_status` | 手工 |
| B05 | 学生返回内容不包含标准答案、解析和听力原文；录音问题题干正常返回 | `GET /api/v1/listening-papers/1`（student token）：响应全文搜不到 `correct_option`、`explanation_text`、`explanation_source`、`segments`；`question_text` 均非空，抽一题与 `psql` 中 `segment_type='question'` 的文本核对 | 手工 |
| B06 | 学生不能调用管理员专属接口、修改可见性或读取不可见试卷；管理员管理全部题库，不按导入人限制 | student token 调三个 `/admin/...` 均 403；无 token 401；取消可见后学生读详情/音频均 404；用另一管理员账号（或同账号）管理该卷不受导入人限制 | 手工 |
| B07 | 可**实际读取、解码并核听**绑定正确的整套音频；学生不能绕过试卷权限读取音频 | ① `Range: bytes=0-1023` → 206 且 `Content-Range: bytes 0-1023/4169648`；② 无 Range → 200、长度 4169648、`Content-Type: audio/mp4`；③ **用播放器打开该 URL 实际播放并拖动进度条**，确认与真题音频一致；④ 取消可见后学生请求 404 | 手工 |
| B08 | 确认与取消及记录持久；检查未通过时拒绝确认并说明原因，但**允许取消可见**；取消后列表不返回该卷，详情与音频拒绝 | 确认→学生可见；取消→列表不含、详情与音频 404；重启后端再查一次；`psql` 查 `paper_visibility` 与 `visibility_audit_logs`；把某题 `content_state` 改成 `待补齐`→确认被 400 拒绝且给出题号→**此时仍能取消**（应当成功） | 手工 |
| B09 | 整卷数据属于同一当前批次，不混入草稿或失败批次；新批次不继承旧批次可见确认；导入失败不影响原当前批次；可见性不改变其他审核和验收状态 | ① 确认可见后重复执行第 4 节导入：返回 `noop`，**可见确认仍在**；② `psql` 查 `passages/questions/presentations` 的 `batch_id` 是否全部等于当前批次；③ 改坏 payload 触发失败导入：原批次仍 `is_current`、学生仍可见；④ 查 `import_batches` 无 `pending`/`failed` 残留批次；⑤ 确认/取消可见前后，25 题 `review_status` 不变 | 手工 |
| B10 | 不存在、无权访问、空数据及音频不可读取等情况均有明确响应 | 请求不存在的试卷 id→404；学生读不可见卷→404；查无数据的试卷（如先取消可见）→空列表而非 500；把音频文件临时改名→音频接口返回明确错误而非 500 堆栈 | 手工 |
| B11 | 来源字段、接口字段、类型与角色可见范围对应明确，接口说明足以支持后续前端对接 | 对照 `docs/development/module-2/api.md` 与开发文档第 4 节「功能—来源表和字段—接口字段—角色可见范围」：任取 3 个接口字段，能追到来源列与角色范围 | 手工 |
| B12 | 两名验收人员分别记录结论；存在未通过项时修正并复验，均通过后再提交施博宇 | 两位验收人各出一份记录（格式见第 8 节），不得共用；有未通过项时由开发者修正后**复验同一项**并记录 | 流程 |
| B13 | 相同材料重复导入无重复记录，不无故切换批次或清除已有可见确认；可控错误导入失败后不留下半套试卷、不污染当前数据 | 同 B09 ①②③；另核对重复导入前后 `import_batches` 行数不变、`questions` 仍 25 | 手工 |
| B14 | 重启后端后，试卷、题目、批次和可见性仍可正常查询；断开数据库时明确报错，不回退到写死样例伪装成功 | 重启服务后重查列表/详情/音频/检查结果；停掉 PostgreSQL 再请求 → 数秒内返回 `{"code":500,...}`，不返回任何题目内容；恢复数据库后自动重连 | 手工 |
| B15 | 新增迁移与功能不破坏已有账号、登录、退出、角色及基础鉴权 | `.venv/Scripts/python.exe -m pytest` → `18 passed`；`python -m scripts.acceptance` → `8/8 通过` | ✅ |
| B16 | 样例材料与来源清单固定，全部题干、选项、答案、解析与原文对应核对，整套音频完成核听，附真实核对与问题修正记录；历史待审核试填不直接作为人工审核通过依据 | 按 `docs/acceptance/module-2/content-check-record.md` 逐题填写并**完整核听 1416 秒音频**；记录放受控目录，不进 Git | 手工 |

> 手工调接口可用 `http://127.0.0.1:8010/docs` 的 Swagger 页面（账号 `admin/admin123`、`student/student123`）。
> B03 的"全部题目"是需求原文要求，**不接受抽样**；B07 的"核听"是需求原文要求，只看 `Content-Type` 不算通过。

---

## 7. 关于 B16（必须真人做，不能省）

数据库里 25 题的 `review_status` 全部是 `待审核`，`collector` 是"人工整理导入（试填数据，未经人工核听）"。这不是漏填，是**这批数据确实没有经过人工审核**：

- 英文转写与时间戳沿用历史自动对齐结果；
- 新标注为试标；
- 需求 §3.3 明确：历史试填中的自动转写、时间对齐与待审核记录**不**直接视为人工审核通过。

要做 B16，就拿第 4 节的材料，按 `docs/acceptance/module-2/content-check-record.md` 逐题填，并**完整播放整套 1416 秒音频**（不是抽样）。填好的记录放本机受控目录，不进 Git。

**B16 没完成之前，模块二不能算验收通过**，即使前面 17 项全绿。

---

## 8. 记录与回执

**记录的效力范围**：需求文档没有指定验收人员或验收环境（§2 修订说明第 10 行），因此本指南不额外设门槛。但验收项本身要求"实际执行"——B02 要求在 PostgreSQL 上执行迁移与导入并比对接口与库、B07 要求实际读取解码并核听、B14 要求重启与断库——**没有运行环境的记录无法覆盖这些项**。

因此：只做了代码阅读、或环境不满足（如 Python 3.12、无 PostgreSQL）的记录，可以作为参考意见附在验收材料里，但**不能据此判 B02/B03/B07/B14 通过**，也就不能作为 B12 要求的两份"通过"结论之一。

按 B12，两位验收人各自记录结论；若存在未通过项，由开发者修正后**复验该项**并记录，两人均通过后再提交施博宇。

每人独立出一份记录（两人不得共用一份）。建议格式：

```text
验收人：<姓名>        日期：<YYYY-MM-DD>
被验收 commit：<git rev-parse --short HEAD>
环境：Python <x.y.z> / PostgreSQL <18.6> / OS <...>

一、一键自检
命令：python -m scripts.verify_module2_all
结果：<实际通过项数/总项数与失败项>

二、逐项核查（B01–B16）
B01：<操作> → <实际输出>
...
B16：<是否完成，核对人，结论>

三、发现的问题
- <问题> → <复现步骤> → <期望 vs 实际>

四、结论
□ 通过    □ 不通过（原因：<...>）
```

回执给开发者时，**请附上失败项的原始输出**，不要只写"有问题"。

---

## 9. 常见问题

| 现象 | 原因与处理 |
| --- | --- |
| `pytest` 把开发库数据清了 | 已在 `tests/conftest.py` 加护栏：engine 若绑到非测试库会直接报错。若你看到该报错，说明有测试模块在模块级 import 了 `app.*`，请勿删护栏，把报错原文发给开发者 |
| 本机接口莫名 404 / 空响应 | 环境里可能有 `HTTP_PROXY`。验收脚本已用 `trust_env=False`；手工 curl 时加 `--noproxy '*'` |
| `alembic upgrade head` 报连不上库 | 确认 PostgreSQL 在跑、`.env` 的密码对、库已建 |
| 音频接口 500 且日志里有 `UnicodeEncodeError` | 只可能出现在旧代码上；当前版本已按 RFC 5987 编码中文文件名。请确认 commit 正确 |
| 时间对不上 | 时间戳统一 UTC 存储，接口返回 ISO 8601 带时区，属正常 |
| `git clone m2-review.bundle` 报缺前置提交 | 拿到的是增量包；要求开发者用 `git bundle create <文件> feature/m2-backend-listening-papers` 重新打包（自包含） |


## 扩展复验修复版：建立原卷题量基准

本节适用于 `fix/module2-recheck-20261104` 及包含该修复的后续提交，优先于上文旧版导入步骤。`alembic upgrade head` 后应为 `0004_expected_count_source`。从旧版升级会使无来源的历史基准失效，须补录并重新确认可见。

在仓库根目录整理材料时，显式提供核定题量和独立原卷：

```powershell
.\backend\.venv\Scripts\python.exe scripts/prepare_module2_materials.py `
  --xlsx "<受控材料目录>/2025年6月四级第一套_听力采集试填_16表版_20261024.xlsx" `
  --out "<受控输出目录>" `
  --expected-question-count 25 `
  --count-source-file "<受控材料目录>/CET4_2025年6月_第1套_真题.pdf" `
  --count-source-locator "原卷第1—2页，Part II Listening Comprehension，题号1—25"
```

这里的 25 仅适用于已选定样例，其他试卷须对照各自原卷登记。脚本计算原卷 SHA-256，但题量及定位说明由实际核对者负责，不能从导入题目数自动推定；这不等于 B16 全内容人工核对完成。

再在 `backend` 目录执行迁移、种子与 `python -m app.import_module2 --input "<受控输出目录>/import_payload.json" --audio-file "<对应真实音频>"`。不提供题量依据时也可导入待核对材料，但预检须显示缺少基准，确认开放返回 400，学生不能访问。

来源字段为 `exam_paper.expected_question_count_source`，对象包含 `document`（文件名）、`sha256`（64位小写十六进制）、`locator`（原卷定位）；与正整数 `expected_question_count` 同时提供。只给题量、不给来源会拒绝导入。保存后不可由后续批次静默改写。

回归时至少保留：已有版本文件中途失败、已有版本文件提交失败、新建文件提交失败、复制中断、首次24题无基准、可信25题基准下24题、旧版已开放缺题数据升级后的阻断。原始证据包与 [修复验证记录](fix-20261104.md) 对应保存。
