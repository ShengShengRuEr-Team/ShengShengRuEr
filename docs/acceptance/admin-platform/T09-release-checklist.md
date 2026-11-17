# T09 发布与回退检查表

## 1. 依赖与构建

- [ ] `backend/requirements.txt` 与锁一致；唯一新增 `psutil==7.2.2`（T08 批准）；当前 SHA-256 `6f964878…a78f`（基线 `728105b…cc74` 因 psutil 变更）。
- [ ] 前端 `package-lock.json` 一致；唯一新增 `swagger-ui-dist@5.35.0`（T06 批准）。
- [ ] `npm run typecheck && npm run build` 通过；子路径构建时设置：
  `VITE_BASE=/listening/`、`VITE_API_BASE_URL=/listening/api/v1`。

## 2. 配置项

| 变量 | 说明 |
| --- | --- |
| `DATABASE_URL` | 必填，`postgresql+psycopg://` |
| `JWT_SECRET_KEY` / `JWT_ALGORITHM=HS256` | ≥32 位、非占位；轮换会使旧 token 全 401 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 默认 120 |
| `ADMIN_DASHBOARD_CACHE_ENABLED` | 默认 true；关闭时缓存状态 not_configured |
| `ADMIN_MONITORING_ENABLED` | 默认 true；测试环境 false |
| `PUBLIC_ORIGIN` | 站点 origin；**不代表已验证 TLS** |
| `TRUSTED_PROXY_CIDRS` / `PROXY_HEADER_MODE` | 可信代理网段与单一模式（forwarded/x_forwarded） |
| `ADMIN_MODULE3_OBSERVATION_ENABLED` | 默认 false；本版本无模块三表 |
| `ADMIN_AUDIT_FALLBACK_DIR` / `AUDIO_STORAGE_DIR` | 受控持久卷目录 |

## 3. 启动

```bash
# API（根路径）
python -m uvicorn app.main:application --host 127.0.0.1 --port 8001 --no-proxy-headers

# API（子路径 /listening/）
python -m uvicorn app.main:application --host 127.0.0.1 --port 8001 \
  --no-proxy-headers --root-path /listening

# 调度进程（独立，不嵌入 API）
python -m app.admin_scheduler
```

- 反向代理：子路径 `location /listening/ { proxy_pass http://127.0.0.1:8001/; }`（尾斜杠剥离），`/listening/api/...` 最终到后端 `/api/v1/...`。
- 禁止在 Uvicorn 开启代理头解析（必须 `--no-proxy-headers`）。

## 4. 迁移顺序

- [ ] 发布前 `pg_dump` 备份。
- [ ] `alembic upgrade head`（0001→0008 顺序执行；禁止跳版）。
- [ ] `alembic current` 为 `0008_admin_retention_scheduler`；`alembic check` 无漂移。
- [ ] 不在开发库执行升级；成功/失败都以备份为准。

## 5. 回退

1. 停调度进程（避免继续执行保留清理）。
2. 回退前端静态与代理配置。
3. 滚动重启 API 至上一版本（兼容当前库结构）。
4. 仅在确认必须回退结构时：停写 → 备份 → `alembic downgrade <上一版本>` → 恢复前端；downgrade base 会删表，禁止在生产无备份执行。
5. 保留审计降级文件目录与 `var/` 数据。

## 6. 已知限制

- 模块三未集成（默认关闭，Worker 存活 unknown，不生成心跳）。
- OAuth Server 未启用（固定 not_configured）。
- 缓存为单实例进程内 TTL；无 Redis/Celery/APScheduler。
- 监控/池/缓存指标按实例展示，不提供集群总量。
- 真实 TLS 终止、1280/1920 视觉与键盘走查、真实浏览器下载：**未实测**（T09-D 记录）。

## 7. 发布后验证

- `/health/live` 200、`/health/ready` 200。
- 管理员登录、`/admin/dashboard`、`/admin/monitor/database|server`、`/admin/monitor/jobs`。
- 调度进程心跳 `ok`（≤60 秒）。
- 旧 token 在密钥轮换后 401。
