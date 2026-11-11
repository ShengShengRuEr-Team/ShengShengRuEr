# 模块二前端 · 真实环境复验手册（E2E Runbook）

- 日期：2026-11-10
- 目的：解决复验报告问题 1（无 `.env`、无 `psycopg`、无 PostgreSQL、pytest 34 项 setup error），使 F07 真实链路与 F13 持久化可验证
- 适用：Windows x64；命令以 Git Bash 为例，PowerShell 等价

## 0. 结论先行

复验机的后端**根本没有装起来**：`backend/.venv` 不存在、`backend/.env` 不存在、`psycopg` 未安装、5432 无监听。前端代码与文档不是阻塞点，按下面 1–6 步即可恢复。

## 1. 准备解释器与数据库

```bash
py -3.13 -V                  # 必须 3.13.x（V1.2 基线 3.13.16）
psql --version               # 18.x（基线 18.6）
```

- 没有 3.13：装 Python 3.13.16，再用它建 venv（**不要**沿用 3.12/3.14）。
- 没有 PostgreSQL：用免安装 zip 解压到受控目录，`initdb` 建库目录，启动时只监听 127.0.0.1。

## 2. 建后端环境与配置

```bash
cd backend
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -U pip
.venv/Scripts/python -m pip install -r requirements.txt      # 含 psycopg[binary]==3.3.6
cp .env.example .env                                          # 然后编辑 .env
```

`.env` 至少填三项：

```text
DATABASE_URL=postgresql+psycopg://postgres:<密码>@127.0.0.1:5432/shengshengruer
JWT_SECRET_KEY=<任意足够长的随机串>
AUDIO_STORAGE_DIR=var/audio
```

> 复验报告里的 `RuntimeError: 未找到 DATABASE_URL` 就是因为缺这个文件。

## 3. 建库、迁移、种子

```bash
createdb -h 127.0.0.1 -U postgres shengshengruer          # 已存在则跳过
.venv/Scripts/python -m alembic upgrade head               # 必须到 head
.venv/Scripts/python -m app.seed                           # admin/admin123、student/student123
```

**踩坑提示：** 迁移没到 head 时，`exam_papers.expected_count_source` 不存在，`/companion` 会直接 500（表现为页面“无法加载试卷详情”）。本次整改就是在本机补跑 `alembic upgrade head` 修好的。

## 4. 跑后端测试（放行的第 1 个条件）

```bash
.venv/Scripts/python -m pytest -q
```

期望：**34 passed**，无 setup error、无 skip。若仍 setup error，回到第 2 步检查 `.env`。

## 5. 导入样例并起服务

材料按仓库规范不入库（版权/体量），从受控资料包取得 `import_payload.json` 与音频：

```bash
.venv/Scripts/python -m app.import_module2 \
  --input "<受控目录>/import_payload.json" \
  --audio-file "<受控目录>/CET4_2025_06_1_听力.m4a"

.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
cd ../frontend
npm ci            # 不要 npm install
npm run dev       # 127.0.0.1:5173
```

## 6. 两条必验真实链路（放行的第 2 个条件）

### 6.1 新卷 → 确认 → 学生可见（F07 主链路）

1. 用导入工具导入一套**全新**试卷（无检查记录）。
2. 管理员打开详情：应显示「尚未检查」，**「确认开放」可点击**，页头出现"确认会先重新执行检查"提示。
3. 点确认 → 提交：
   - 数据合规：变为「检查通过 / 已确认开放 / 当前可访问」，且 `content_checks` 新增一条 `passed` 记录；
   - 数据不合规：返回 400 并列出问题，抽屉出现新失败记录，**按钮仍可再点**（修数据后重试）。
4. 学生登录刷新列表：应看到该卷；`GET /api/v1/listening-papers` 含该 `exam_paper_id`。

核对 SQL（可选）：

```sql
SELECT exam_paper_id, is_passed, checked_at FROM content_checks ORDER BY id DESC LIMIT 3;
SELECT exam_paper_id, batch_id, is_visible FROM paper_visibility ORDER BY id DESC LIMIT 3;
```

### 6.2 取消 → 学生拒绝（F08/F13）

1. 管理员取消开放。
2. 学生新请求列表应为 `[]`；详情与音频返回 404。
3. 重启后端进程后，再查一次：状态保持。

## 7. 复验要留的证据

- `pytest -q` 输出（34 passed）
- 两条链路的页面截图 + 对应 SQL 查询结果
- 重启前后的状态对比（F13）
- 若失败，记录：接口、状态码、响应体、复现步骤

## 8. 不在本手册范围

- 真实 23:36 音频的整段下载与拖动（需真实样例，按第 5 步导入后自然覆盖）
- 列表 >20 套降级（需造 20+ 试卷）
- 移动端与视觉体系、作答/判分（任务三）
