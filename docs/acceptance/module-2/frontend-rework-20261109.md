# 模块二前端 · 验收整改说明

- 日期：2026-11-09
- 依据：《验收报告_模块二前端_F01-F18_20261109》——16 PASS / 1 PARTIAL（F07）/ 1 FAIL（F14），另有 3 项环境与交付缺口
- 整改范围：仅前端代码与文档；**未改后端、未改数据库结构、未新增依赖**
- 整改提交：`630371e`（分支 `feature/m2-frontend-listening-papers`，已推送；修复前为 `247328a`）

## 一、逐项处理

| # | 报告问题 | 处理 | 证据 |
| --- | --- | --- | --- |
| 1 | **[高] 新导入试卷无法确认开放（F07 PARTIAL）** | 确认按钮不再以检查结论禁用，只在「无当前批次」「已开放」时禁用；并新增页头提示与文案，说明确认会先执行检查 | `ListeningPaperDetailPage.tsx` 的 `confirmDisabledReason` 去掉 `!checkPassed`；新增 `showCheckOnConfirmHint` 与 `Alert`；需求文档升 V0.4（§4.2、§4.3、D11、F07） |
| 2 | **[中] README 未同步、验收基线缺失（F14 FAIL）** | 全量重写 README；把需求 V0.4、原型 HTML、实现记录、交接说明、验收报告、截图（现 18 张）纳入仓库，并更新三处文档索引 | `frontend/README.md`；`docs/requirements/module-2/frontend-requirements.md`、`frontend-prototype.html`；`docs/acceptance/module-2/` 下 4 份文档与 `screenshots/` |
| 3 | **[中] 后端环境未达 V1.2 基线** | 不属前端改动，登记为环境待办（见第四节）。补充：开发者本机 venv 为 Python 3.14.10，同样不是 3.13.16，两侧都需按锁文件重建 | 本机 `python -V` = 3.14.10 |
| 4 | **[中] 开发库为空、样例不可复现** | 交接文档已补「无数据时先迁移→seed→导入」；样例仍按仓库规范不入库，改为给出受控资料包位置与复现命令 | `docs/acceptance/module-2/frontend-handoff.md` §二；本文第二节 |
| 5 | **[低] 路由注释仍写"模块一"** | 已改为「路由表：模块一页面框架 + 模块二题库业务页面」 | `frontend/src/router/index.tsx:37` |
| 6 | **[中] 尚未检查抽屉仍写"本页没有执行检查的能力"（复验新增）** | 空态文案改为「尚未检查。点击「确认开放」会先执行一次检查，通过则开放，未通过会在此列出问题。」，与页头提示一致 | `ListeningPaperDetailPage.tsx` 抽屉 `Empty`；`shot_f06_none.png` 已按整改后构建重生成（2026-11-10） |
| 7 | **[中] 首验报告 19 张截图断链、数量写错（复验新增）** | 首验截图在验收人受控目录、未入库，无法代为复制；已在报告顶部加"整理说明"，新增 `screenshots/README.md`；本目录更正为 18 张，补入 `shot_404.png` 与 `20_f07_unchecked_can_confirm.png` | `screenshots/README.md` |

### 1 的详细说明（为什么这样改）

后端的检查记录只有 `POST /visibility`（confirm）会生成；导入工具不写检查记录。前端原先在「尚未检查 / 检查未通过」时禁用确认，导致：

- 新导入的试卷永远无法产生第一条通过记录 → 无法开放；
- 数据修正后，旧的失败记录也会把按钮永久卡死。

改为「确认即触发检查」：通过则开放并落一条通过记录，未通过则后端返回 400、前端重读检查记录并展示问题。判定权在后端，前端只负责提示，避免再出现不可达状态。

### 2 的详细说明（为什么之前判 FAIL）

需求文档、原型、截图此前只放在课题组工作目录（`模块二/前端/`），没有进入仓库，验收人只能以交接表为准。本次已全部纳入 `docs/`，README 也补齐了 4 条新路由、目录结构、`npm ci` 与一期边界。

## 二、样例数据怎么复现（报告问题 4）

样例原卷、答案解析、音频与导入 payload **不进入仓库**（版权与体量，见 `docs/development/development-guide.md` §11）。复现方式：

1. 从受控资料包取得 `import_payload.json` 与 `CET4_2025_06_1_听力` 音频；
2. 按 `docs/development/module-2/delivery.md` 执行 `alembic upgrade head` → `app.seed` → `python -m app.import_module2 --input <payload> --audio-file <音频>`；
3. 预期结果：`exam_papers=1`、25 题、8 篇章、165 片段、音频 1416046ms（23:36）。

若受控包不可用，验收报告中「真实导入工具生成的 3 套合成卷」仍是有效的过程证据，但 F04/F10/F15/F16 的**规模结论**需在有样例的环境补一次。

## 三、复验建议（重点验 F07，约 15 分钟）

1. `git fetch && git switch feature/m2-frontend-listening-papers && git pull`
2. `npm ci && npm run build`
3. 导入一套**全新**试卷（不带任何检查记录）→ 打开管理端详情
   - 期望：检查显示「尚未检查」，**确认开放可点击**，页头出现"确认会先重新执行检查"的提示
4. 点「确认开放」→ 确认弹窗 → 提交
   - 合规数据：成功后为「检查通过 / 已确认开放 / 当前可访问」
   - 缺题或映射异常：返回 400，弹出具体问题；抽屉同时出现新的失败记录，「确认开放」仍可再点（修数据后可重试）
5. 学生端刷新列表：应能看到该卷
6. 回归：已开放的卷，确认按钮仍禁用；无当前批次的卷，两个按钮都禁用

## 四、真实环境复验（针对复验报告问题 1）

复验机缺 `.env`、`psycopg`、PostgreSQL 与 venv，导致 34 项 pytest 全部 setup error、F07 真实链路与 F13 无法验证。操作步骤已写入 [真实环境复验手册](frontend-e2e-runbook.md)：建 3.13 venv → 装 requirements → `.env` → `alembic upgrade head` → `app.seed` → `pytest` 34 passed → 导入样例 → 两条 E2E（新卷确认、取消后 404）。

## 五、遗留事项（不属前端代码，需对应负责人）

| 事项 | 说明 | 建议责任人 |
| --- | --- | --- |
| 后端环境重建 | 两侧都不达标：验收机 Python 3.12.10 / Starlette 1.10.0，开发机 Python 3.14.10。需统一按锁文件重建 3.13.16 / Starlette 1.7.0，再重跑 `pytest` 与导入 | 后端/环境负责人 |
| 本地库迁移 | 本次复验发现开发库缺 `0004_expected_count_source` 迁移（`exam_papers.expected_count_source` 不存在导致 companion 500）；已执行 `alembic upgrade head` 修复。接手环境请先确认迁移到 head | 环境使用人 |
| 真实样例规模复验 | 在有 25 题样例的环境补 F04/F10/F15/F16 | 验收人 + 资料持有人 |
| PR | 复验通过后再创建，目标 `develop`，merge commit | 开发者 |

## 六、PR

[PR #12](https://github.com/ShengShengRuEr-Team/ShengShengRuEr/pull/12)：base `develop`，非 Draft；合并前置条件为真实环境 E2E 两条链路通过。

## 七、变更清单

- `frontend/src/pages/admin/ListeningPaperDetailPage.tsx`：确认按钮规则、提示语与文案
- `frontend/src/router/index.tsx`：注释
- `frontend/README.md`：全量重写
- `docs/requirements/module-2/frontend-requirements.md`（新增，V0.4）
- `docs/requirements/module-2/frontend-prototype.html`（新增）
- `docs/acceptance/module-2/frontend-implementation.md`、`frontend-handoff.md`、`frontend-acceptance-20261109.md`（新增）
- `docs/acceptance/module-2/screenshots/*.png`（16 张）
- `docs/README.md`、`docs/requirements/README.md`、`docs/acceptance/README.md`：索引
