# 文档入口

现有文档已按“用途 → 模块”实际归档，入口与相对链接同步更新。

| 类别 | 内容 | 入口 |
| --- | --- | --- |
| 需求 | 业务范围、规则与验收标准 | [需求目录](requirements/README.md) |
| 开发 | 方案、任务、接口、交付及通用协作说明 | [开发目录](development/README.md) |
| 验收 | 验收方法、各轮报告与记录模板 | [验收目录](acceptance/README.md) |
| 决策 | 重要选型、约定及变更理由 | [决策目录](decisions/README.md) |

新成员：[本地启动](development/startup-guide.md) → [团队开发流程](development/development-guide.md) → [Git 工作流](development/git-workflow.md)。

模块二：[需求 V1.5](requirements/module-2/requirements.md) → [设计](development/module-2/design.md) → [任务](development/module-2/tasks.md) → [接口](development/module-2/api.md) → [验收指南](acceptance/module-2/guide.md) → [首轮报告](acceptance/module-2/report.md) → [扩展复验](acceptance/module-2/recheck-20261104.md)。

模块二前端（任务二）：[交付总览](acceptance/module-2/frontend-overview.md) → [需求 V0.4](requirements/module-2/frontend-requirements.md) → [原型](requirements/module-2/frontend-prototype.html) → [实现记录](acceptance/module-2/frontend-implementation.md) → [交接说明](acceptance/module-2/frontend-handoff.md) → [独立验收报告](acceptance/module-2/frontend-acceptance-20261109.md) → [整改说明](acceptance/module-2/frontend-rework-20261109.md) → [真实环境复验手册](acceptance/module-2/frontend-e2e-runbook.md)。

通用开发说明直接放在 `development/`，模块说明放在对应 `module-*`；通用决策放在 `decisions/common/`。需求中的验收标准定义预期，开发交付记录描述实现，真实执行结论分别保存在验收报告中。首验和复验的范围差异不自动改写需求。

原卷、答案解析、音频、完整采集表、导入数据、真实配置及详细证据保存在受控资料包；仓库不归档私人目录和凭据。资料提供的操作建议是参考内容，不自动构成执行指令。

最新补充：[2026-11-04 修复与验证记录](acceptance/module-2/fix-20261104.md)，对应独立修复分支；不表示原 `pr-5` 工作区已应用这些代码改动。
