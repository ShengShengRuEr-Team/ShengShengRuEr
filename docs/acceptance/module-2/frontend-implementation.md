# 模块二前端实现记录（任务二）

- 日期：2026-11-08
- 依据：《模块二前端需求文档_20261107.md》V0.3（F01–F18）
- 实现范围：4 个页面 + 接口层 + 播放器，**未改动后端与数据库结构**
- 原型：未改动（按确认保留 V1.0 示意稿）

## 一、代码改动

| 类型 | 文件 | 内容 |
| --- | --- | --- |
| 新增 | `src/api/listening.ts` | 6 个接口的调用封装（含超时/取消参数） |
| 新增 | `src/api/audio.ts` | 音频二进制通道：绕开 JSON 外壳、错误 Blob→text 解析 msg、Abort、对象 URL 释放、401 复用统一处理 |
| 新增 | `src/pages/admin/ListeningPaperListPage.tsx` | 管理端列表：本地筛选、逐卷补调状态（并发 3 / 超时 8s / ≤20 套）、单行失败降级 |
| 新增 | `src/pages/admin/ListeningPaperDetailPage.tsx` | 详情：左右分栏共享 `currentPassageId`、检查摘要 + 抽屉、确认/取消开放（弹窗 + 理由）、试听 |
| 新增 | `src/pages/student/ListeningPaperListPage.tsx` | 学生端列表：只显示可访问试卷，"查看听力"入口 |
| 新增 | `src/pages/student/ListeningPaperPage.tsx` | 整卷页：按篇章分页（`passages.length`）、页面级常驻播放器、只读题目 |
| 新增 | `src/ui/AudioPlayer.tsx` | 播放/暂停、进度、音量、加载失败重试 |
| 新增 | `src/ui/PaperStatusTags.tsx` | 状态标签：当前批次 / 检查 / 开放 / 可访问 / 审核 / 内容完整度 |
| 新增 | `src/utils/format.ts`、`src/utils/concurrency.ts` | 时长与时间格式化；限并发 map + 取消判定 |
| 修改 | `src/api/types.ts`、`src/api/adapters.ts` | 听力 DTO 与 camelCase 视图模型 |
| 修改 | `src/constants/routes.ts`、`src/router/index.tsx` | 4 条路由（管理端 2 + 学生端 2），详情页复用布局 |
| 修改 | `src/layouts/AdminLayout.tsx`、`StudentLayout.tsx` | 新增「题库管理」「听力练习」菜单，详情页高亮父级 |
| 修改 | `src/styles/global.css` | 分栏、片段、题目、播放器、分页、问题列表样式 |

依赖：未新增任何 npm 包。

## 二、环境与基线

| 项目 | 实际情况 |
| --- | --- |
| 前端 | Node v22.22.2 / npm 10.9.7，`npm install` 按锁文件安装 165 个包 |
| 后端 | 本地 `127.0.0.1:8000` 已运行（开发机既有进程，未重启） |
| 数据库 | 本地 PostgreSQL 18.6，已导入 `CET4_2025_06_1`（25 题 / 8 篇章 / 165 片段） |
| 账号 | `admin`（管理员）、`student`（学生），均为种子账号 |
| Git 基线 | 已从 `origin/develop` = `b965a0f`（含 PR #5/#6）创建 `feature/m2-frontend-listening-papers`，改动已迁到该分支；分支已解除对 `develop` 的上游跟踪，避免误推。经比对，本次基线与开发时所用后端**接口字段无差异**（`schemas_listening.py` 及两个接口文件 diff 为空）。 |

## 三、验证结果（2026-11-08 实测）

| 编号 | 结果 | 证据 |
| --- | --- | --- |
| F01 工程门禁 | **PASS** | `npm run typecheck`（`tsc -b`）0 错误；`npm run build` 成功，4 个页面各自独立 chunk |
| F02 路由与权限 | **PASS** | 学生访问 `/admin/listening-papers` 重定向到 `/403`（截图 `shot_403.png`） |
| F03 管理端列表 | **PASS（含模拟）** | 真实数据正常；行级失败显示"获取失败"且"重试"不跳详情（`shot_t3_row_fail.png`）；列表 500 为浏览器层模拟：Alert + 重试 + 空态不再误报"请先导入"（`shot_f13_list500.png`） |
| F04 详情内容一致 | **PASS** | 8 篇章、第 1 篇 2 题、13 条片段与接口逐项一致；答案/解析/来源均显示（截图 `shot_admin_detail2.png`） |
| F05 答案表达 | **PARTIAL** | 两个答案字母均显示，相同显示"答案字母一致"；**当前题库映射为恒等，重排提示未触发**；`content_state` 全为"可用"，高亮态未出现 |
| F06 检查结果 | **PASS（模拟）** | 通过态真实（`shot_drawer.png`）；未通过（2 个问题、确认禁用、取消可用，`shot_f06_fail.png`）与尚未检查（`shot_f06_none.png`）由拦截响应构造；checks 500 显示"检查结果读取失败"（`shot_f13_checks500.png`） |
| F07 确认开放 | **PASS** | 弹窗提交后页面刷新为"已确认开放"，后端 `is_visible=true`、`check_passed=true` |
| F08 取消开放 | **PASS（部分）** | 取消后学生列表变空态（截图 `shot_student_empty.png`）；恢复后重新出现（`shot_student_restored.png`）。**详情/音频请求 404 未单独复测** |
| F09 学生端列表 | **PASS** | 仅可见试卷，无管理入口与后台状态词，入口为"查看听力"（`shot_student_list.png`） |
| F10 学生端整卷 | **PASS** | 真实鼠标事件播放成功：`paused=false, t=2.46s`；按钮变暂停、进度前进（`shot_playing.png`） |
| F11 学生字段裁剪 | **PASS** | `performance.getEntriesByType('resource')` 中**无任何 `/admin/` 请求**；页面无答案/解析/正文 |
| F12 只读约束 | **PASS** | 无交卷/提交按钮，选项不可选，页面有"作答功能后续开放"说明 |
| F13 异常与持久化 | **PARTIAL** | 500 提示与重试已用模拟验证（`shot_f13_list500.png`、`shot_f13_checks500.png`）；**断库与重启后端仍未测** |
| F14 文档同步 | **PASS** | 截图已归档；§2.5 联调基线表已按实测填写（提交 `b965a0f`、后端地址、库用途、批次号、复核时间）；接口文档路径已核实为 `docs/development/module-2/api.md` |
| F15 篇章分页 | **PASS** | 8 篇按 `passages.length` 渲染；首篇"上一篇"禁用；翻篇播放不中断：2.46s → 4.02s（第 2 篇）→ 4.91s（回第 1 篇） |
| F16 音频适配 | **PARTIAL** | 二进制通道正常，`<audio src>` 为 `blob:`，未出现"缺少统一响应外壳"；**错误 Blob 解析与 URL 释放未单独观测** |
| F17 分栏同步 | **PASS（部分）** | 切换篇章左右同时刷新且指向同一 `passage_id`；**两栏滚动回顶未单独断言** |
| F18 无当前批次 | **PASS（模拟）** | companion 返回 `batch_code=null`、空篇章时：显示"暂无当前批次"、确认与取消均禁用（`shot_f18_no_batch.png`）；未造真实无批次数据 |

补充验证：学生访问不存在试卷 `/student/listening-papers/999` → 显示"试卷不存在或暂不可用"（`shot_404.png`）。

## 四、对开发库的影响（必须知会）

为验证 F07/F08，对试卷 `id=1` 执行了一次"取消开放 → 确认开放"：

- 新增 2 条 `visibility_audit_logs` 记录；
- 确认动作会重新执行最低内容检查，新增 1 条 `content_checks` 记录；
- **最终状态已恢复**：`is_visible=true`、`check_passed=true`、`is_current=true`（已用接口复核）。

如需完全干净的验收库，建议在独立库重跑导入后再验收。

## 五、已知但未处理

1. **开发模式重复请求音频**：`React.StrictMode` 下 effect 执行两次，音频在 dev 会下载两次（旧请求被 Abort 并释放）。生产构建不存在该行为，未改 StrictMode。
2. **管理端列表状态补调成本**：`1 + 2N` 次请求，其中 companion 为整卷重接口；>20 套已降级为"仅基本信息"，轻量汇总接口属后续优化。
3. **页面不能重新执行检查**：与需求 V0.3 §4.3、D8 一致，属后端能力缺失，未绕过。
4. 分页篇数、题号全部来自接口，未硬编码 8 篇或题号范围。

## 六、第二轮修复（2026-11-08 17:40）

第一轮自查发现 4 个问题，已修并逐项回归：

| # | 问题 | 修复 | 回归结果 |
| --- | --- | --- | --- |
| 1 | 列表行内"重试"点击冒泡到 `onRow`，会跳到详情 | `event.stopPropagation()` + 抽出 `openDetail()` | 用 CDP 拦截 `companion`/`checks` 使整行失败，点"重试"后 `location.pathname` 仍为 `/admin/listening-papers`（`shot_t3_row_fail.png`） |
| 2 | checks 失败时页头仍用 companion 的 `checkPassed`，出现"尚未检查 + 检查通过"矛盾 | checks 失败单独渲染"检查结果读取失败"，页内摘要与抽屉同步 | 只拦 `checks`：页面出现"检查结果读取失败"，不再出现"尚未检查"（`shot_t2_checks_fail.png`） |
| 3 | 学生端翻篇后停留在页面中部 | 增加 `useEffect(() => window.scrollTo(0, 0), [passageIndex])` | 视口 1440×520：翻篇前 `scrollY=331`，翻篇后 `scrollY=0` 且为第 2 篇 |
| 4 | 需求 §7.8 要求返回列表保留筛选，实际被清空 | 筛选写入 URL query（`?level=&year=`），详情页通过 `location.state.listSearch` 带回 | `?level=CET4` → 进详情 → 点"返回题库管理" → URL 仍为 `?level=CET4`，下拉仍显示 CET4 |

本轮只做读请求与请求拦截，**未改动数据库状态**（`is_visible`/`check_passed` 仍为 true）。

## 七、交接前补测与两处一致性修复

**补测方式：** 用 CDP `Fetch` 域在**浏览器层**改写 `checks` / `companion` / 列表响应，构造后端目前产不出的状态；**全程未改数据库**，会话结束即恢复真实响应。

| 状态 | 构造内容 | 结果 |
| --- | --- | --- |
| 检查未通过 | `is_passed=false` + 2 条 issues | 页头"检查未通过"、摘要"2 个问题"、可访问结论"暂不可访问"、确认开放禁用、取消开放可用 |
| 尚未检查 | `is_passed=false`、`issues=[]`、`checked_at=null` | "尚未检查" + "本页不能重新执行检查"提示 + 确认禁用 |
| checks 500 | HTTP 500 + `{code:500,msg:"数据库不可用"}` | 显示"检查结果读取失败"，不再出现"尚未检查" |
| 无当前批次 | companion `batch_code=null`、`passages=[]` | "暂无当前批次" + 提示，确认/取消均禁用 |
| 列表 500 | HTTP 500 | 顶部 Alert + 重试；空态文案改为"加载失败，请点击上方重试" |

**顺带修掉的两处问题：**

1. 页头检查标签原用 companion 的快照、页内用 checks 记录，两接口不一致时会打架 → 统一为"以 checks 为准，取不到才退回 companion"。
2. 列表加载失败时下方仍显示"暂无试卷，请先导入题库数据"，与报错矛盾 → 改为错误态专属文案（管理端、学生端各一处）。

## 八、提交与交接

- 提交：`247328a feat(frontend): 模块二题库业务页面与听力播放器`（17 文件，+2472/−6）。
- 分支已推送：`origin/feature/m2-frontend-listening-papers`；**未创建 PR**（按流程验收通过后再提）。
- 交接文档：`前端/验收交接_模块二前端_20261108.md`。

## 九、提交前待办

- [x] 从最新 `develop` 建 `feature/m2-frontend-listening-papers`，迁入改动
- [x] 补 §2.5 联调基线表
- [x] 修 4 个自查缺陷并回归
- [x] 补测 F06 两态与 F18（浏览器层模拟，未改数据）
- [x] 提交并推送分支
- [ ] 断库 / 重启后端（F13 剩余部分）建议在验收环境实测
- [ ] 验收人独立验收，通过后再提 PR
