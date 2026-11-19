import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

/**
 * 前端测试独立配置：只服务 `npm test`，不进入生产构建。
 * jsdom 无真实布局/音频；响应式与播放器由手工/E2E 覆盖。
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    restoreMocks: true,
    clearMocks: true,
    unstubGlobals: true,
    css: false,
    testTimeout: 30000,
    hookTimeout: 30000,
  },
})
