/** 管理端通用展示辅助。 */

/** 服务端未知值保留原值，显示「未知（原值）」，不当作成功状态。 */
export function labelOf(
  labels: Record<string, string>,
  value: string | null | undefined,
): string {
  if (!value) {
    return ''
  }
  return labels[value] ?? `未知（${value}）`
}
