# ShengShengRuEr

面向大学英语四、六级学习者的英语听力个性化学习系统。

围绕「听力练习 → 错因分析 → 错题沉淀 → 个性化推荐 → 复习巩固」开展团队开发。

## 当前状态

模块一（登录与管理端、用户端框架）已完成，前后端均可运行：

| 模块 | 内容 | 技术栈 |
| --- | --- | --- |
| 后端 | 登录、退出、当前用户信息、身份区分、基础接口鉴权 | FastAPI + SQLAlchemy + Alembic + PostgreSQL |
| 前端 | 登录页、管理端 / 学生端页面框架、路由守卫 | React + TypeScript + Ant Design + Vite |

- 后端 4 个接口、4 张表，测试 11 项、端到端验收 8 项全部通过
- 前端 4 个页面，`tsc -b` 零错误，`vite build` 通过

安装、启动与测试说明见 [backend/README.md](backend/README.md) 与 [frontend/README.md](frontend/README.md)。

题库、处理任务、作答判分、错因分析与推荐等功能在后续模块中实现。

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
│   ├── api/                 API 契约
│   ├── decisions/           已确认的技术决策及理由
│   └── requirements/        需求与验收条件
├── deploy/                  开发、验收、正式环境的部署配置
├── scripts/                 可重复运行的辅助脚本
├── .editorconfig            编辑器格式约定
├── .gitattributes           换行与文件类型约定
├── .gitignore               本地配置、缓存和大文件忽略规则
├── .env.example             配置字段样例，不含真实凭据
└── CONTRIBUTING.md          开发入口与 PR 提交要求
```

## 开始参与

**新成员先阅读 [团队开发流程](docs/development-guide.md)**：包含第一次下载项目、创建分支、提交 PR、处理审核和日常同步的完整步骤。

```bash
git clone https://github.com/ShengShengRuEr-Team/ShengShengRuEr.git
cd ShengShengRuEr
git switch develop
git pull --ff-only origin develop
git switch -c feature/23-listening-player
```

上述流程适用于远端已经建立 `develop` 的情况。首次初始化的分支发布顺序见 [Git 工作流](docs/git-workflow.md#首次初始化)。

开发完成后，推送自己的任务分支并向 `develop` 发起 PR；不要直接推送到 `main` 或 `develop`。

## 团队文档

- [团队开发流程](docs/development-guide.md)：可直接分享给队友的操作指南。
- [参与开发](CONTRIBUTING.md)：任务、审查和提交要求。
- [命名规范](docs/naming-conventions.md)：目录、文件、代码、接口与环境变量的统一命名。
- [Git 工作流](docs/git-workflow.md)：分支来源、合并方向、发布和线上修复。
- [文档索引](docs/README.md)：需求、接口与技术决策入口。

## 配置与数据

后端已读取 `backend/.env`（数据库连接、JWT 密钥等），样例见 `backend/.env.example`；
前端读取 `frontend/.env` 的 `VITE_API_BASE_URL`，样例见 `frontend/.env.example`。
真实配置保存在本地或部署平台，**不提交到 Git**。

听力音频、完整题库、模型权重、用户录音和生产数据库不保存在本仓库。需要入库的样例应可公开、已脱敏且体积小；资料目录与下载的参考项目不整批导入。

## 开源许可

目前未选定开源许可证。仓库公开可访问不代表已授予任意复制、修改或商用的许可；对外复用和引入第三方材料前，先明确许可与来源。
