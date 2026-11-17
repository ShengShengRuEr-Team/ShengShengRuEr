# 管理端阶段一：设计决策收口记录（DD-01—DD-05）

- 登记日期：2026-11-17（Asia/Shanghai），实施分支 `feature/admin-platform`，基线 `develop @ 3609186`。
- 唯一主文档：`D:\guochuangxiangmu\docs\development\admin-platform\development.md`（V1.0，606 行，SHA-256 `9276f1f2e9d38c1d3dc7edd11cd78773a6f526566f59cfe5975e4997e23e3ba7`），本文件逐条转录其 §2。
- 需求基线：`requirements.md` V1.0，SHA-256 `728105bdefece77759cdf69f30723e35bf48859b75e78dbf8637e5c4dac8cc74`，未修改任何需求条款，仓库内归档件与来源逐字节一致。
- 来源限制：主文档引用的《第三轮复验意见》`若依管理端引入_正式需求规格_第三轮复验意见_20261116.md` 与《参考开发文档借鉴评估》`若依管理端引入_参考开发文档借鉴评估_20261117.md` 在本地缺失（路径与哈希已登记于 `docs/acceptance/admin-platform/evidence/T00-docs-sha256.txt` 的缺失清单说明与 `T00-baseline.md`）。本文件只转录主文档 §2 已写明的结论，不引用、不推断、不编造缺失文档的任何内容。
- 有效范围：本记录不修改原需求的验收编号，也不宣称已获得新的独立复验通过；DD 条款随实现同步，不把设计新增说成需求已修订。

## 决策条款（转录自主文档 §2）

| 决策 | 收口规则 | 对应需求/补充验证 |
| --- | --- | --- |
| DD-01 安全回退 | 常规回退保留新版认证与会话撤销检查。确需回旧鉴权，关闭所有受保护流量，停全部旧/新 API 实例，统一更换 JWT 签名密钥，取消旧密钥接受能力，重新启动所有实例并验证旧 token 全部 401 后才恢复流量；无法满足则禁止该回退 | §11.2、AC-35；改密前、强退前、停用再启用前和普通 token，跨实例全部失效 |
| DD-02 TLS 证据 | Uvicorn 固定 `--no-proxy-headers`；最外层 TransportEvidenceMiddleware 先保存原始 TCP client 与 scheme，再由该层独自校验代理信任。外部 scheme 和后端传输事实分字段；拿不到原始事实时 unknown，不能用处理后的 scope 反推 TLS | §4.2/6.5、AC-22；真实代理、直连 TLS、伪造头和中间件顺序验证 |
| DD-03 导出事件 | 保留 `EXPORT_COMPLETED` 编码，准确含义为“文件已生成、行数已确定、审计已持久化，获准返回”；界面标签“导出生成完成”。它不证明响应已发送、传输完整或客户端保存。发送中断只补运行事件 | §4.1/10.2、AC-32；审计提交后发送前崩溃不冒充已交付 |
| DD-04 ID 类型 | user_id 等既有数值 ID 为正整数；session_id/event_id/run_id 为 UUID；job_id 是 `admin.retention_cleanup`。格式非法 422，不存在 404；任务控制显式拒绝非白名单编码为 400 | §2.1/11.1、各路由类型与边界测试 |
| DD-05 角色投影 | 既有 roles 关系保留；新用户只选 admin/student 之一。管理列表/详情/CSV 的单值 role 按 admin 优先、否则 student；无已知角色投影 null，界面“未知”，不改库。role 筛选按同一投影，混合角色不落学生列表或学生计数 | §3.1/10.1/10.2、AC-01/30/31；getInfo.roles 继续原数组 |

## 另行选定（转录自主文档 §2 末段）

- 日志与新列表排序：按各实体时间列倒序、主键倒序。
- 过滤文本的 `%`、`_` 作为包含匹配的普通字符转义，不给用户通配查询。
- 新权限码逐字沿用正式规格，大小写保留 `resetPassword/loginLogs/operationLogs`，不改为参考稿命名；共 21 个，不允许 `*:*:*` 通配。

## 本轮（T00–T02）落地约束

1. DD-04：`auth_sessions.id`、`event_id` 均使用 UUID；`user_id` 保持正整数。
2. DD-05：本轮不改 roles 关系、不做角色投影接口；`getInfo.roles` 保持原数组，仅新增 `permissions`。
3. DD-01：本轮建立“旧 token 因缺少 `auth_version`/`session_id` 一律 401”与“会话撤销跨实例生效”的事实基础，回退演练属 T09。
4. DD-02/DD-03 涉及 T06/T08/T09，本轮不实现，仅登记以免实现时与主文档冲突。
