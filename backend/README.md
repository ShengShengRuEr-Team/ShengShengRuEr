# backend

后端包含模块一认证权限与模块二题库、整卷展示、管理员配套内容、可见性和受控音频。模块二验收整改见 [验收目录](../docs/acceptance/README.md)。

Windows 首次运行请先阅读 [本地启动指南](../docs/development/startup-guide.md)，创建 `backend/.venv`、安装依赖并初始化数据库。下文命令均在 `backend` 目录执行。

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
│   ├── api/                 # 认证路由、管理端占位路由与鉴权依赖
│   ├── core/                # 配置、角色定义、JWT/bcrypt、统一异常
│   ├── db/                  # 声明基类、会话、4 张表模型
│   ├── main.py              # 应用装配与统一响应/异常外壳
│   ├── schemas.py           # 请求与响应模型
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
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

`JWT_SECRET_KEY` 未配置、少于 32 字符或使用占位值时，应用拒绝启动；`JWT_ALGORITHM` 只允许 `HS256`。

## 初始化数据库

首次安装先创建数据库 `shengshengruer`；已有数据库使用迁移增量升级，不清空账号数据：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.seed
```

模块一迁移创建 4 张表（模块二分支还会增建题库与批次等业务表）：`users`、`roles`、`user_roles`、`token_revocations`。

种子数据只允许在 `development` / `test` 环境写入默认口令：

| 角色 | `role_key` | 用户名 | 密码 | 进入端 |
| --- | --- | --- | --- | --- |
| 管理员 | `admin` | `admin` | `admin123` | 管理端 |
| 学生 | `student` | `student` | `student123` | 学生端 |

身份由后端角色决定，前端不做权限码判断。

## 启动

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
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
| 4 | GET | `/api/v1/admin/overview` | 仅 `admin` 角色 |

鉴权顺序固定为**先 401、后 403**：无 token / token 失效 / 账号停用返回 401；
token 有效但不是管理员，调用接口 4 返回 403。

`/api/v1/admin/overview` 是一期保留的最小管理端接口，用于验证「页面隐藏与后端接口权限保持一致」：
管理端首页会调用它；学生即使在前端手输 `/admin`，也会被路由守卫拦到 403，直接调接口同样返回 403。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

测试会自动创建/重建 `shengshengruer_test` 库，执行 Alembic 迁移并写入种子数据。
连接账号需要具备 `CREATE DATABASE` 权限；如不希望自动建库，可先手工创建该库。

模块一历史基线结果：**11 passed**，覆盖 6 条验收用例与 5 条鉴权边界（登录失败提示一致、422、
token 篡改、非法认证方案、401 优先于 403）。

## 端到端验收

先启动服务，再执行：

```powershell
.\.venv\Scripts\python.exe scripts\acceptance.py
```

预期输出 **8/8 通过**，退出码为 0。

## 代码风格

```powershell
ruff check .
```

Ruff 配置在 [pyproject.toml](pyproject.toml)；`B008` 因 FastAPI `Depends` 约定而忽略。

## 一期边界

- 模块一：登录、退出、当前用户、角色及基础接口鉴权。
- 模块二：真实数据库题库、整卷查询、配套内容、可见性、音频与导入；[接口契约](../docs/development/module-2/api.md)、[验收指南](../docs/acceptance/module-2/guide.md)。
- 自动处理、作答判分、错题本、画像与推荐后续实施。
- 不引入 Redis；退出失效写入 `token_revocations` 表。
- 数据库结构只通过 Alembic 迁移变更。
