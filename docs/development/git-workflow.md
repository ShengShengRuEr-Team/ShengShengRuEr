# Git 工作流

## 分支约定

本项目采用 Git Flow：`main` 和 `develop` 长期保留，任务与发布准备使用临时分支。

| 分支 | 来源 | 合并目标 | 作用 |
| --- | --- | --- | --- |
| `main` | 仓库初始化 | — | 已验收的正式发布主线 |
| `develop` | `main` | 经 `release/*` 发布 | 下一版本的开发集成 |
| `feature/*` | 最新 `develop` | `develop` | 新功能 |
| `fix/*` | 有问题的 `develop` 或当前 `release/*` | 对应来源分支 | 非线上紧急问题修复 |
| `docs/*` | 最新 `develop` | `develop` | 文档更新 |
| `chore/*` | 最新 `develop` | `develop` | 工程维护、目录和配置 |
| `release/*` | 达到发布范围的 `develop` | `main` 并回合 `develop` | 发布冻结与验收 |
| `hotfix/*` | 实际线上版本对应的 `main` 提交或标签 | `main`，并同步 `develop` 与当前发布分支 | 线上紧急修复 |

任务分支合并后删除。受删除保护的发布分支可保留追溯，不能为日常清理随意绕过分支保护。每次发布同时只维护一个验收中的 `release/*`，避免小团队同时维护多条发布线。

## 首次初始化

首次建库时，从远端 `main` 创建本地 `develop`，再创建 `chore/repository-initialization`。目录和规范的变化位于该任务分支，通过 PR 进入 `develop`。

若远端尚无 `develop`，首次发布分支按以下顺序进行：

1. 管理员把本地 `develop` 推送到远端。当前两条规则未限制分支创建；若以后增加创建限制，按当时权限执行。
2. 推送 `chore/repository-initialization`，创建目标为 `develop` 的 PR。
3. 普通成员发起的 PR 由非作者审核批准，管理员执行 Merge；管理员本人发起的初始化 PR 可以使用仅限 PR 的审核例外完成合并。
4. 团队随后克隆仓库，或拉取远端分支，从最新 `develop` 开发。

```bash
git push -u origin develop
git push -u origin chore/repository-initialization
```

上述命令仅用于首次发布分支，不是日常开发步骤。推送任务分支不代表初始化改动已合并，PR 审核通过并由管理员合并后，团队才会在 `develop` 看到完整目录。不要把初始化改动直接推送进受保护的 `main` 或 `develop`。

## 日常开发

```bash
git switch develop
git pull --ff-only origin develop
git switch -c feature/23-listening-player
# 开发、自测并提交后：
git push -u origin feature/23-listening-player
```

发起目标为 `develop` 的 PR。普通成员审核，管理员合并。共享开发环境未来跟随 `develop` 自动部署，当前尚未配置部署流程。

## 发布

1. 确认当前版本全部需求已经进入 `develop`，且没有未计划发布的功能。不要将做了一半的功能合入发布范围。
2. 从选定的 `develop` 提交创建 `release/0.1.0`，冻结功能范围。
3. 部署验收环境；只接收修复和必要发布配置，新功能继续在 `develop` 开发。
4. 验收修复从发布分支创建 `fix/*`，经 PR 合回发布分支。
5. 验收完成，将发布分支通过 PR 合入 `main`，并回合 `develop`，保留验收期间的修复。
6. 在 `main` 的发布合并提交创建不可移动的版本标签 `v0.1.0`，关联发布说明。标签或管理员手动操作触发正式部署；仅合并代码不自动代表部署成功。
7. 正式部署使用与验收一致的应用产物，记录产物标识、对应源码提交、版本、迁移与配置变化，检查关键业务流程。

如果将来使用构建产物，正式发布前验证发布合并后的源码树与验收产物来源一致；若发生实质变化，重新构建和验收。部署方式由后续技术决策确定。

## 线上紧急修复

从实际线上标签创建 `hotfix/0.1.1-audio-playback`，验证后经 PR 合入 `main`，发布新标签 `v0.1.1`。不能从含有未发布功能的 `develop` 创建线上热修复。

同步修复到 `develop`。若存在当前验收中的 `release/*`，也要同步修复，防止下一版重新引入旧问题。所有同步仍经 PR 完成。

## 合并和回退

所有 PR 使用 **Create a merge commit**；不要为受保护分支启用 Require linear history，不要使用 Squash 或 Rebase merge 破坏分支之间的提交关系。

线上回退优先重新部署已验证的上一版产物；需要撤销代码时，经 PR 提交撤销变更，不能强制重置 `main`。数据库迁移需单独评估：备份、采用向后兼容变更，并明确数据恢复步骤。

## 仓库保护规则

GitHub 中设置两条 **Active** 的分支规则，均匹配 `main`、`develop`、`release/*`。`feature/*` 等任务分支不在此范围，普通开发者可推送自己的开发提交。

### pr-required

- Bypass list 添加 Organization admin，方式为 Allow for pull requests only。组织管理员可在 PR 中绕过等待批准；普通成员不获得例外权限。
- 勾选 Require a pull request before merging，Required approvals 为 `1`。
- 勾选 Dismiss stale pull request approvals when new commits are pushed。
- 勾选 Require conversation resolution before merging。
- Allowed merge methods 只保留 Merge。
- 勾选 Restrict deletions 和 Block force pushes。
- 项目接入 CI 并实际运行后，再加入对应必需检查，不能填写尚不存在的检查名。

### owner-only-merge

- 只勾选 Restrict updates。
- Bypass list 添加 Organization admin，方式为 Allow for pull requests only。
- 普通成员给予仓库 Write 权限；组织所有者属于允许合并的管理员范围。若要求仅一人合并，就不能再把其他成员提升为组织所有者。

两条规则共同生效：普通成员需要发起 PR 并接受审核，不能合并到目标分支；组织管理员必须通过 PR 更新目标分支，但可选择绕过等待批准，合并自己的 PR，不必再等待另一名成员批准。

仅限 PR 的例外不会授予直接推送、强制推送或直接删除受保护分支的权限。管理员不能批准自己的 PR，但可以按规则执行绕过合并；PR 中仍应写清修改与验证。该例外在技术上也可用于其他 PR，日常仍要求管理员先审核成员提交的改动，再确认合并。

仓库当前采用 Free 组织与公开仓库方案。公开意味着代码与历史可被外界读取；免费私有仓库无法据此强制执行规则。修改可见性或套餐时，需要重新确认规则是否执行。

初始化源文件不会自动创建 GitHub 分支保护、任务、远端分支或部署环境。请以 GitHub 实际设置和一次协作者验证结果为准。
