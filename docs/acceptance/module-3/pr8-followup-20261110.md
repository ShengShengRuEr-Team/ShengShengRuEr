# PR #8 验收报告后续开发与技术复验（2026-11-10）

本次依据《PR8 独立代码验收报告》继续开发，工作区为 `feature/7-module3-auto-processing`，起点为报告指定提交 `f9cf127a2da37cd456c5b8d05d245e906f991234`。此次为开发侧实际执行的技术复验，不冒充接收方独立验收；用户提供的报告原文及其历史判定未改写。

## 修改与发现

实际运行空库迁移时发现：`0005_module3_processing` 的 downgrade 在移除 `passages.genre_id → classification_dicts.id` 外键之前删除 `classification_dicts`，PostgreSQL 报 `DependentObjectsStillExist`。即使无业务数据也无法正常回退。已将该外键删除移到 downgrade 开头，不使用 CASCADE，不变更升级路径、revision ID 或业务数据。

新增 `backend/scripts/verify_module3.py`，自动新建随机命名的迁移库与测试库，隔离媒体和阶段目录，运行迁移、旧数据保留检查、真实 TCP 权限检查、空队列独立 Worker、pytest、Ruff 和 diff 检查。退出时只删除本次成功创建的数据库，保留日志。源码/锁文件哈希、依赖版本、提交及工作区状态、执行时间、退出码、JUnit 和证据哈希可回查。

新增 `module3_legacy_fixture.py`，仅允许在指定前缀的新建迁移库、`0004` revision 下准备合成模块二账号、音频、试卷、批次、正文、问题、选项、原卷映射与检查记录。逐表比对 15 张模块一/二旧表原有列的行数及内容哈希，分别验证升级至 head、回退至 `0004` 后数据保留；不把新加列混入旧数据比较。

新增 `run_module3_unittests.py`，在 ASR/OCR 各自环境中补跑 CPU 用例；出现跳过、零用例、失败或不符合 Python 3.13.16 x64 常规 GIL 要求均返回非零。已用缺少 torch 的 API 环境反向验证：unittest 虽输出 `OK (skipped=7)`，该入口仍返回 1 并将 JSON 标为 FAIL。

新增根目录 `AGENTS.md` 和 `.github/workflows/module3.yml`，同步[测试指南](../../development/module-3/testing-guide.md#7-pr-8-后续技术复验与-ci)。自动 CI 覆盖 Windows API 与 PostgreSQL 18.6 迁移；手动可补跑完整冻结 ASR/OCR 环境。PostgreSQL 下载包使用供应商 SHA-256 校验，保留原有版本与三套依赖锁文件。本次未更换模型、未新增付费调用。

## 本机运行结果

环境：Windows x64、三套 Python 3.13.16、PostgreSQL 18.6。使用本机已有隔离环境，本次未重新安装三套锁文件，不能据此宣称完成接收方干净环境重建。

| 检查 | 本次结果 | 范围 |
| --- | --- | --- |
| API 诊断 | PASS | Python/GIL 与诊断中规定的核心包 |
| 空库 upgrade head / downgrade base | PASS | 修复前失败日志与修复后成功日志均保留 |
| 模块二 0004 → head → 0004 → head | PASS | 合成题目/音频等旧列数据哈希保持一致 |
| 真实 TCP 权限 | PASS | 匿名 401、学生 403、管理员 200；登录令牌不写证据 |
| 独立 Worker 进程 | PASS | 空队列 `--once` 启动退出；不代表真实推理 |
| API 环境 pytest | 159 通过，14 跳过 | 173 个收集用例；跳过项为处理环境专用用例 |
| ASR 环境 unittest | 10 通过，0 跳过 | CTC 边界与原文定位，CPU 合成帧 |
| OCR 环境 unittest | 7 通过，0 跳过 | 印刷间距、题号及规则线处理，合成图片 |
| Ruff / git diff --check | PASS | 按测试指南的模块三路径，加三个新验收脚本 |
| CI 工作流本地校验 | PASS | actionlint 1.7.12、YAML 解析及六段 PowerShell 语法检查；未执行远端 Actions |
| 临时数据库清理 | PASS | 业务库未作为迁移或 pytest 目标 |

去除三个 API/ASR 重叠用例，共 173 个不同用例通过。这个数字来自本次日志，不是沿用历史开发声明。

完整技术复验命令（在 `backend/`）：

```powershell
.\.venv-api\Scripts\python.exe -m scripts.verify_module3 --suite all --output var/verification/pr8-followup-20261110-final
```

## 证据与判定边界

本机证据目录均相对于 `backend/`，受 `.gitignore` 保护，原始材料与日志不进入 Git：

- `var/verification/pr8-followup-20261110/`：首次失败，包括外键依赖导致的回退异常。
- `var/verification/pr8-followup-20261110-r2/`：修复后的完整技术复跑，`summary.json` 为 `PASS_TECHNICAL`。
- `var/verification/pr8-followup-20261110-final/`：最终复验脚本、源码身份与完整结果。
- `var/verification/skip-guard-20261110.json`：缺少 torch 时拒绝跳过通过的反向证据。

| 原报告发现项 | 后续状态 |
| --- | --- |
| F-01 未运行测试/迁移/服务 | 已补本机技术运行证据并修复实际迁移缺陷；真实推理链路、干净环境重建及接收方独立复验仍待执行 |
| F-02 无 CI | 工作流已落地并本地检查；远端 Actions 状态以 PR 对应提交的实际 Check Run 为准，工作流文件存在不等于 CI 已通过 |
| F-03 无 AGENTS.md | 已补入项目开发约定，不追溯改变原报告事实 |
| F-04 真实材料/人工核听/语义质量 | 保持未验证；本轮合成技术回归不替代逐题人工核对、≤300ms 实测与整套核听 |

开发侧技术回归通过。模块三全线验收维持待补证据，不能把此记录解释为需求 V2.3 的全线 PASS。本记录形成于本机复验阶段，后续提交、推送与 CI 结果以 PR #8 实际状态为准；未合并或部署。
