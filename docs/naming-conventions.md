# 命名规范

## 项目与目录

项目名称沿用 `ShengShengRuEr`；技术资源标识统一使用 `shengshengruer`。模块资源名使用 `shengshengruer-frontend`、`shengshengruer-backend` 等形式。

一级目录固定为 `frontend`、`backend`、`ai`、`docs`、`deploy`、`scripts`。默认目录和普通文档使用英文小写、短横线分词，例如 `listening-player/`、`git-workflow.md`。

不要使用姓名、拼音缩写、空格或 `new`、`final-v2` 等模糊后缀给正式文件命名。草稿状态写入文档或 PR，不靠文件名堆版本。

## 文件与代码

| 对象 | 规则 | 示例 |
| --- | --- | --- |
| 普通 Markdown 文档 | `kebab-case.md` | `listening-workflow.md` |
| 前端页面、UI 组件 | `PascalCase` | `ListeningPlayer.vue`、`ListeningPlayer.tsx` |
| 前端普通模块 | `kebab-case` | `audio-player.ts` |
| JS / TS 变量与函数 | `camelCase` | `playbackRate`、`loadExercises()` |
| 类、类型、接口 | `PascalCase` | `ListeningExercise`、`RecommendationResult` |
| Python 文件、包、变量与函数（如采用 Python） | `snake_case` | `error_analysis.py`、`analyze_errors()` |
| 常量 | `UPPER_SNAKE_CASE` | `MAX_RETRY_COUNT` |
| 样式类 | `kebab-case` | `listening-player` |
| 测试文件 | 与对应模块一致，遵守测试框架惯例 | `audio-player.test.ts`、`test_error_analysis.py` |
| 标准工具文件 | 保留工具要求的固定名称 | `README.md`、`Dockerfile`、`pyproject.toml` |

`usePlayback.ts` 等框架要求或成熟社区惯例允许作为特例，选型后在模块说明中明确。同一模块保持一致，语言自身要求优先，不强制所有语言使用同一种大小写。

代码标识使用英文，中文用于说明、注释和产品文案。避免含义不明的 `data1`、`temp2`、`doStuff`。

## 业务词汇

| 含义 | 统一英文 |
| --- | --- |
| 听力练习（一组材料和题目） | `listening_exercise` |
| 单道题目 | `question` |
| 一次作答记录 | `attempt` |
| 错题记录 | `mistake` |
| 错因分析 | `error_analysis` |
| 推荐结果 | `recommendation` |
| 复习计划 | `review_schedule` |

表中用 `snake_case` 表达概念；具体代码按所在语言转换，例如前端 `listeningExercise`。不要把一组练习和单道题目都命名为 `question`。

## API 与数据字段

- API 路径以 `/api/v1` 开始，资源名用英文复数和短横线，例如 `/api/v1/listening-exercises`。
- 路径参数采用 `snake_case`，例如 `/api/v1/listening-exercises/{exercise_id}`。
- 查询参数、请求 JSON、响应 JSON 统一 `snake_case`，例如 `page_size`、`exercise_id`、`created_at`。
- 前端在请求适配层处理 JSON 字段与代码变量的转换，避免同一个接口混用两种命名。
- 数据库表名使用复数 `snake_case`，例如 `listening_exercises`、`attempts`；列名使用 `snake_case`。
- 主键统一 `id`，外键使用 `<实体>_id`；主键具体类型由技术决策确定。
- 时间字段使用 `created_at`、`updated_at` 等后缀，接口时间采用带时区的 ISO 8601 格式，存储时间以 UTC 为准。
- 布尔字段使用 `is_`、`has_` 或 `can_` 前缀；枚举取值用小写 `snake_case`，并在接口契约中列举允许值。

上述路径与字段是命名示例，尚未实现接口。响应结构、分页方式和错误码应在实现前另行确定。

## 分支、提交与标签

```text
feature/23-listening-player
fix/41-audio-retry
docs/12-api-contract
chore/repository-initialization
release/0.1.0
hotfix/0.1.1-audio-playback
```

任务分支优先带 Issue 编号；首次仓库初始化可不带编号。分支统一小写，不能使用中文或成员姓名。

提交和 PR 标题采用 `type(scope): 说明`，例如 `feat(frontend): 支持逐句播放`。PR 正文关联对应任务。

发布分支不带 `v`，正式版本标签带 `v`，如 `release/0.1.0` 与 `v0.1.0`。修复升级补丁号、兼容功能升级次版本号、不兼容变更升级主版本号。`0.x` 阶段仍须记录不兼容变化，已发布标签不移动、不覆盖。

## 环境与配置

环境统一三个标识：

- `development`：个人开发与共享开发联调。
- `staging`：发布验收。
- `production`：正式服务。

环境变量采用 `UPPER_SNAKE_CASE`，如 `APP_ENV`、`DATABASE_URL`、`LLM_API_KEY`。本地真实值写入未跟踪的 `.env` 文件，样例只保留字段和非敏感默认值。

前端仅接收可公开的配置。任何会被打包进浏览器的环境变量都可能被用户读取，不得存放模型密钥、数据库密码或对象存储私钥。

迁移文件使用迁移工具生成的命名，依赖锁文件使用包管理器生成的名称；不要为了本规范手工重命名工具管理的文件。
