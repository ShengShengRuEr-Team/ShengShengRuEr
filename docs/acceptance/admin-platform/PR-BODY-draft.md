# PR 草稿：管理端阶段一（T00–T09）

> 仅落盘草稿，未 push、未创建 PR。目标分支：`develop`；源分支：`feature/admin-platform`。

## 标题

feat(admin): 管理端阶段一 T00–T09（认证/权限/审计/账户/日志导出/首页/文档/留存调度/监控/交付）

## 范围

- 基线归档与固定权限目录（21 码）、持久会话、活动节流。
- 两类审计事件、request-id、降级通道。
- 用户管理、个人中心、在线会话强退、登录/操作日志、三类 CSV 导出。
- 业务首页（一致快照 + TTL 缓存）、私有接口文档与受限 GET 调试。
- 留存清理：三表 + 独立调度进程（互斥/补跑/重试/中断）+ 任务监控。
- 监控：15 秒采样（DB/OS/调度/审计健康）、缓存查看/清理、TLS 证据中间件、OAuth 能力页、live/ready、模块三只读（默认关闭）。
- 前端管理端布局、页面、轮询与状态展示；子路径部署支持。

## 提交清单（自 develop `3609186` 起）

```text
92bc80a feat(admin): T00–T01 基线归档、持久会话与固定权限
2f473da feat(admin): T02 审计基础（两类事件表、事务与降级通道、request-id）
5e8a386 fix(admin): T02 审计通道拆分（登录/操作分表，降级记录 channel）
ae6d206 feat(admin): T03 账户/本人/在线（用户管理、个人中心、会话强退与活动节流）
d0c7332 feat(admin): T04 日志查询接口（登录/操作列表与详情）
20d0ead feat(admin): T04 三类 CSV 导出（用户/登录日志/操作日志）
5aec78d feat(admin): T04 共用 UI 与枚举生成（权限组件、rawClient、恢复态、日志页）
0e22cc7 feat(admin): T03-FE 用户管理与个人中心页面
721d951 feat(admin): T05 业务首页（一致快照统计与真实 TTL 缓存）
2eb999c feat(admin): T06 私有接口文档与受限 GET 调试
026f77b feat(admin): T07a 留存调度三张表与 0008 迁移
82354cc feat(admin): T07b 留存调度进程、互斥、补跑/重试/中断与批删除
62c9298 feat(admin): T07c 留存任务控制 API 与任务监控页
25bc512 test(admin): T07a 模型用例只断言 seed 不可变列
b696f1b feat(admin): T08a 15 秒采样服务与真实指标
cc0c5a5 feat(admin): T08b 监控读取、缓存清理、TLS 证据、OAuth 与健康探针
10f02db feat(admin): T08c 监控前端页面与轮询
6ccf845 docs(admin): T08 实现要点与证据索引
7c426d0 fix(admin): 支持子路径部署 base 与 BrowserRouter basename
```

## 验证

- 后端 431 passed；前端 193 passed；typecheck/build 通过。
- `alembic heads` 单 head `0008`；`alembic check` 无漂移；迁移往返（0001→0008→base→0008）通过。
- 双实例：跨实例会话/撤销、缓存与监控实例隔离；调度进程心跳/触发/暂停恢复/重启通过。
- `/health/live` 200、断库 `/health/ready` 503；JWT 轮换旧 token 401。
- 子路径 `/listening/` 经一次性代理验证剥离、静态与深链；**真实 TLS 终止未实测**。

## 验收结论

AC 详见 `docs/acceptance/admin-platform/T00–T09` 各卡记录；T09 结论 **PASS（含未实测项）**，AC-22 未实测不宣称通过。

## 风险与未覆盖项

- 模块三未集成、OAuth 未启用、单实例缓存。
- 真实 TLS/证书、1280/1920 视觉与键盘走查、真实浏览器下载未实测。
- 发布前需按 `T09-release-checklist.md` 备份并核对依赖 SHA。
