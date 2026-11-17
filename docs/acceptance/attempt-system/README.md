# 作答系统验收指南（任务二 / 模块三作答）

> 日期：2026-11-16（含 PR #16 独立验收整改）  
> 代码：`D:\ssre_V1\ShengShengRuEr`，`feature/attempt-system`（PR #16；基线 `main@846270b`）  
> 需求：V1.2；开发：V1.1；原型：图集 V1.1（评审结论“通过”，签字按用户指示暂不处理）

## 1. 阅读顺序

| 文档 | 用途 |
| --- | --- |
| [PR16 二次整改说明](PR16-二次整改说明-20261117.md) | **二次整改先读**：F08/F09 修复、复验命令、未关闭项 |
| [PR16 一轮整改说明](PR16-整改说明-20261116.md) | F01–F07 修复、复验命令 |
| [验收交接](验收交接文档.md) | **验收人入口**：结论、环境、快速复核、BLOCKED 裁定项 |
| [验收矩阵](acceptance-matrix.md) | AC-01–AC-50、B-01–B-16、R-01–R-08、E2E 1–20、F01–F07 逐项结果与证据 |
| [任务卡回填](report.md) | 每张任务卡的实际改动、未提交差异、测试、未覆盖项、下一步 |
| [接口契约](../../development/attempt-system/api.md) | API-1/API-3 字段、错误码、幂等、单快照 |
| [实施记录](../../development/attempt-system/implementation.md) | 文件清单、N01–N08 落地 |
| [需求口径同步](../../requirements/attempt-system/attempt-system-sync-20261116.md) | P-01/P-03/API-3/实现差异 |
| [截图与结果](screenshots/) | 真实浏览器 E2E 截图、`e2e-results.json`（18 项） |
| [证据目录](evidence/) | pytest/ruff/npm test/typecheck/build/E2E 原始输出 |

## 2. 环境（本次实际）

| 项 | 值 |
| --- | --- |
| Node / npm | 24.14.0 / 11.9.0 |
| Python（backend/venv） | 3.12.10 |
| PostgreSQL | 16（服务 `postgresql-x64-16`，监听 `127.0.0.1:5433`） |
| 前端 | Vite 8.3.5、React 19.3.1、antd 6.6.8 |
| 测试 | Vitest 5.1.0、jsdom 28.1.0、RTL 16.3.3、user-event 14.6.1；pytest 9.2.0 |
| 浏览器 | 本机 Microsoft Edge（Playwright Core 1.56.1，无额外浏览器下载） |

> `backend/.env` 的 `DATABASE_URL` 写的是 5432，本机实际 5433。所有测试/启动命令通过环境变量覆盖端口，**不修改 `.env`、不输出密码明文**。

## 3. 自动化门禁复现

```powershell
# 后端（backend 目录；从 .env 读取连接串并仅替换端口，不打印）
$u = ((Select-String -Path .env -Pattern '^DATABASE_URL=' | Select-Object -First 1).Line -replace '^DATABASE_URL=','')
$env:DATABASE_URL = ($u -replace '@127\.0\.0\.1:5432/','@127.0.0.1:5433/')
.\venv\Scripts\python.exe -m pytest
# 预期 265 passed, 1 warning
```

```powershell
# 前端（frontend 目录）
npm test          # 预期 18 files / 129 tests passed（含 PR16 定向回归 12 项）
npm run typecheck # 预期退出 0、无输出
npm run build     # 预期 built in …（仅 chunk 体积提示）
```

原始输出见 `evidence/`。

## 4. 真实链路复现

### 4.1 独立 E2E 库与试卷（不写开发库/测试库）

```powershell
cd backend
$u = ((Select-String -Path .env -Pattern '^DATABASE_URL=' | Select-Object -First 1).Line -replace '^DATABASE_URL=','')
$e2e = (($u -replace '@127\.0\.0\.1:5432/','@127.0.0.1:5433/') -replace '/shengshengruer$','/shengshengruer_e2e')
$env:DATABASE_URL = $e2e
.\venv\Scripts\python.exe scripts\e2e_attempt_setup.py
# 输出 3 套试卷 + 第二学生 e2e_student_b
```

> 若 E2E 库是上一轮遗留、`alembic_version` 指向已删除版本：删除该 **E2E 专用库**后重建（不要动开发库/测试库）。

### 4.2 启动后端与前端

```powershell
# 终端 A（仍用 E2E 库）
cd backend
$env:APP_ENV='development'
$env:DATABASE_URL = <4.1 的 $e2e>
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 终端 B
cd frontend
npm run dev
```

### 4.3 运行真实浏览器与真实 API 验收

```powershell
cd frontend
node scripts\e2e_attempt.mjs
# 预期 21 项 PASS（登录/列表四态/门禁/选择标记/刷新恢复/提交汇总/只读/
# 受保护字段/多标签终态/1440+1280+1024 提交栏视口/PR16 F01/F02/F04/F05/F06/F08/F09/管理员）

cd ..\backend
.\venv\Scripts\python.exe scripts\e2e_attempt_api.py
# 预期 {"total": 23, "failed": 0}
```

> 浏览器脚本会清理本机 `ssre.attempt*` 记录；**每轮完整 E2E 前请重跑 4.1 的 setup**（重置三套试卷与作答）。
> 脚本输出目录默认 `docs/acceptance/attempt-system/screenshots/`；可用 `E2E_OUT_DIR`、`E2E_BROWSER`、`E2E_APP_URL` 覆盖。

## 5. 手工验收建议（覆盖 BLOCKED / 未闭环组合）

1. 401 提交中：交卷前清除 token，确认保留信封、登录回跳后 API-3 查询。
2. E04：提交前由管理员/脚本切换当前批次，确认提示「内容已更新」并清空答案/信封。
3. AC-35：pending 期间换批，分别观察 API-3 true/false/失败三种结果均不误删信封。
4. AC-38：双页签分别制造「后台挂起」（隐藏页面后再操作）与「即将关闭」（`pagehide` 时仍有待保存 timer）。
5. 真实 500：代理层注入 API-3 500，确认只读缓存标注“本机保存，仅供参考”。
6. 空卷：全部未答提交，确认强提示与 0%。
7. 音频：真实音频核听；失败时播放器内重试且不阻塞作答。

## 6. 证据目录

```text
docs/acceptance/attempt-system/
├─ README.md  handoff.md  report.md  acceptance-matrix.md
├─ e2e-api-results.json
├─ evidence/（pytest / ruff / npm test / typecheck / build）
└─ screenshots/（E2E 截图 + e2e-results.json）
```
