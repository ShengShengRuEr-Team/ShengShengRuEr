# 作答系统验收交接文档（验收人入口）

> 交接日期：2026-11-16  
> 代码位置：`D:\ssre_V1\ShengShengRuEr`  
> 分支/基线：`main@846270b`（已含 API-1 与 `0005_attempt_system`；工作区含本任务未提交改动）  
> 需求/开发/原型：V1.2 / V1.1 / 图集 V1.1（评审结论“通过”，签字按用户指示暂不处理）

## 1. 一页结论

| 项 | 结论 |
| --- | --- |
| 交付范围 | API-3（schema/仓储/服务/路由/测试）、前端作答域（作答/草稿/信封/提交/汇总/只读）、测试工具链、真实 E2E、文档同步 |
| 自动化门禁 | 后端 265 passed；前端 17 files / 117 tests passed；typecheck/build 通过；本次新增/修改文件 ruff 全绿（全仓与基线同为 178） |
| 真实链路 | 浏览器 E2E **11/11 PASS**；真实 API E2E **23/23 PASS** |
| 整轮验收 | **PARTIAL（有条件通过），最终由验收负责人裁定** |
| 阻塞/风险 | 无 FAIL/BLOCKED；核心项 AC-35/AC-38 为 PARTIAL（缺两真实组合）；UX-01 签字未回填；P-03 保留期未确认 |
| 是否可进入验收 | **可以**：主链路与核心契约均有可复现真实证据；请按 §6 对 PARTIAL 项裁定 |

> 本文件不替代独立验收：开发自测结果只作为待复核证据，最终结论由验收负责人按需求 §11 判定。

## 2. 交付物

| 交付物 | 位置 |
| --- | --- |
| 验收矩阵（AC/B/R/E2E 逐项） | [acceptance-matrix.md](acceptance-matrix.md) |
| 任务卡回填（改动/未提交差异/测试/未覆盖） | [report.md](report.md) |
| 复现指南（环境/命令/故障排查） | [README.md](README.md) |
| 接口契约（API-1/API-3/错误码/幂等/单快照） | [../../development/attempt-system/api.md](../../development/attempt-system/api.md) |
| 实施记录（文件清单/N01–N08 落地） | [../../development/attempt-system/implementation.md](../../development/attempt-system/implementation.md) |
| 需求口径同步（P-01/P-03/API-3/实现差异） | [../../requirements/attempt-system/attempt-system-sync-20261116.md](../../requirements/attempt-system/attempt-system-sync-20261116.md) |
| 真实浏览器截图 | [screenshots/](screenshots/) |
| 测试原始输出 | [evidence/](evidence/) |
| 真实 API 结果 | [e2e-api-results.json](e2e-api-results.json) |

## 3. 环境与基线（先核对）

| 项 | 实际值 | 备注 |
| --- | --- | --- |
| 仓库 | `D:\ssre_V1\ShengShengRuEr` | 工作区有未提交改动，无新迁移 |
| 基线 | `main@846270b` | **已含 API-1**；`alembic head = 0005_attempt_system` |
| Node / npm | 24.14.0 / 11.9.0 | `frontend/.node-version` |
| Python | `backend/venv` 3.12.10 | 用 venv 解释器 |
| PostgreSQL | 16，`127.0.0.1:5433` | `backend/.env` 写 5432，命令用环境变量覆盖端口（不改 `.env`、不输出密码） |
| 数据库迁移 | 无新增/修改 | 若库在 0004，先 `alembic upgrade head` |

> 端口覆盖写法（PowerShell，不打印连接串）：
>
> ```powershell
> cd backend
> $u = ((Select-String -Path .env -Pattern '^DATABASE_URL=' | Select-Object -First 1).Line -replace '^DATABASE_URL=','')
> $env:DATABASE_URL = ($u -replace '@127\.0\.0\.1:5432/','@127.0.0.1:5433/')
> ```

## 4. 15 分钟快速复核（先跑门禁）

```powershell
# 1) 后端
cd D:\ssre_V1\ShengShengRuEr\backend
$u = ((Select-String -Path .env -Pattern '^DATABASE_URL=' | Select-Object -First 1).Line -replace '^DATABASE_URL=','')
$env:DATABASE_URL = ($u -replace '@127\.0\.0\.1:5432/','@127.0.0.1:5433/')
.\venv\Scripts\python.exe -m pytest
# 预期：265 passed, 1 warning

# 2) 前端
cd ..\frontend
npm test          # 预期：17 files / 117 tests passed
npm run typecheck # 预期：无输出、退出 0
npm run build     # 预期：built in …，仅有 chunk 体积提示
```

原始输出见 `docs/acceptance/attempt-system/evidence/`。

## 5. 真实链路复核（约 20 分钟）

### 5.1 准备独立 E2E 库与试卷（不写开发库/测试库）

```powershell
cd D:\ssre_V1\ShengShengRuEr\backend
$u = ((Select-String -Path .env -Pattern '^DATABASE_URL=' | Select-Object -First 1).Line -replace '^DATABASE_URL=','')
$e2e = (($u -replace '@127\.0\.0\.1:5432/','@127.0.0.1:5433/') -replace '/shengshengruer$','/shengshengruer_e2e')
$env:DATABASE_URL = $e2e
.\venv\Scripts\python.exe scripts\e2e_attempt_setup.py
# 输出 3 套试卷（E2E_ATTEMPT_001/002/003）与第二学生 e2e_student_b
```

> 若该库是上一轮遗留、`alembic_version` 指向已删除的 revision，可先删除该 **E2E 专用库**再重建（不要动开发库/测试库）。

### 5.2 启动后端与前端

```powershell
# 终端 A（仍用 E2E 库）
cd D:\ssre_V1\ShengShengRuEr\backend
$env:APP_ENV='development'
$env:DATABASE_URL = <5.1 的 $e2e>
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 终端 B
cd D:\ssre_V1\ShengShengRuEr\frontend
npm run dev
```

### 5.3 运行真实 E2E 与真实 API 验收

```powershell
cd D:\ssre_V1\ShengShengRuEr\frontend
node scripts\e2e_attempt.mjs
# 预期 11 项 PASS：登录/列表四态/门禁/选择标记/刷新恢复/提交汇总/只读/
# 受保护字段/多标签终态/1280+1024 断点/管理员

cd ..\backend
.\venv\Scripts\python.exe scripts\e2e_attempt_api.py
# 预期 {"total": 23, "failed": 0}
```

> 浏览器脚本会清理本机 `ssre.attempt*` 记录；**每轮完整 E2E 前请重跑 5.1 的 setup**（重置三套试卷与作答），否则已提交试卷会让列表直接进入只读。

## 6. 逐项验收指引（按矩阵）

1. **功能主链路**（AC-01–05、AC-09–12、AC-16–18、AC-23/24）：看 `screenshots/e2e-02…06` 与 `e2e-results.json`，对照页面截图确认“作答→确认→汇总→刷新只读”。
2. **API-3 契约**（B-01–B-16、AC-21/22/43/45/48）：看 `e2e-api-results.json`（17 项含 401/403/404/no-store/字段白名单/语义不变量）与 pytest 用例名；单快照策略见 `test_status_uses_single_window_statement`。
3. **异常与保护**（AC-07/14/16/17/34/36/40/41/46/47/49/50）：跑 `backend/tests/test_attempt_status_api.py` 与 `frontend/src/pages/student/ListeningPaperPage*.test.tsx`，逐条对照矩阵“证据”列。
4. **布局**（AC-26）：看 `e2e-07-1280.png`、`e2e-08-1024.png`，也可在浏览器缩放至 1280/1024 复核提交栏不被遮挡。
5. **回归**（R-01–08）：`git status` 确认无迁移变更；pytest 全量包含 API-1/模块一/模块二既有用例。
6. **PARTIAL 裁定**（必须书面）：

| 项 | 现状 | 请裁定 |
| --- | --- | --- |
| AC-35 | pending+内容变化 true/false/失败三组合仅有单测/服务端证据 | 接受 ✓ / 补测（管理员换批后 pending 查询） |
| AC-38 | 已有“B 已保存时 A 成功冻结”“事件未处理写入前检查”；缺“后台挂起/即将关闭” | 接受 ✓ / 补双页签脚本 |
| AC-08/13/15/29/33、R-04、E2E 6/7/8/9/10/13/14/15/19/20 | 见矩阵 | 接受或安排补测 |
| UX-01 | 原型评审通过、签字留痕未回填 | 按流程补签 |
| P-03 | 保留期未确认；自动重试关闭 | 确认后仅改 `KEY_RETENTION_POLICY` 常量 |

## 7. 证据位置

```text
docs/acceptance/attempt-system/
├─ handoff.md                 # 本文
├─ acceptance-matrix.md       # AC-01–50 / B-01–16 / R-01–08 / E2E 1–20
├─ report.md                  # 任务卡回填与未提交差异
├─ README.md                  # 复现指南
├─ e2e-api-results.json       # 真实 API 23 项
├─ evidence/                  # pytest / ruff / npm test / typecheck / build 原始输出
└─ screenshots/               # 浏览器 E2E 截图 + e2e-results.json（11 项）
```

## 8. 未覆盖与建议下一步

| 项 | 原因 | 后续 |
| --- | --- | --- |
| 核心 PARTIAL（AC-35/38） | 缺两真实组合 | 验收负责人接受或补测；补齐后重判整轮 |
| 401/E04/真实 500/空卷/换批 | 需专用环境或故障注入 | 按矩阵补跑 |
| P-03 保留期 | 未确认 | 确认后仅改常量并补自动重试 E2E |
| UX-01 签字 | 用户指示暂不处理 | 按项目流程补签 |
| 全仓 ruff 178 | 基线历史问题 | 另立技术债（本次零新增） |

## 9. 验收结论模板（请验收人填写）

```text
验收日期：
验收人：
代码基线（main@846270b）/ 实际复核提交：
是否接受“无新增迁移、API-1 保持基线”：
自动化门禁：pytest __ / npm test __ / typecheck __ / build __
真实 E2E：__/11；真实 API E2E：__/23
AC-01–AC-50：通过 / 有条件通过 / 不通过
B-01–B-16：
R-01–R-08：
PARTIAL 裁定（AC-35/38/08/13/15/29/33、R-04、E2E 项）：
UX-01 签字：
P-03 保留期结论：
AC-25 正式关闭日期与责任人：
整轮结论：通过 / 有条件通过 / 不通过
重判责任人与日期：
```
