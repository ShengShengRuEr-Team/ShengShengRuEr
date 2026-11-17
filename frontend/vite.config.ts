import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// 生产子路径由 VITE_BASE 注入（例如 /listening/）；默认根路径。
// API 基址由 VITE_API_BASE_URL 注入（子路径下为 /listening/api/v1）。
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  return {
    base: env.VITE_BASE?.trim() || '/',
    plugins: [react()],
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      // .cache 下是本机验证用的临时浏览器数据，不触发页面重载。
      watch: {
        ignored: ['**/.cache/**'],
      },
    },
  }
})
