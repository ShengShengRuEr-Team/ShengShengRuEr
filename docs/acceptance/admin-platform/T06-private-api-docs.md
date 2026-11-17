# T06 私有接口文档与受限调试 · 证据记录

| 字段 | 值 |
| --- | --- |
| ac_id | AC-13、AC-14、AC-15（T06 范围） |
| requirement_ids | ADM-IF01 |
| executor | 开发实施人（lead agent） |
| executed_at | 2026-11-17 14:30—14:45（Asia/Shanghai） |
| commit_sha | 起点 `721d951`；T06 本地提交（不 push） |
| workspace_state | 后端新增文档路由/白名单/调试中间件；前端新增文档页；新增唯一依赖 swagger-ui-dist@5.35.0 |
| environment | Windows；Python 3.13.16；Node 24.14.0；PostgreSQL 本地；测试库 `shengshengruer_test` |
| migration_heads | `0007_admin_audit_events (head)`，T06 零迁移 |
| dependency_versions | 新增 `swagger-ui-dist@5.35.0`（精确版本，已入 package.json/lock） |
| result | **PASS** |

## 1 公开入口关闭

`FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`，全局生效（含开发/测试）。实测：

```text
/docs -> 404
/docs/oauth2-redirect -> 404
/redoc -> 404
/openapi.json -> 404
/api/v1/openapi.json -> 404
```

旧业务接口（`/api/v1/admin/overview` 等）行为不变，仍 200 且字段 `{role,message}`。

## 2 受保护 schema

- `GET /api/v1/admin/openapi.json`，`admin:docs:read`：无 token 401、学生 403、管理员 200。
- 原始 JSON（无 `code/data` 外壳）、`Cache-Control: no-store`。
- 含真实路径与 `x-admin-debug-allowlist`（9 条，method 全为 GET，含 `path_template/permission`）。
- 零秘密：响应不含 `JWT_SECRET_KEY`、`DATABASE_URL`、连接串、演示密码。

## 3 受限 GET 调试

| 场景 | 结果 |
| --- | --- |
| 管理员 + 标记 GET 白名单路径 | 200，写 `DOC_GET_DEBUG`（method/path_template/status_code、duration、request_id） |
| 无标记普通请求 | 与改造前完全一致，不写 DOC 事件 |
| 学生 + 标记 | 403 |
| 无 token + 标记 | 401 |
| 管理员缺 `docs:debug` | 403 |
| 管理员缺目标权限 | 403 |
| 非白名单路径（schema/导出/overview） | 400 |
| `POST` + 标记 | 400 |
| 尾斜杠/双斜杠/`%2F`/`%252F` | 400 |
| 标记值非 `1` | 400 |
| 目标路由 404（详情不存在） | 404，事件 result=FAILURE、status_code=404 |
| 审计写失败 | 响应替换为 500，不交付原结果 |

审计不记录 query、Authorization、token、响应体；summary 仅三字段。

## 4 前端

- `/admin/tools/api`（`admin:docs:read`，菜单同权限显隐）；schema 经 `rawClient` 取得后以 `spec` 传给本地打包的 Swagger UI（`swagger-ui-dist@5.35.0`），不使用 `url`、无 CDN/外部 validator。
- `persistAuthorization=false`、`validatorUrl=null`、`supportedSubmitMethods` 默认 `[]`；具备 `admin:docs:debug` 才显示「启用调试」，启用后仅 `get`。
- requestInterceptor：同源 + 仅 GET + 模板白名单；启用后注入 Bearer 与 `X-Admin-Docs-Debug: 1`；非白名单本地拒绝。
- schema 加载失败显示错误与重试，不回退公开入口；卸载清空容器与引用。
- 构建产物检查：`dist/assets/*.js` 无 `cdn.jsdelivr`/`unpkg`/`cdnjs`/`swagger-ui-dist@`/Google Fonts 外链。

## 5 测试

```text
后端定向：17 passed in 7.84s
后端全量：385 passed in 123.67s（368 + 17）
前端全量：182 passed（175 + 7）
typecheck：通过
build：✓ built
alembic current → 0007_admin_audit_events (head)
alembic check → No new upgrade operations detected.
```

新增后端 17 例（公开入口 5、schema 3、调试 9）；前端 7 例（白名单工具 3、文档页 4）。

## 6 过程中发现并修复

1. 调试白名单最初用 `scope["path"]`（已被 ASGI 解码）判断，`%2F` 绕过无法识别；改为基于 `scope["raw_path"]` 原始编码判断，实测尾斜杠/双斜杠/单双编码均 400。
2. 中间件错误响应最初借用 `JSONResponse` 需要完整 scope，改为直接发送 ASGI 响应消息，避免 scope 不完整导致的异常。
3. Swagger mock 未声明参数导致 typecheck 报 `Tuple type []`，补齐 mock 签名后通过。

## 7 未覆盖项

- 监控读取类白名单（database/server/cache/transport/oauth）与缓存元数据页属 T08，届时同一常量补登。
- 真实浏览器/子路径部署下的 Swagger 交互（E2E）属 T09。
- 文档页的下载按钮与在线 validator 被显式禁用，未做“隐藏 curl”二次定制（`supportedSubmitMethods` 已限制发起请求）。

## 8 结论

**PASS**。公开入口真 404、受保护 schema、白名单双重校验、调试审计与前端本地 Swagger 按 §8 实现；后端 385、前端 182 全绿，零迁移且无漂移。
