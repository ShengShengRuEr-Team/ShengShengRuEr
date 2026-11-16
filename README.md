# ShengShengRuEr

面向大学英语四、六级学习者的英语听力个性化学习系统。

围绕「听力练习 → 错因分析 → 错题沉淀 → 个性化推荐 → 复习巩固」开展团队开发。

## 当前状态

模块一登录与两端页面框架已实现；模块二后端题库、整卷查询、权限、可见性及受控音频已实现，正在按验收报告整改。本分支实现模块三自动处理后端及[独立单页工作台](tools/module3-console-20261110/README.md)，支持上传、进度与停止、对齐校正、五题试标及结果复核。作答判分与推荐后续实施；模块三技术验证与人工内容验收分别记录。

首次运行见 [本地启动指南](docs/development/startup-guide.md)。模块二说明见 [开发文档](docs/development/module-2/design.md) 和 [验收记录](docs/acceptance/README.md)。不同提交的测试结果分别保留，不把历史通过数字当作当前验收结论。

## 项目标识

| 场景 | 统一名称 |
| --- | --- |
| GitHub 仓库、对外项目名称 | `ShengShengRuEr` |
| 包、容器、部署资源等技术标识 | `shengshengruer`，例如 `shengshengruer-backend` |
| 日常开发集成分支 | `develop` |
| 正式发布主线 | `main` |

不要为了统一大小写改动已有 GitHub 仓库名称。

## 目录结构

```text
ShengShengRuEr/
├── .github/                 PR 和任务模板
├── frontend/                用户界面与浏览器端音频交互
├── backend/                 业务接口、鉴权与数据库迁移
├── ai/                      提示词、推荐与诊断逻辑、AI 评测材料
│   ├── prompts/             可版本管理的提示词
│   └── evals/               评测规则与可共享的小型样例
├── docs/                    需求、接口、设计决策和团队规范
│   ├── requirements/        需求与验收条件
│   ├── development/         开发方案、任务、接口与运行
│   ├── acceptance/          验收方法、报告与复验记录
│   └── decisions/           技术取舍及变更理由
├── deploy/                  开发、验收、正式环境的部署配置
├── scripts/                 可重复运行的辅助脚本
├── .editorconfig            编辑器格式约定
├── .gitattributes           换行与文件类型约定
├── .gitignore               本地配置、缓存和大文件忽略规则
├── .env.example             配置字段样例，不含真实凭据
└── CONTRIBUTING.md          开发入口与 PR 提交要求
```

## 开始参与

**新成员先阅读 [团队开发流程](docs/development/development-guide.md)**：包含第一次下载项目、创建分支、提交 PR、处理审核和日常同步的完整步骤。

```bash
git clone https://github.com/ShengShengRuEr-Team/ShengShengRuEr.git
cd ShengShengRuEr
git switch develop
git pull --ff-only origin develop
git switch -c feature/23-listening-player
```

上述流程适用于远端已经建立 `develop` 的情况。首次初始化的分支发布顺序见 [Git 工作流](docs/development/git-workflow.md#首次初始化)。

开发完成后，推送自己的任务分支并向 `develop` 发起 PR；不要直接推送到 `main` 或 `develop`。

## 团队文档

- [本地启动指南](docs/development/startup-guide.md)：Windows 首次安装、日常启动与常见问题。
- [团队开发流程](docs/development/development-guide.md)：可直接分享给队友的操作指南。
- [参与开发](CONTRIBUTING.md)：任务、审查和提交要求。
- [命名规范](docs/development/naming-conventions.md)：目录、文件、代码、接口与环境变量的统一命名。
- [Git 工作流](docs/development/git-workflow.md)：分支来源、合并方向、发布和线上修复。
- [文档索引](docs/README.md)：需求、接口与技术决策入口。

## 配置与数据

后端已读取 `backend/.env`（数据库连接、JWT 密钥等），样例见 `backend/.env.example`；
前端本地配置使用 `frontend/.env.local` 的 `VITE_API_BASE_URL`，样例见 `frontend/.env.example`。
真实配置保存在本地或部署平台，**不提交到 Git**。

听力音频、完整题库、模型权重、用户录音和生产数据库不保存在本仓库。需要入库的样例应可公开、已脱敏且体积小；资料目录与下载的参考项目不整批导入。

## 开源许可

目前未选定开源许可证。仓库公开可访问不代表已授予任意复制、修改或商用的许可；对外复用和引入第三方材料前，先明确许可与来源。
