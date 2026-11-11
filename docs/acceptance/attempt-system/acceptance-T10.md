# 基础作答系统 T10 真实数据验收记录（2026-11-10）

> 本记录由独立验收人出具，**未修改任何实现代码**；开发人回填不作为验收依据。
> 代码基线：`feature/11-attempt-check` @ `9b88928`（T04–T09 已在 PR2 分支）；T10 仅使用受控材料与独立数据库，不改仓库代码。
> 依据：需求 v0.21、开发文档 v0.14、module-2 验收指南（`docs/acceptance/module-2/guide.md`）。

## 1. 受控材料（不入 Git）

| 文件 | 字节 | SHA-256 | 校验 |
|---|---|---|---|
| `CET4_2025年6月_第1套_真题.pdf` | 366,427 | `2880…09ac08` | 与 `materials-sha256.json` 一致 |
| `CET4_2025年6月_第1套_答案解析.pdf` | 4,459,701 | `1021…b232f4` | 一致 |
| `CET4_2025_06_1_听力.m4a` | 4,169,648 | `a23dc74f…864c` | 一致（时长 1416.05s，AAC 44.1kHz 双声道） |
| `CET4_2025_06_1_paper_scan_300dpi.pdf` | 6,202,057 | `6739…d780f2` | 一致（无文本层 300dpi 派生件；非纸张实扫） |

材料包自带 `scan-generation.json`（renderer=pypdfium2 5.14.0、image_only=true、source_sha256）与 `材料说明.txt`；材料包**不替代完整验收报告**。

## 2. 环境与隔离

- 独立数据库 `shengshengruer_t10`（新库，迁移 `0005_attempt_system`，19 表）；**开发库 `shengshengruer` 全程未动（仍 0004、16 表、无 attempt 表）**。
- 音频受控目录：`D:\pytemp\t10_audio`；音频本体不入库（DB 只存 storage_key/hash/duration）。
- 真实 API 服务：`127.0.0.1:8012`，`APP_ENV=test`；验收结束后停止进程。
- 种子账号：`admin/admin123`、`student/student123`（`app.seed`）；判分核对另建 `t10_grader_a/b`。

## 3. 材料结构化（真实文本 + 标注的近似时间轴）

| 环节 | 方法 | 结果 |
|---|---|---|
| 题干/选项 | 真题 PDF 文本层解析 | 25 题 × 4 选项，无缺失 |
| 答案/解析 | 答案解析 PDF（19 页扫描件）OCR 180dpi + 规则解析 | 25 题答案与中文解析齐备；Q5 解析句被 OCR 截断，按 300dpi 页面图像人工复核补回（选项 C 加框） |
| 听力原文 | OCR「听力原文」+ `[N]` 题号标记 | 8 篇、60 段（body + question） |
| 时间轴 | 按各篇/各段文本长度比例分配（**近似值，非强制对齐**） | `start_ms/end_ms` 覆盖 0–1416046ms |
| 音频元数据 | ffprobe | duration_ms=1416046、file_hash 与清单一致 |

## 4. 导入与发布

`run_import` 结果：`status=imported`，batch `CET4_2025_06_1-6643d29d02b3`（active/current），计数 `content_groups=1, passages=8, transcript_segments=60, questions=25, presentations=25`；`expected_question_count=25` 与来源校验通过。

管理员确认：`GET checks` → 200；`POST visibility {"action":"confirm"}` → 200（`check_passed=true, is_visible=true`）。学生侧：列表 1 套、详情 8 篇 25 题、音频 200（4,169,648 字节，`Accept-Ranges: bytes`）。

## 5. 端到端与判分核对（真实材料）

| 检查 | 实际结果 |
|---|---|
| T09 脚本主流程（真实 HTTP + 只读 SQL） | **PASS=11, FAIL=0, 运行期 BLOCKED=0, 预期冻结 BLOCKED=4, exit 0** |
| 样例已消耗守卫（再次运行同一学生） | `[BLOCKED] 样例已被该学生使用（attempts>0 或 markers>0）`，**exit 2** |
| V-E1 判分正确性（学生 A，官方答案全对） | 200；`correct_count=25, correct_rate=100, practice_score=249`；响应无逐题/答案/解析字段 |
| V-E1 判分正确性（学生 B，仅 Q22 改错） | 200；`correct_count=24, correct_rate=96, practice_score=235`（听力篇章权重 20，符合 249 分公式） |
| 库内快照 | 学生 A：25 行 attempt_answers，全部 `is_correct=true`；学生 B：Q22 `correct_option=B, selected_option=C, is_correct=false` |
| 数据库最终状态 | attempts=3、answers=75、rejections=0、content_checks=1、paper_visibility=1 |

## 6. 限制与说明

1. **时间轴为近似值**：按文本长度比例分配，非 ASR 强制对齐；`start_ms/end_ms` 仅满足数据结构与粗粒度定位，不作为精确校对依据。
2. **解析来源为 OCR 整理**：Q5 解析句经 300dpi 图像人工复核补回；其余解析未逐字人工校对。
3. **题干来自答案解析 OCR**（CET 听力原卷只印选项，题干为听力内容）；选项取自真题 PDF 文本层。
4. **仅一套受控材料**：T10 覆盖 2025-06 第 1 套；未覆盖多套/多批次真实数据。
5. **未运行 ASR/强制对齐、未做人工核听**：与 module-2 指南 B16"1416 秒核听须真人"不同；本记录不宣称 B16 已完成。

## 7. 结论

**T10：PASS（附上述限制）**。真实试卷/音频已导入独立库并发布，真实 HTTP 端到端与判分正确性核对通过；T09-A2/A5 由本轮真实执行补齐。
仍保持 BLOCKED：V-E4（D-14 需求冲突）、V-E5b/V-E2/E3（API-2 冻结）、M-32/M-41（D-14）、M-03b（逐题回显冻结）。
