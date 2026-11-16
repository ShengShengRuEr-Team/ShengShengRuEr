# 模块三单页工作台

上传原卷 PDF、答案解析 PDF 和听力音频，在同一页查看处理进度、核听对齐、校正来源、生成技能与证据标注及查看结果。界面沿用项目蓝白配色。此目录是独立适配器，复用原后端和 Worker；原有后端接口、三套依赖锁、迁移和模型版本不变。

## 启动

先按 [模块三运行与测试指南](../../docs/development/module-3/testing-guide.md) 准备 Windows x64、三套 Python 3.13.16 环境、PostgreSQL、模型和 `backend/.env`。`M3_ASR_PYTHON`、`M3_OCR_PYTHON` 等配置仍按原指南填写，不新增依赖。然后在仓库根目录执行：

```powershell
.\tools\module3-console-20261110\start.ps1
```

打开 <http://127.0.0.1:8002/>，本实例接口文档位于 `/docs`。首次启动创建独立库并运行原增量迁移与开发种子账号：`admin/admin123`。仅监听本机；启动失败查看此目录 `server.stderr.log`。停止整个服务使用同目录 `stop.ps1`；停止某次处理请使用网页按钮。

也可从 `backend` 前台启动，便于查看启动错误：

```powershell
.\.venv-api\Scripts\python.exe ..\tools\module3-console-20261110\server.py
```

| 环境变量 | 默认值 / 用途 |
| --- | --- |
| `M3_CONSOLE_DATABASE` | `m3_console_local`，只允许 `m3_console_` 前缀；连接地址/凭据从环境 `DATABASE_URL` 或 `backend/.env` 读取 |
| `M3_CONSOLE_DATA_DIR` | 本目录 `data`，包含材料、产物、工作流、受控音频及日志 |
| `M3_CONSOLE_PORT` | `8002`；启停脚本需使用相同值 |
| `M3_CONSOLE_BACKEND_DIR` | 自动定位同仓库 `backend`；通常不用设置 |
| `M3_CONSOLE_EXAMPLES_DIR` | 可选的本地历史验收目录；未配置时隐藏历史示例 |
| `M3_CONSOLE_WORKER` / `M3_CONSOLE_MONITOR` | 默认 `1`；隔离验证时置 `0`，关闭自动处理及入库后检查 |

数据库账号须能创建独立库，首次启动会升级指定库，不重建 public schema。不在此目录放置真实凭据。材料、数据库、模型、运行结果和日志均不进 Git。另一台机器不会获得本机已有任务；交接资料需另行受控传递。

## 流程与停止点

1. 上传三份材料，选择文本卷或扫描卷，可指定解析中听力页码。
2. 自动提取原文并对齐音频。核听后明确确认，再继续组装；异常可调整搜索范围，或合并相邻、同篇章、同一明确说话人的正文，保留来源文字及不可变修订记录。局部重对齐复用已核验产物，不重跑整套 OCR。
3. 组装保留全部原题号。缺字段用 `null` 并列为待补，答案不明确或冲突时不猜造。支持跨页解析及“解析”被 OCR 拆成“析”。可以先生成标注草稿再补缺口。
4. 明确确认付费调用后，仅生成前五题技能、标注理由和答案证据，完成即停在**五题待复核**。不会自动开始整套标注；只有提交实际逐题复核后才继续。来源不完整题跳过，单题候选或传输失败记入清单后继续，预算耗尽则停止后续请求。
5. 整套标注、正式入库、设为当前批次、学生可见均保留原有明确门控。未补齐来源/标注不得正式入库；生成结果可返回题目草稿补全，历史版本保留。

每步显示实际检查点、已完成页/题数、阶段耗时；没有可信比例时使用动态条。网页“停止本次处理”终止本工作台拥有的处理进程树并撤销租约，保留源文件与已有产物；停止后填写原因才能重试，已发送的模型请求仍可能计费。

`server.py` 提供管理适配接口；`console_worker.py` 在普通任务中调用原 Worker，修订和草稿模式分别由 `alignment_revision.py`、`draft_generation.py` 扩展。实现哈希随任务冻结；升级适配器后不要直接恢复旧实现的未完成任务，应明确建立重试任务。

## 验证

在仓库根目录运行：

```powershell
.\backend\.venv-api\Scripts\python.exe tools\module3-console-20261110\verify_checkout.py
.\backend\.venv-api\Scripts\python.exe -m ruff check tools/module3-console-20261110
```

验证器只创建并删除自己生成的随机隔离库及临时媒体目录，使用合成材料和模型响应，不调用付费服务，不重置业务库。覆盖登录/权限、上传哈希与路径、停止与继续阻断、单题失败后续生成、五题范围、复核门控、缺口阻断入库。可使用同一套 API 哈希锁在 CI 中运行。浏览器与真实材料历史验证范围见 [交付记录](../../docs/acceptance/module-3/console-20261110.md)。
