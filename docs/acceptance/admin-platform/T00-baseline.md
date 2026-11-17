# T00 基线/归档 · 证据记录

| 字段 | 值 |
| --- | --- |
| ac_id | T00（基线卡，无独立 AC；为 AC-28/AC-35/AC-36 及后续全部工作包的证据前置） |
| requirement_ids | ADM-MON01、ADM-LOG01、ADM-LOG02、ADM-PERM01（本轮直接相关），其余 ADM-* 为本期总范围 |
| executor | 开发实施人（lead agent） |
| executed_at | 2026-11-17 11:35—11:50（Asia/Shanghai） |
| commit_sha | `3609186a9a98787bfe4bbc9943b7162896a2d80f`（`develop`），本轮新建 `feature/admin-platform` 未提交任何代码 |
| workspace_state | 开工时 `git status --short` 为空；随后仅新增 `docs/**` 文档与归档件（未提交） |
| environment | Windows 10/11 本地；Python 3.13.16（`backend/.venv`）；Node 24.14.0；npm 11.9.0；PostgreSQL 本地 `127.0.0.1:5432`；临时目录 `D:\pytemp` |
| migration_heads | `0005_attempt_system (head)`；单链 0001→0002→0003→0004→0005 |
| dependency_versions | 见 `docs/development/admin-platform/implementation-notes.md` §5；本轮不新增、不升级 |
| config_summary | `APP_ENV=development`；开发库 `shengshengruer`（只读）；测试库 `shengshengruer_test`（由 `tests/conftest.py` 自动建库并 `upgrade head`） |
| result | **PASS**（附 1 项偏离说明：Issue 未创建） |

## 1 执行步骤、预期与实际

| # | 步骤（真实命令） | 预期 | 实际 |
| --- | --- | --- | --- |
| 1 | `git status --short` | 空 | 空 |
| 2 | `git log --oneline -3` | 末次为 PR16 合并 | `3609186` / `8eb795b` / `e67d616` |
| 3 | `git switch -c feature/admin-platform` | 新建分支成功 | `Switched to a new branch 'feature/admin-platform'` |
| 4 | `python -m alembic heads` | 单一 head | `0005_attempt_system (head)` |
| 5 | `python -m alembic current` | 记录开发库版本，不迁移 | `0004_expected_count_source`（落后 head 一个版本） |
| 6 | 只读查询开发库 | 新表不存在 | `auth_sessions=None`、`admin_login_events=None`，public 表 16 张 |
| 7 | `python -m alembic history` | 线性链 | 0001→0005 线性，无分叉 |
| 8 | `python -m pytest -o addopts= -q -p no:warnings` | 全绿 | **265 passed in 33.15s** |
| 9 | `npm ci` → `npm test -- --run` | 全绿 | `added 248 packages`；**18 files / 129 tests passed** |
| 10 | `Get-FileHash requirements.md -Algorithm SHA256` | `728105bd…8cc74` | 一致；归档副本同哈希 |
| 11 | 分发文档哈希 | 记录全部输入文档 | 见 `evidence/T00-docs-sha256.txt` |

## 2 关键事实与偏差

1. **开发库与 head 差异（只读，不迁移）**：开发库停在 `0004_expected_count_source`，head 为 `0005_attempt_system`。这是 PR16 合入后未执行迁移的既有事实，不是本轮引入。本轮所有迁移与测试只在独立测试库执行，开发库不改动。
2. **前端依赖不完整**：首次 `npm test` 报 `vitest` 不存在（`node_modules` 缺 devDependencies）。执行 `npm ci` 后恢复正常；`node_modules` 已被 `.gitignore` 忽略，工作区保持干净。这是环境修复，不是代码改动。
3. **Issue 未创建**：本机无 `gh` 命令（`gh not found`），无法在本轮创建 GitHub Issue。按用户备选方案，分支名固定 `feature/admin-platform`，后续 PR 正文以 `Refs: 基础管理端阶段一（T00–T02）` 说明关联；若你提供 Issue 编号，我把分支/PR 引用改为该编号。
4. **缺失文档登记**：`D:\guochuangxiangmu\docs\requirements\admin-platform\` 下不存在《第三轮复验意见》，`D:\guochuangxiangmu\docs\development\admin-platform\` 下不存在《参考开发文档借鉴评估》。本轮以主文档为唯一依据，未引用、未编造其内容。
5. **文档口径冲突**：`tasks.md`/`api.md` 为旧一期口径（11 个 `user:*` 权限码），与主文档 21 个 `admin:*` 权限码冲突，已按主文档执行，详见 `implementation-notes.md` §2。

## 3 T00 交付物

| 交付物 | 路径 |
| --- | --- |
| 需求归档（与来源同哈希） | `docs/requirements/admin-platform/requirements.md` |
| DD 收口记录 | `docs/development/admin-platform/dd-record.md` |
| 实施说明（基线/迁移计划/文件清单/依赖固定/探针计划） | `docs/development/admin-platform/implementation-notes.md` |
| 证据原始输出 | `docs/acceptance/admin-platform/evidence/T00-*.txt`（git、alembic、env、devdb、docs-sha256、backend-pytest、frontend-test） |

## 4 未覆盖项

- 未执行开发库迁移、未对生产做任何操作。
- 未创建 Issue、未提交、未 push、未建 PR。
- 双实例/真实代理/TLS 等运行验证属 T08/T09，本轮不做。

## 5 结论

**PASS**。基线、归档、DD 收口、迁移计划与文件清单、依赖固定、探针契约登记均已完成；Issue 创建因环境缺少 `gh` 未执行，已按用户备选方案登记。
