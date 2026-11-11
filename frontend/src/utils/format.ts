/** 毫秒转 mm:ss（超过 1 小时用 h:mm:ss）；无效值返回 --:--。 */
export function formatDuration(ms: number | null | undefined): string {
  if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) {
    return '--:--'
  }
  const totalSeconds = Math.floor(ms / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const pad = (value: number) => String(value).padStart(2, '0')
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${pad(minutes)}:${pad(seconds)}`
}

/** 时间区间：00:00–00:58。 */
export function formatTimeRange(startMs: number, endMs: number | null | undefined): string {
  if (typeof endMs !== 'number') {
    return formatDuration(startMs)
  }
  return `${formatDuration(startMs)}–${formatDuration(endMs)}`
}

/** ISO 时间转本地可读格式；无效值返回 —。 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) {
    return '—'
  }
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return iso
  }
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** 试卷的展示名：2025 年 6 月 · 第 1 套。 */
export function formatPaperLabel(year: number, month: number, paperSet: number): string {
  return `${year} 年 ${month} 月 · 第 ${paperSet} 套`
}

/** 接口返回的 content_scope，本阶段只有听力。 */
export function formatContentScope(scope: string): string {
  return scope === 'listening' ? '听力部分' : scope
}
