/**
 * 由 Vite BASE_URL 推导 BrowserRouter basename。
 * 根路径 "/" → "/"；子路径 "/listening/" → "/listening"。
 */
export function routerBasename(baseUrl: string): string {
  const stripped = baseUrl.replace(/\/+$/, '')
  return stripped === '' ? '/' : stripped
}
