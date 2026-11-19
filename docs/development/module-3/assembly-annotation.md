# 第7步原件组装与第8步关联标注

最新授权（2026-11-07）：用户要求沿用候选规则并开发至全线PASS，现已继续第9、10步。当前流程和真实证据以[全流程说明](full-pipeline.md)为准，需求V2.2／开发V1.8。本文下方的第9步前停止是第7—8步历史阶段边界；对应显式assemble/annotate_sample/annotate请求仍按原契约硬停止，不被新的completed请求影响。

以下为第7—8步历史交付记录：2026-11-07，Asia/Shanghai。需求V2.1，开发V1.7。该轮后端范围到第9步开始前停止，未使用completed。当前第9—10步授权按上方最新说明执行，默认任务仍停止align。

当前完成：本套8篇25题已通过组装、标注结构/词典/证据检查与Codex逐题内容复核；25项主要技能、25项答案证据、1项错因候选。最终任务`10e9c1d5-33e2-4570-a86a-7aaa8264144c`停在`awaiting_confirmation / annotate`，`batch_id=null`，第9步未启动。完整报告（历史本地资料，随验收证据另行交接）、25题效果（历史本地资料，随验收证据另行交接）分别保存检查结论和实际内容。

## 当前流程

1. 核验正式上游任务379ec20c-f12a-42c4-97cb-628dd131cb1b的原件、方法、锁、模型清单、阶段JSON与页图；复用165句及原时间，不重跑OCR正文、ASR或对齐。
2. 原卷有文字层，按听力部分题号提取A—D选项；明确处理A/C与B/D双栏顺序，Section说明不归上一题。未知续行、重复选项或缺项阻断。
3. `assembly_scan.py`通过冻结PaddleOCR检测/识别、PaddleX SortQuadBoxes和CropByPolys，从答案原件第2—9页读取解析；保留原始框、页图、置信度和SHA-256。不做像素行推断、字典分词或字符补空格，不改写上游正文。
4. `source_assembly.py`由题号和篇章标题确定解析归属，只接受明确答案声明；“排除B”不是答案B。原卷第8页KEYS独立核对扫描解析的25个答案。缺失、冲突、低可信或不支持的版式停止。
5. 保存全部题目、原卷恒等映射和来源，`stop_after=assemble`停止。已有完整组装可核验复用，不重复OCR。
6. `stop_after=annotate_sample`调用真实DeepSeek完成前5题。模型只接收文字、固定词典和句子ID，不接收音频、图像或时间。原件字段由程序提供且候选schema禁止覆盖。
7. 第8步候选门控检查JSON/schema、启用且适用的三级词典、主要技能、同篇连续正文引用、逐字引文、有效对齐和依据文字。时间由程序取正文句边界。
8. 逐题内容复核小样，保存草稿hash、审核者真实身份类别、时间、答案支持理由和技能适用理由；不能以DeepSeek自评代替。
9. 新建`stop_after=annotate`任务，绑定小样及语义复核，核验后直接复用其5题响应，只调用余下20题。整套再做第8步检查与逐题语义复核，保存处理草稿，释放租约，在annotate停止。

组装保留上游原件M/W说话人；标注输入包含说话人。证据须含代词所需先行词，不得只摘孤立结论。主要技能选完成题目必需的具体能力，不按表面词汇增加泛化辅助技能；角色遵循既有PRIMARY/AUXILIARY约束。错因是针对具体选项及原文机制的候选，依据不足可为空，不推断学习者状态。

流程中的第9行仍是模块第8步内部动作，不是业务第9步。`validate_result`、`check_result`、`persist_result`、pending业务批次、版本切换及学生可见性不在本轮执行范围。

## 新增请求与阶段接口

`TaskRequest.stop_after`增加`assemble`、`annotate_sample`、`annotate`；缺省`align`不变。`reuse_alignment_task_id`显式绑定原任务；`reuse_assembly_scan_task_id`用于复用解析OCR（包括开发失败任务中已完整保存的扫描阶段），`reuse_assembly_task_id`复用组装。`reuse_annotation_task_id`和`sample_review`同时出现，后者须绑定小样草稿hash并覆盖5题。整套annotate没有已审核小样即拒绝。

管理员`GET /api/v1/admin/processing-tasks/{id}/stages/{stage}`新增reuse、assembly_extract、assemble、annotate、annotation_checks。返回前核对产物hash，继续遵守管理员鉴权及无服务器任意路径暴露规则。

`reuse_full_annotation_task_id`与`annotation_review`成对指定整套语义修订来源，只用于annotate。审核必须绑定源草稿hash并覆盖全部25题；approved题复用不可变候选，changes_required题必须带具体repair_feedback并发起新的真实请求。复用核查方法自身hash、提示词/词典、题目/正文/说话人与候选hash，不能以旧审核绕过变更；小样仍独立受原小样审核门控。本套整套初次语义复核发现第12、14、16、20、23题问题，新增5次真实请求修复，其余20题复用，最后独立worker复核不再新增收费请求。

停止点只调用`processing_drafts`保存auto_draft/final，最终任务`awaiting_confirmation`且`batch_id=null`。这里的final表示本任务冻结草稿视图，不表示业务审批完成或发布。

## 复用与失效

`reuse.py`核验原件类别/哈希、试卷编码、源任务状态、源方法hash、原锁、模型清单与实际上游算法文件。上游依赖包括audio、reference、auto_reference、document_reference、reference_document_scan、ocr_refinement、reference_locator、acoustic_features、ctc_alignment、contracts。

worker/tasks的下游编排和ocr_worker的新分派入口变化，不据此重跑未变化的上游算法。上游文字、分句、音频、算法或资源变化则拒绝复用，不能用旧通过结果为新方法背书。旧方法中的Windows反斜杠路径键规范化后核验，不忽略缺失hash。

新任务保存来源task/method hash及source_artifact_id。解析OCR、组装和小样各自核验对应实现及产物；改变解析器可复用未变的扫描结果，改变提示词则不能沿用旧小样。所有复用明确记录来源，不能称为本次重新推理通过。

## 模型与费用审计

请求仍为冻结的deepseek-flash、thinking disabled、temperature 0、JSON object、max_tokens 4096、httpx直接请求；不升级依赖或模型。最终提示词版本`m3.annotations.v5`；旧v2/v3/v4真实运行及失败按原版本保留。实际请求全文、原始响应model、usage和调用时间保存在processing_llm_attempts与受控证据文件。服务别名不保证权重不可变。

结构/证据契约失败每题最多3次尝试，反馈具体失败条件，拒绝原稿与重试检查点保留；语义复核另行进行，不由模型重复自评替代。本套真实请求合计56次（含历史小样与修订、1次有界契约重试），其中小样20次估算0.05649300美元、整套所有真实请求估算0.16824060美元。含历史未知测试预留的阶段承诺1.84887900美元，均未超过既定上限；不是账户实际扣款证明。

发送前按UTF-8字节上界、最大输出和20%余量预留；未知失败不归零。成功响应按冻结峰值单价估算保守费用，不把估算称为账户扣款。小样0.50美元、同套2美元、阶段5美元上限不变。同一音频的run_key独立于任务编号和方法版本，失败重试计入同套。

预留使用postgres数据库共享advisory lock，串行核查当前集群可连接数据库中的既有账本；历史测试/未知预留也保守计入，不以换任务/换隔离库清零。不能核查旧账本即停止收费调用。未授权清理任何真实费用账本。

## 验证与限制

真实材料必须经管理员ASGI API和独立worker，另存请求、任务状态、阶段输出、方法、调用账本和前后业务表计数。验收工具`scripts/review_module3_downstream.py`固定使用已有隔离验收库，不重置它；HTTP传输采用FastAPI TestClient ASGI，不将其称为公网或TCP部署验收。

结构/来源一致性与语义分报。逐题内容复核由本轮Codex检查正文、选项、答案、解析和词典边界，保留具体依据；不是双人独立人工金标准，也不报告模型自评准确率。既有300ms只保留上游复现一致性结论，不升级为独立人工绝对精度。

真实结果与最终文件：本轮证据目录（历史本地资料，随验收证据另行交接）；完成状态以其中result.md为准。

## 后续待办

- 用户另行授权后才开始模块第9步业务检查和待审批次入库；先把原卷导出的可信题量/来源带入后续请求，保持当前版本不动。
- 第10步内容/音频/标注最终复核、管理员显式切换版本和独立学生可见性确认另行执行。
- 本轮不覆盖任意新版式、多套试卷泛化、双人独立教学标注准确率或独立人工毫秒精度评定。
- 不提交、合并或部署；原develop仓库保持不动，现有未提交实现保留。
