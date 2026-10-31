/** 试卷级别（exam_level）展示文案；未知值原样显示。 */
export const EXAM_LEVEL_LABELS: Record<string, string> = {
  cet4: '四级',
  cet6: '六级',
}

export function formatExamLevel(level: string): string {
  return EXAM_LEVEL_LABELS[level] ?? level
}
