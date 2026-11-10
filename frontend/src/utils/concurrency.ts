/**
 * 限制并发的 order-preserving map。
 * 用于管理端列表逐卷补调状态：并发有上限，避免一次打出几十个重请求。
 */
export async function mapWithConcurrency<T, R>(
  items: readonly T[],
  limit: number,
  worker: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  const results = new Array<R>(items.length)
  const size = Math.max(1, Math.min(limit, items.length))
  let nextIndex = 0

  async function run(): Promise<void> {
    while (nextIndex < items.length) {
      const currentIndex = nextIndex
      nextIndex += 1
      results[currentIndex] = await worker(items[currentIndex], currentIndex)
    }
  }

  await Promise.all(Array.from({ length: size }, () => run()))
  return results
}

/** 判断异常是否来自主动取消（AbortController / axios CanceledError）。 */
export function isAbortError(error: unknown): boolean {
  if (!error || typeof error !== 'object') {
    return false
  }
  const name = (error as { name?: unknown }).name
  return name === 'CanceledError' || name === 'AbortError'
}
