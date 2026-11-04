# 模块二后端交付说明（2026-11-03）

- 基线：`develop` @ `6af6197`（与需求文档 §1.1 记录一致）
- 依据：`docs/module-2-backend-development.md` V1.0、`docs/module-2-backend-tasks.md` V1.0
- 结论：**代码可运行、可复现、自动化验收全部通过**；**B16（人工逐题核对与整套核听）未完成**，需真实人员执行。

## 一、交付内容

### 代码

| 类别 | 文件 |
| --- | --- |
| 模型 | `backend/app/db/models_listening.py`（11 张表） |
| 迁移 | `backend/alembic/versions/0002_module2_listening_papers.py` |
| 数据访问 | `backend/app/repositories/listening.py` |
| 业务服务 | `backend/app/services/content_check.py`、`services/visibility.py` |
| 接口 | `backend/app/api/listening_papers.py`（学生 3 个）、`backend/app/api/admin_listening_papers.py`（管理员 3 个） |
| 音频 | `backend/app/core/audio_response.py`（Range 206 / 416 / 200） |
| 导入工具 | `backend/app/import_module2.py` |
| 验收脚本 | `backend/scripts/acceptance_module2.py` |
| 测试用例 | `backend/tests/test_module2_listening.py`（7 个） |
| 材料整理 | `scripts/prepare_module2_materials.py`（试填 xlsx → 结构化导入文件 + 自动预检） |

### 文档

| 文件 | 内容 |
| --- | --- |
| `docs/module-2-backend-development.md` | 开发文档 V1.0：工程调研、表设计、功能—字段—接口—角色对照表、接口契约、导入方案、B01–B16 验证方法、审核结论、实现与证据 |
| `docs/module-2-backend-tasks.md` | 任务卡 V1.0：T01–T09 依赖、改动文件、验收标准，附实现状态表 |
| `docs/api/listening-papers.md` | 6 个接口的完整契约（含样例、错误码、状态口径） |
| `docs/module-2-schema-alignment.md` | 与 16 表基线的逐字段比对、枚举对齐、未建 9 张表的理由 |
| `docs/module-2-acceptance-guide.md` | 验收指南：环境、材料、一键自检、B01–B16 核查表、记录模板、常见问题 |
| `docs/module-2-content-check-record.md` | B16 逐题核对与核听记录**空模板**（25 行） |
| `docs/module-2-delivery-report.md` | 本文件 |

### 环境改动（仅本机，无一条进仓库）

1. `backend/.env`（真实库密码、音频目录，已被 `.gitignore` 忽略）。
2. `backend/.venv`（Python 3.14.10）。
3. PostgreSQL 18.6 免安装实例：`C:\Users\win\AppData\Local\ssre_pg`，数据目录 `pgdata`，端口 5432，仅监听 127.0.0.1。
4. **VC++ 运行时修复**：把 14.44.35211 的 `msvcp140.dll` / `vcruntime140.dll` / `vcruntime140_1.dll` 放入 `pgsql/bin`。原因是本机 PATH 里 Java JRE 目录靠前，PG 18 加载了其中的旧版 `MSVCP140.dll`（14.16），在 post-bootstrap 阶段访问违规崩溃。**换 PG 版本不能解决这个问题。**

## 二、复现步骤

```bash
# 1. 启动数据库（本机为后台进程；重启机器后需重新启动）
# <PG_DIR> 为本机 PostgreSQL 解压目录，<PG_DATA> 为数据目录，按自己机器替换
"<PG_DIR>/bin/postgres.exe" -D "<PG_DATA>" -p 5432 -c listen_addresses=127.0.0.1

# 2. 建库（首次）
psql -h 127.0.0.1 -U postgres -d postgres -c "CREATE DATABASE shengshengruer;"
psql -h 127.0.0.1 -U postgres -d postgres -c "CREATE DATABASE shengshengruer_test;"

# 3. 迁移 + 种子 + 导入（在 backend 目录）
cd backend
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m app.seed
.venv/Scripts/python.exe -m app.import_module2 \
  --input  "<受控目录>/import_payload.json" \
  --audio-file "<受控目录>/CET4_2025_06_1_听力.m4a"

# 4. 启动服务 + 验收
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
.venv/Scripts/python.exe -m scripts.acceptance_module2
.venv/Scripts/python.exe -m pytest
```

> 注意：`pytest` 只操作 `shengshengruer_test`。`tests/conftest.py` 已加护栏——若 engine 误绑开发库会立刻报错，不再静默清空开发库。

## 三、验证结果（实际执行）

| 项 | 结果 |
| --- | --- |
| 迁移 `upgrade head` | 通过，新增 11 张表（合计 16 张） |
| 16 表字段比对 | 7 张业务表逐字段对齐；14 个字段补齐、5 处类型放宽、1 处枚举修正 |
| 来源字段脱敏 | 导入文件与库内本机盘符路径 0 条；`meta.source_xlsx` 只留文件名，公开来源 URL 保留 |
| `content_state` 门槛 | 第 1 题改为 `待补齐` → 确认可见 400 并给出具体题目；改回 `可用` → 200 |
| 迁移 `downgrade base` / 重新 `upgrade` | 通过 |
| 第二套库复现迁移与导入 | 通过，与开发库完全一致 |
| 导入工具首次导入 | 1 卷 / 1 音频 / 1 批次 / 1 内容组 / 8 篇章 / 165 片段 / 25 题 / 25 映射 |
| 重复导入（幂等） | `noop`，记录数不变 |
| 失败导入（哈希不符 / 事务中途失败） | 整体回滚，无半套数据 |
| 模块二端到端验收 | **16/16 通过** |
| `pytest` | **18 passed**（模块一 11 + 模块二 7） |
| 模块一验收脚本 | **8/8 通过** |
| 重启后端 | 试卷、25 题、音频、可见性、检查结果均持久 |
| 断开数据库 | 5.1 秒返回 `{"code":500,"msg":"服务器内部错误"}`，无写死样例；恢复后自动重连 |

## 四、未完成项与下一步

1. **B16 内容核对（阻塞验收）**：需指定负责人，按 `docs/module-2-content-check-record.md` 逐题核对 25 题的题干、选项、标准答案、解析、原文对应，并**完整核听整套 1416 秒音频**。现有试填数据来自自动转写与自动对齐，按需求 §3.3 **不能视为人工审核通过**。
2. **字段表比对已闭环**（2026-11-03）：`schema_options_merged_16tables.json` 到位后完成 7 张业务表逐字段对齐，补齐 14 个字段、放宽 5 处类型、修正 1 处枚举默认值、新增 7 个 CHECK，并让 `content_state != 可用` 的题目阻断确认可见。详见 `docs/module-2-schema-alignment.md`。仍缺旧采集表 `四六级听力数据采集汇总_ljt.xlsx`（仅用于历史数据追溯，不影响本期验收）。
3. **合并流程**：本次改动在本地分支 `feature/m2-backend-listening-papers`，**未推送到远端**（需要仓库 Write 权限）。按流程应发 PR 到 `develop`，由两人独立验收后交施博宇合并。
4. **本机环境**：PostgreSQL 是本机后台进程而非系统服务，**机器重启后需手动启动**；如需长期使用，可考虑注册为 Windows 服务。

## 五、给学生端的接口自查提示

联调前端时可先确认三件事，避免把受限内容当接口缺口：

- 学生详情里**没有**答案、解析、原文片段是设计要求，不是缺字段；
- 未确认可见的试卷统一 404，不区分「不存在」和「无权」；
- 音频支持 `Range`，播放器可直接 seek；`Content-Type` 为 `audio/mp4`（源文件为 AAC 容器，仅扩展名为 mp3）。
