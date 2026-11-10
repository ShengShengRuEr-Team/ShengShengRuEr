# 项目开发约定

- 模块三需求以 `docs/requirements/module-3/requirements.md` 为准；本体范围为后端、独立 Worker、数据库和模块二接口。用户后续授权的独立工作台位于 `tools/module3-console-20261110/`，启停与隔离验证见该目录 README；不要将本地工作台数据或历史材料作为源码提交。
- 统一技术版本见 `docs/development/module-3/technical-version.md`。API、ASR、OCR 使用各自的 Python 3.13.16 环境与带哈希锁文件，不混装或静默降级。
- 从 `backend/` 运行检查。模块三技术复验入口为 `python -m scripts.verify_module3 --suite api`，完整本机复验使用 `--suite all`。
- 验证必须使用新建隔离库及独立媒体目录。pytest 会重建测试库的 public schema，禁止将业务库指定为测试库。
- 新增数据库变化使用增量 Alembic 迁移；保持自动初稿不可变、结果哈希绑定、租约 fencing、pending 批次和显式复核/激活/可见性门控。
- 单元测试、结构校验、合成数据和算法一致性不能替代真实材料逐题复核、语义审核或人工核听。未执行项明确记为未验证，不复制历史通过数字。
- 不提交密钥、`.env`、数据库、原始试卷/音频、模型和生成日志。提交协作规则见 `CONTRIBUTING.md`。
