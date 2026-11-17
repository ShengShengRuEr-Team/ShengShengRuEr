export const stateLabels: Record<string, string> = {
  review:'逐题审核',align:'音频对齐',assemble:'来源组装',annotate:'整套标注',annotate_sample:'前5题试标',
  extract:'原件提取',assembly_extract:'答案解析识别',reuse:'复用已确认结果',normalize:'音频解码',reference:'原文提取',preflight:'环境检查',materials:'材料准备',
  awaiting_materials: '待补材料', queued: '排队中', running: '执行中', awaiting_alignment: '等待核听确认',
  awaiting_source: '等待来源确认', awaiting_sample: '等待5题试标复核', awaiting_review: '等待整套审核',
  not_ready: '尚未就绪', pending: '待审核', approved: '已通过', unpublished: '未发布', preparing: '发布准备中',
  pending_batch: '待审批次已保存', validating: '校验中', activating: '切换中', published: '已发布',
  completed: '处理完成', failed: '失败', stopping: '正在停止', stopped: '已停止',
  missing: '未上传', reserved: '已预留，等待传输', uploading: '接收中', ready: '已验证', cancelled: '已取消', superseded: '已替代',
  generated: '已生成，待审核', generated_empty: '空错因已生成，待审核', not_generated: '待生成', legacy_pending: '旧错因已停用，待重新标注',
}
export const label = (state: string) => stateLabels[state] ?? state
export const skillName = (skill: {skill_code: string; skill_name?: string | null}) =>
  skill.skill_name ?? __M3_SKILL_NAMES__[skill.skill_code] ?? '名称暂缺'
export const paperName = (paper: {exam_level: string; exam_year: number; exam_month: number; paper_set: number}) =>
  `${paper.exam_year}年${paper.exam_month}月 ${paper.exam_level} 第${paper.paper_set}套`
