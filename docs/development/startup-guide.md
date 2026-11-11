# 本地启动指南（Windows / PowerShell）

适用范围：模块一登录与两端页面框架的基础启动流程。模块二分支已实现后端题库与受控音频，真实样例导入另见 [模块二验收指南](../acceptance/module-2/guide.md)；模块二业务页面、作答判分、错题本与推荐后续实施。实际迁移范围以所检出的分支为准。

启动顺序：**PostgreSQL 数据库 → 后端服务 → 前端页面**。首次使用完成第 1～6 节；之后按第 7 节启动即可。

本文以项目路径 `C:\work\ShengShengRuEr` 为例。其他成员使用时替换成自己的路径；路径含空格时保留引号。命令均在 PowerShell 中执行，每组执行成功后再继续。

## 1. 准备环境与代码

| 软件 | 项目要求或原开发环境记录 | 用途 |
| --- | --- | --- |
| Git | 能正常拉取仓库 | 同步代码 |
| Python | 3.13.16；一期统一技术版本 V1.2 | 运行后端，见 `backend/.python-version` |
| Node.js | 24.14.0；`package.json` 的最低兼容版本不替代验收目标 | 运行前端，见 `frontend/.node-version` |
| npm | 11.9.0；独立检查版本，不假定随 Node.js 安装的版本一致 | 安装前端依赖 |
| PostgreSQL | 后端 README 记录为 18.6，安装 18 系列服务端 | 保存账号与角色等数据 |

检查环境：

```powershell
git --version
py -3.13 --version
node --version
npm.cmd --version
```

2026-11-02 本机实际环境：Python 3.14.3、Node.js 24.13.0、npm 11.6.2、PostgreSQL 18.6。数据库安装在 `E:\postgresql`，Windows 服务名为 `postgresql-x64-18`。已完成依赖安装、开发库初始化与前后端启动；接口验收 8/8 通过。

如果缺少软件，先安装对应运行环境。安装 PostgreSQL 时保留数据库服务端和命令行工具，记录 `postgres` 用户密码，本文使用默认端口 `5432`。安装 Python 时包含 Python Launcher（`py` 命令）。安装后重新打开 PowerShell。

已有本地修改时先保存并处理，再同步代码：

```powershell
Set-Location "C:\work\ShengShengRuEr"
git status
git switch develop
git pull --ff-only origin develop
```

前后端已合入 `develop`，启动时直接使用该分支，无需分别切换两个功能分支。

## 2. 创建 PostgreSQL 数据库

确认 PostgreSQL 服务已运行。可在 Windows 的“服务”中检查，也可查看：

```powershell
Get-Service -Name '*postgres*'
```

打开 PostgreSQL 安装自带的 **SQL Shell (psql)**，按提示连接本机服务，数据库填写 `postgres`，用户填写 `postgres`，输入安装时设置的密码。也可以在 PowerShell 中执行（安装路径不同时替换）：

```powershell
& "E:\postgresql\bin\psql.exe" -h 127.0.0.1 -p 5432 -U postgres -d postgres -W
```

连接成功后，在 `psql` 中执行：

```sql
CREATE DATABASE shengshengruer;
```

输入 `\q` 退出。若提示数据库已存在，确认它是本项目使用的开发库后继续，不要删除或重建已有数据库。这里仅创建数据库，业务表由第 4 节的迁移命令创建。

## 3. 首次安装后端并填写配置

在 PowerShell 中进入后端目录，创建独立环境并安装仓库锁定的依赖：

```powershell
Set-Location "C:\work\ShengShengRuEr\backend"
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

后续始终使用这里的 `.venv`，无需激活环境，也无需修改 PowerShell 执行策略。

首次创建配置文件；已有 `.env` 时会保留原文件：

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
notepad .env
```

将 `.env` 改为以下结构，替换数据库密码与 JWT 密钥：

```dotenv
APP_ENV=development
LOG_LEVEL=INFO
DATABASE_URL="postgresql+psycopg://postgres:YOUR_DATABASE_PASSWORD@127.0.0.1:5432/shengshengruer"
JWT_SECRET_KEY=YOUR_RANDOM_SECRET
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=120
AUDIO_STORAGE_DIR=var/audio
```

- `YOUR_DATABASE_PASSWORD`：第 2 节中 `postgres` 用户的真实密码。密码中包含 `@`、`#`、`%` 等 URL 特殊字符时，密码部分需进行 URL 编码，例如 `@` 写成 `%40`、`#` 写成 `%23`、`%` 写成 `%25`。
- `YOUR_RANDOM_SECRET`：在同一个后端目录执行下面的命令，将输出的一整行随机字符串填入。至少 32 个字符，不能保留样例占位值。

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

保存并关闭记事本。后端读取的是 **`backend/.env`**，不是仓库根目录的 `.env.example`。本地 `.env` 已被 Git 忽略，密钥和数据库密码不提交到仓库。

## 4. 初始化数据并启动后端

继续在 `backend` 目录执行：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.seed
```

第一条命令按当前分支迁移：模块一包含 `users`、`roles`、`user_roles`、`token_revocations`，模块二分支还包含题库、批次和检查等表，另有 Alembic 版本表。第二条写入开发账号；正常会看到“种子数据完成：roles=2, users=2”。种子脚本可重复执行，但不会重置已有账号密码。

启动后端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

看到 `Application startup complete` 后，保持该窗口运行，打开 [后端接口文档](http://127.0.0.1:8000/docs)。后端根路径 `/` 没有页面，访问它得到 404 不代表服务启动失败。接口文档能打开后，还需登录确认数据库连接正常。

## 5. 首次安装并启动前端

**新开第二个 PowerShell 窗口**，执行：

```powershell
Set-Location "C:\work\ShengShengRuEr\frontend"
npm.cmd ci
if (-not (Test-Path -LiteralPath .env.local)) {
    Copy-Item -LiteralPath .env.example -Destination .env.local
}
npm.cmd run dev
```

`npm.cmd ci` 按已提交的 `package-lock.json` 安装依赖，重装时会替换现有 `node_modules`；无需删除或重新生成锁文件。使用 `npm.cmd` 可以避开 PowerShell 对 `npm.ps1` 的执行策略限制。

默认 `.env.local` 内容为：

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

这里填写后端基础地址，不附加 `/api/v1`。已有 `.env.local` 时检查其值；更改后需重启前端。前端配置只放公开地址，不放数据库密码或 JWT 密钥。

看到开发服务器就绪后，保持窗口运行，打开 [系统登录页](http://127.0.0.1:5173/login)。前端固定使用 `5173` 端口；仅启动前端时可以显示页面，但登录需要后端和数据库同时运行。

## 6. 登录并检查功能

第 4 节初始化后，新建开发库中可使用：

| 身份 | 用户名 | 密码 | 登录后页面 |
| --- | --- | --- | --- |
| 管理员 | `admin` | `admin123` | `/admin` 管理端首页 |
| 学生 | `student` | `student123` | `/student` 学生端首页 |

这些账号仅用于本地开发和测试，种子脚本只允许在 `development` / `test` 环境运行。

按以下顺序检查：

1. 管理员登录后进入管理端首页，能看到管理端接口返回的信息。
2. 退出后，用学生账号登录，应进入学生端首页，看不到管理菜单。
3. 保持学生登录，在地址栏访问 `http://127.0.0.1:5173/admin`，应跳转到无权限页 `/403`。
4. 退出后访问受保护页面，应回到登录页。

当前两端首页是模块一的基础框架，尚无题库和听力练习入口属于当前范围。

## 7. 以后每次怎么启动与停止

环境和数据库已经初始化后，确认 PostgreSQL 服务运行，再分别打开两个 PowerShell 窗口。

**窗口一：启动后端。**

```powershell
Set-Location "C:\work\ShengShengRuEr\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**窗口二：启动前端。**

```powershell
Set-Location "C:\work\ShengShengRuEr\frontend"
npm.cmd run dev
```

打开 [系统首页](http://127.0.0.1:5173)。首次安装步骤无需每天重复；关闭网页不会停止服务，在两个终端分别按 `Ctrl+C` 即可停止前后端。停止服务不会删除数据库数据。

拉取新代码后，若后端 `requirements.txt` 变化，重新执行后端依赖安装；若新增数据库迁移，执行 `alembic upgrade head`；若前端依赖或锁文件变化，重新执行 `npm.cmd ci`。这些命令的完整写法分别见第 3、4、5 节。

## 8. 可选验证

这些是可选检查，无需在每次启动时执行。2026-11-02 已在本机执行接口验收，结果为 8/8 通过；本次未执行前端构建或后端 pytest。

后端已启动且默认开发账号可用时，在第三个 PowerShell 窗口执行接口验收：

```powershell
Set-Location "C:\work\ShengShengRuEr\backend"
.\.venv\Scripts\python.exe scripts\acceptance.py
```

预期汇总为 `8/8 通过`，包含管理员/学生登录、权限隔离和退出后旧 token 失效等检查。该脚本会登录并退出测试会话，请只对开发环境运行。

前端构建验证：

```powershell
Set-Location "C:\work\ShengShengRuEr\frontend"
npm.cmd run build
```

该命令同时进行 TypeScript 检查与打包，通过后生成 `frontend/dist`。日常开发继续使用 `npm.cmd run dev`。

如需运行后端 pytest，见 [后端测试说明](../../backend/README.md#测试)。测试会清空并重建独立测试库的 `public` schema；不要把 `TEST_DATABASE_NAME` 指向任何需要保留数据的数据库。

## 9. 常见问题

| 现象 | 处理方式 |
| --- | --- |
| `py` 或 `py -3.13` 找不到 | 准备 Python 3.13.16 与 Python Launcher，重新打开终端；用 `py -0p` 查看可用版本，也可用解释器绝对路径。 |
| `.venv\Scripts\python.exe` 找不到 | 确认当前在 `backend` 目录，且已完成第 3 节创建环境的步骤。 |
| `ModuleNotFoundError: app`、找不到 `alembic.ini` | 先进入 `backend`，再执行迁移、种子或后端启动命令。 |
| 找不到 `npm`，或 npm 脚本被禁止执行 | 先确认 Node.js 已安装并重新打开终端；本文统一使用 `npm.cmd`。 |
| pip 报 `No matching distribution` / npm 报 `ETARGET` | 核对运行环境版本、软件源与仓库锁定版本是否一致；保留完整错误交给维护者核查，不擅自取消版本锁定。 |
| npm 缓存不可写 | 在 `frontend` 执行 `npm.cmd ci --cache .cache/npm`。 |
| `psql` 找不到 | 使用第 2 节完整路径，或从开始菜单打开 SQL Shell；按实际安装版本修改路径。 |
| PostgreSQL `connection refused` | 确认数据库服务已启动，且 `DATABASE_URL` 的地址与端口正确。 |
| PostgreSQL `password authentication failed` | 检查数据库用户名、真实密码和密码中的 URL 编码。这里使用数据库账号，不是网页登录账号。 |
| `database "shengshengruer" does not exist` | 按第 2 节创建数据库；迁移命令不会代为创建数据库本身。 |
| `relation "users" does not exist` | 对 `.env` 指向的开发库执行第 4 节迁移，再初始化账号。 |
| JWT 密钥校验失败 | 将 `backend/.env` 的 `JWT_SECRET_KEY` 改为随机生成的至少 32 字符字符串，保存并重启后端。 |
| 前端 `5173` 或后端 `8000` 端口被占用 | 确认是否已启动过本项目，优先回到原窗口使用或按 `Ctrl+C` 停止；不要重复启动。前端更换端口还需同步后端 CORS 配置。 |
| 页面能打开但登录失败 / 请求报错 | 先确认后端窗口无错误、数据库运行、前端配置指向 `http://127.0.0.1:8000`，再检查账号初始化及密码。 |
| 学生访问管理端出现 403 | 属于预期权限限制；退出后使用管理员账号登录。 |
| 修改 `.env` 后没有生效 | 保存文件并手动重启对应服务；同时检查当前终端是否存在覆盖文件配置的同名环境变量。 |

本文按仓库当前配置、迁移、种子数据和验收脚本核对编写。本机已验证依赖安装、数据库初始化与前后端启动，登录页及后端接口文档返回 HTTP 200，接口验收 8/8 通过。
