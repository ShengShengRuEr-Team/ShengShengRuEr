# backend

模块一后端：账号登录、管理员/学生身份区分、接口级鉴权、敏感字段隔离、试卷与题目读取、处理任务占位接口。

## 技术栈

- Python 3.14.2
- FastAPI 0.143.0 + Uvicorn 0.54.0
- PostgreSQL 18.6 + SQLAlchemy 2.1.4 + Alembic 1.20.0
- Pydantic 2.14.1 + pydantic-settings 2.16.2
- PyJWT（HS256）+ bcrypt（不使用 passlib）
- pytest 9.2.0 + httpx 0.28.1

完整锁定版本见 [requirements.txt](requirements.txt)。

## 目录

```text
backend/
├── app/
│   ├── api/                 # 认证、试卷、管理端题目、任务路由与鉴权依赖
│   ├── core/                # 配置、权限码、JWT/bcrypt、统一异常
│   ├── db/                  # 声明基类、会话、8 张表模型
│   ├── main.py              # 应用装配与统一响应/异常外壳
│   ├── schemas.py           # 学生/管理端两套题目响应模型
│   └── seed.py              # 开发/测试环境种子数据
├── alembic/                 # 版本化迁移
├── scripts/acceptance.py    # 真实服务端到端验收脚本
├── tests/                   # pytest 用例
├── .env.example
├── alembic.ini
├── pyproject.toml           # Ruff 配置
├── pytest.ini
└── requirements.txt
```

## 配置

复制样例并填写真实值：

```powershell
cd backend
Copy-Item .env.example .env
```

`.env` 已被根目录 `.gitignore` 忽略，禁止提交。至少需要填写：

```dotenv
APP_ENV=development
DATABASE_URL=postgresql+psycopg://postgres:真实密码@127.0.0.1:5432/shengshengruer
JWT_SECRET_KEY=至少32位随机字符串
```

生成 JWT 密钥：

```powershell
D:\guochuangxiangmu\.venv-backend\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

`JWT_SECRET_KEY` 未配置、少于 32 字符或使用占位值时，应用拒绝启动；`JWT_ALGORITHM` 只允许 `HS256`。

## 初始化数据库

数据库 `shengshengruer` 需先创建并保持为空库：

```powershell
D:\guochuangxiangmu\.venv-backend\Scripts\python.exe -m alembic upgrade head
D:\guochuangxiangmu\.venv-backend\Scripts\python.exe -m app.seed
```

种子数据只允许在 `development` / `test` 环境写入默认口令：

| 角色 | 用户名 | 密码 | 权限码 |
| --- | --- | --- | --- |
| 管理员 | `admin` | `admin123` | 全部 5 个 |
| 学生 | `student` | `student123` | `paper:read`、`question:read` |

同时写入 1 套占位试卷与 2 道占位题目。

## 启动

```powershell
D:\guochuangxiangmu\.venv-backend\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- Swagger：<http://127.0.0.1:8000/docs>
- OpenAPI：<http://127.0.0.1:8000/api/v1/openapi.json>

## 接口

所有业务接口以 `/api/v1` 为前缀，统一响应 `{"code", "msg", "data"}`，认证头 `Authorization: Bearer <JWT>`。

| # | 方法 | 路径 | 权限 |
| --- | --- | --- | --- |
| 1 | POST | `/api/v1/login` | 公开 |
| 2 | POST | `/api/v1/logout` | 已登录 |
| 3 | GET | `/api/v1/getInfo` | 已登录 |
| 4 | GET | `/api/v1/papers` | `paper:read` |
| 5 | GET | `/api/v1/papers/{paper_id}/questions` | `question:read` |
| 6 | GET | `/api/v1/admin/papers/{paper_id}/questions` | `question:read_sensitive` |
| 7 | POST | `/api/v1/admin/processing-tasks` | `task:start` |
| 8 | GET | `/api/v1/admin/processing-tasks` | `task:read` |
| 9 | GET | `/api/v1/admin/processing-tasks/{task_id}` | `task:read` |

鉴权顺序固定为**先 401、后 403**：无 token / token 失效 / 账号停用返回 401；token 有效但缺少权限码返回 403。

学生题目接口只返回 `StudentQuestion` 模型，字段为 `id`、`question_no`、`prompt_text`、`option_a`~`option_d`；答案、解析、听力原文只存在于管理端 `AdminQuestion` 模型，不通过运行时删字段实现。

## 测试

```powershell
D:\guochuangxiangmu\.venv-backend\Scripts\python.exe -m pytest -v
```

测试会自动创建/重建 `shengshengruer_test` 库，执行 Alembic 迁移并写入种子数据。连接账号需要具备 `CREATE DATABASE` 权限；如不希望自动建库，可先手工创建该库。

当前结果：15 passed，覆盖 10 条验收用例与鉴权边界（登录失败、422、token 篡改/过期、404、非法任务状态）。

## 端到端验收

先启动服务，再执行：

```powershell
D:\guochuangxiangmu\.venv-backend\Scripts\python.exe scripts\acceptance.py
```

预期输出 10/10 通过，退出码为 0。

## 代码风格

```powershell
ruff check .
```

Ruff 配置在 [pyproject.toml](pyproject.toml)；`B008` 因 FastAPI `Depends` 约定而忽略。

## 一期边界

- 只实现模块一；不包含作答判分、错题本、画像与推荐。
- 处理任务为占位实现：创建后状态停留在 `pending`，执行链路由模块三接入。
- 不引入 Redis；退出失效写入 `token_revocations` 表。
- 数据库结构只通过 Alembic 迁移变更。
