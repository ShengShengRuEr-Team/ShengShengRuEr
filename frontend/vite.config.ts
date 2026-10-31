import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发端口固定 5173：后端 CORS 只放行 localhost:5173 与 127.0.0.1:5173。
// 端口被占用时直接报错，避免 Vite 自动换端口导致跨域失败。
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
  },
})
