# ShengShengRuEr 团队开发流程

适用对象：项目负责人、前端、后端、AI 开发及参与审核的成员。

项目仓库：<https://github.com/ShengShengRuEr-Team/ShengShengRuEr>

团队采用 Git Flow，日常开发从 `develop` 创建任务分支，完成后通过 PR 合回 `develop`；准备正式版本时走发布分支。普通开发者不直接修改受保护分支，合并由组织管理员执行。

## 1. 第一次加入项目

1. 准备自己的 GitHub 账号，接受仓库邀请。正式参与开发需要仓库 **Write** 权限。
2. 安装 Git 和熟悉的编辑器。前后端运行环境按各模块后续选定的技术栈安装。
3. 负责人告知本次任务、所属模块、关联 Issue 和验收条件，再开始写代码。

组织成员身份和仓库开发权限是两件事。Outside Collaborator（外部协作者）只要有 Write 权限，也可以正常开发；不需要共用负责人的账号或密钥。

### 配置提交身份

先查看当前身份：

```bash
git config --global --get user.name
git config --global --get user.email
```

如需配置，替换下面的示例内容后执行：

```bash
git config --global user.name "你的姓名或常用昵称"
git config --global user.email "你的 GitHub 已验证邮箱或 noreply 邮箱"
```

仓库目前是公开仓库，提交身份也会出现在历史中。希望隐藏真实邮箱时，在 GitHub 个人 Settings → Emails 中取得自己的 noreply 邮箱。上述设置用于提交署名，不负责登录 GitHub。

### 下载项目

在准备存放项目的本地目录打开终端，执行一次：

```bash
git clone --branch develop https://github.com/ShengShengRuEr-Team/ShengShengRuEr.git
cd ShengShengRuEr
git status
```

已下载过的人继续使用原目录，不要反复克隆出多个副本。若以前使用个人账号下的旧地址，在已有项目目录更新远端地址：

```bash
git remote set-url origin https://github.com/ShengShengRuEr-Team/ShengShengRuEr.git
git fetch origin
```

如果提示远端没有 `develop`，先请负责人完成首次分支发布。如果 `develop` 里仍只有旧 README，说明初始化 PR 尚未合并；先阅读初始化任务分支中的文档，待审核合并后再开展普通开发。

## 2. 代码和文档放在哪里

| 内容 | 目录 | 常见协作要求 |
| --- | --- | --- |
| 页面、播放器、浏览器端交互 | `frontend/` | 页面变化附截图，先确认 API |
| 鉴权、业务接口、数据库迁移 | `backend/` | 接口和数据库变化同步文档 |
| 推荐、错因分析、提示词与评测 | `ai/` | 说明模型配置、样例来源和验证依据 |
| 产品需求与验收条件 | `docs/requirements/` | 区分调研建议与已确认需求 |
| API 契约 | `docs/api/` | 前后端共同确认后实现 |
| 重要技术选型 | `docs/decisions/` | 记录决定、理由和影响 |
| 部署配置与操作说明 | `deploy/` | 不保存真实凭据 |
| 重复使用的辅助脚本 | `scripts/` | 说明参数、依赖和运行影响 |

当前只初始化了目录和规范，尚无可运行应用、应用测试和部署流程。不要假定 React、Vue、FastAPI 等框架已经确定。选型后，各模块 README 必须补齐实际安装、启动、构建和测试命令。

## 3. 先认清几个分支

| 分支 | 做什么 | 从哪里创建 | PR 合到哪里 |
| --- | --- | --- | --- |
| `main` | 正式发布主线 | 首次建库 | 不直接开发 |
| `develop` | 下一版本的功能集成 | `main` | 经发布流程进入 `main` |
| `feature/23-listening-player` | 新功能 | `develop` | `develop` |
| `fix/41-audio-retry` | 开发或验收问题修复 | 问题所在的 `develop` 或 `release/*` | 对应来源分支 |
| `docs/12-api-contract` | 文档任务 | `develop` | `develop` |
| `chore/15-update-config` | 工程配置与维护 | `develop` | `develop` |
| `release/0.1.0` | 版本冻结与验收 | `develop` | `main`，并回合 `develop` |
| `hotfix/0.1.1-audio-playback` | 线上紧急修复 | 实际线上版本的提交或标签 | `main`，并同步开发和当前发布分支 |

任务编号替换成真实 Issue 编号；分支名使用小写英文和短横线。不要按成员姓名建长期分支，也不要把未完成的功能合入 `develop`。

## 4. 每次开始新任务

先确认当前目录没有未处理修改，再同步 `develop`、创建任务分支：

```bash
git status
git switch develop
git pull --ff-only origin develop
git switch -c feature/23-listening-player
```

上面的 `23` 是示例。文档任务改用 `docs/编号-说明`，维护任务改用 `chore/编号-说明`。

如果当前有未提交修改，先留在原任务分支妥善保存，不要用强制切换或重置丢弃修改。

一个分支聚焦一个任务。多个成员同时改接口、数据库表或题目标签时，先在文档或 Issue 中约定，不要各自实现不同结构。

## 5. 开发、自测、提交

开发时遵守 [命名规范](naming-conventions.md)。完成一段清晰的修改后，先查看本次内容：

```bash
git status
git diff
```

运行所属模块的实际检查。涉及页面时检查交互与异常状态，涉及接口时检查请求、权限与失败分支；不要只验证正常路径。

以修改前端为例，按范围添加并检查待提交内容：

```bash
git add frontend/
git diff --cached
git diff --cached --check
git commit -m "feat(frontend): 支持听力逐句播放"
```

同时修改了接口或其他文件时，显式添加相关文件或目录，再检查待提交内容。不要不看文件列表就把所有本地资料一起提交。

提交标题使用 `type(scope): 说明`，例如：

```text
feat(frontend): 支持听力逐句播放
fix(backend): 修复重复保存作答记录的问题
docs(repo): 补充接口约定
chore(repo): 更新工程配置
```

提交到本地、推送到 GitHub、发起 PR、合并 PR 是四个不同动作；本地提交后，GitHub 不会自动出现新代码。

## 6. 推送任务分支并发起 PR

第一次推送当前示例分支：

```bash
git push -u origin feature/23-listening-player
```

后续同一分支有新提交时，执行 `git push` 即可。GitHub 如果要求登录，使用自己的账号完成 Git 的授权流程；不要把账号密码或访问令牌写进代码、文档或仓库地址。

在仓库页面进入 **Pull requests → New pull request**，检查：

- **base：`develop`**，这是本次要合入的目标。
- **compare：自己的任务分支**，例如 `feature/23-listening-player`。
- 验收修复的 base 应选对应 `release/*`，不是一律选择 `develop`。

PR 标题按提交标题格式命名，正文至少说明：

1. 改了什么、为什么改。
2. 关联哪个 Issue，例如 `Closes #23`；如果上线后才关闭任务，使用 `Refs #23`。
3. 实际如何验证、结果是什么；页面变化附截图。
4. 是否影响接口、数据库、环境配置、提示词、模型或部署。

模板在 [.github/PULL_REQUEST_TEMPLATE.md](../.github/PULL_REQUEST_TEMPLATE.md)。若 GitHub 尚未自动带出模板，可以手动复制内容；模板通常需要进入默认分支后才会被自动使用。尚未完成的工作使用 **Draft PR**，不要提前请求合并。

## 7. 审核、修改和合并

| 人员 | 负责什么 |
| --- | --- |
| PR 作者 | 自测、解释变化、处理意见和冲突 |
| 审核者 | 阅读实际改动，提出问题或点击 Approve |
| 组织管理员 | 检查目标分支和验收情况，执行合并 |

按目前约定的两条规则：

- 受保护分支必须经 PR 修改，至少一名非作者批准。
- 审核通过后再次修改代码，原批准会失效，需要重新审核。
- 讨论需要标记为已解决；「已解决」不等于获得 Approve。
- 普通 Write 成员不能合并到 `main`、`develop`、`release/*`，由规则允许的组织管理员合并。
- 管理员自己提交的 PR，也需要另一位成员批准，不能自己批准自己。
- 合并统一选择 **Create a merge commit**，不选择 Squash 或 Rebase。

需要修改时，在原任务分支继续修改、提交和推送，原 PR 会自动更新，不需要重开一个 PR。权限由 GitHub 实际生效规则决定；如果普通成员竟然可以直接推送到 `develop` 或合并 PR，请负责人检查规则，不用靠口头约定替代设置。

## 8. 处理分支落后和冲突

同一个任务开发期间，其他人的代码可能先合入 `develop`。确认自己在原任务分支且工作区干净后，执行：

```bash
git status
git fetch origin
git merge origin/develop
```

无冲突时，重新运行相关检查，再执行 `git push`。有冲突时，Git 会列出文件：

1. 阅读双方改动，和相关负责人确认正确结果，不要机械地全部保留一边。
2. 修改冲突文件并去掉冲突标记。
3. 用 `git add` 添加已解决文件，再执行 `git commit` 完成本次合并。
4. 重新验证并推送，通知审核者重新审核。

不确定如何处理时，可以先用 `git merge --abort` 取消这一次尚未完成的合并，保留此前已提交的工作，再与负责人处理。不要用 `git push --force` 覆盖共享历史。

如果任务来自 `release/*`，这里同步对应的远端发布分支；不能把整个未发布的 `develop` 合进发布分支。

## 9. PR 合并以后

确认 GitHub 显示 **Merged**，再更新本地开发分支：

```bash
git switch develop
git pull --ff-only origin develop
git branch -d feature/23-listening-player
```

任务远端分支可由管理员在 GitHub 点击 **Delete branch** 清理；本地执行 `git fetch --prune` 更新远端分支列表。下一个任务从最新 `develop` 新建分支，不继续复用已经合并的旧分支。

## 10. 发布由负责人组织

普通成员的 PR 合入 `develop`，只表示进入开发集成，不表示已经上线。

正式版本按以下顺序：

1. 确定本版范围，从 `develop` 创建 `release/版本号`。
2. 部署验收环境；冻结新功能，只接收修复。
3. 验收通过，发布分支经 PR 合入 `main`，并回合 `develop`。
4. 在发布提交打 `v版本号` 标签，部署已验证产物并记录结果。
5. 线上有紧急故障时，从实际线上版本创建 `hotfix/*`，修复后同步所有相关分支。

仓库目前还没有自动部署；仅推送、合并或打标签都不代表服务已经部署。后续以 `deploy/` 中确认的操作说明为准。完整发布与回退约定见 [Git 工作流](git-workflow.md)。

## 11. 哪些内容不能提交

- API Key、数据库密码、访问令牌、私钥和真实 `.env`。
- 用户个人信息、录音、生产数据库、日志中的敏感内容。
- 无权公开的听力材料、整套题库、会议录音或内部报告。
- `node_modules/`、虚拟环境、构建产物、缓存和模型权重。

可以提交依赖锁文件、数据库迁移、公开配置样例和已脱敏且有权共享的小型样例。`.gitignore` 只帮助忽略未跟踪文件，不能清除已经提交过的敏感历史；如果误提交凭据，立即通知负责人并撤销或轮换凭据，不能只删除最新文件。

## 12. 一次普通任务的完成标准

- Issue 中的验收条件已满足。
- 代码和相关文档已更新，必要验证结果写入 PR。
- PR 目标正确，至少一名其他成员批准，审核意见已处理。
- 管理员已按 Merge 方式合并，GitHub 状态显示 Merged。
- 自己已同步 `develop`，旧任务分支按约定清理。

不熟悉 Git 的成员可以使用编辑器自带 Git 界面完成相同步骤，但分支来源、PR 目标、审核要求和合并权限不变。
