# backend

模块一后端：账号登录、退出、当前用户信息、管理员/学生身份区分与基础接口鉴权。

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
D:\guochuangxiangmu\.venv-backend\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

`JWT_SECRET_KEY` 未配置、少于 32 字符或使用占位值时，应用拒绝启动；`JWT_ALGORITHM` 只允许 `HS256`。

## 初始化数据库

数据库 `shengshengruer` 需先创建并保持为空库：

```powershell
D:\guochuangxiangmu\.venv-backend\Scripts\python.exe -m alembic upgrade head
D:\guochuangxiangmu\.venv-backend\Scripts\python.exe -m app.seed
```

迁移会创建 4 张表：`users`、`roles`、`user_roles`、`token_revocations`。

种子数据只允许在 `development` / `test` 环境写入默认口令：

| 角色 | `role_key` | 用户名 | 密码 | 进入端 |
| --- | --- | --- | --- | --- |
| 管理员 | `admin` | `admin` | `admin123` | 管理端 |
| 学生 | `student` | `student` | `student123` | 学生端 |

身份由后端角色决定，前端不做权限码判断。

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
| 4 | GET | `/api/v1/admin/overview` | 仅 `admin` 角色 |

鉴权顺序固定为**先 401、后 403**：无 token / token 失效 / 账号停用返回 401；
token 有效但不是管理员，调用接口 4 返回 403。

`/api/v1/admin/overview` 是一期保留的最小管理端接口，用于验证「页面隐藏与后端接口权限保持一致」：
管理端首页会调用它；学生即使在前端手输 `/admin`，也会被路由守卫拦到 403，直接调接口同样返回 403。

## 测试

```powershell
D:\guochuangxiangmu\.venv-backend\Scripts\python.exe -m pytest -v
```

测试会自动创建/重建 `shengshengruer_test` 库，执行 Alembic 迁移并写入种子数据。
连接账号需要具备 `CREATE DATABASE` 权限；如不希望自动建库，可先手工创建该库。

当前结果：**11 passed**，覆盖 6 条验收用例与 5 条鉴权边界（登录失败提示一致、422、
token 篡改、非法认证方案、401 优先于 403）。

## 端到端验收

先启动服务，再执行：

```powershell
D:\guochuangxiangmu\.venv-backend\Scripts\python.exe scripts\acceptance.py
```

预期输出 **8/8 通过**，退出码为 0。

## 代码风格

```powershell
ruff check .
```

Ruff 配置在 [pyproject.toml](pyproject.toml)；`B008` 因 FastAPI `Depends` 约定而忽略。

## 一期边界

- 只实现模块一：登录、退出、当前用户、身份区分、基础接口鉴权。
- **不包含**题库、题目、处理任务、作答判分、错题本、画像与推荐，这些在后续模块中实现。
- 不引入 Redis；退出失效写入 `token_revocations` 表。
- 数据库结构只通过 Alembic 迁移变更。
