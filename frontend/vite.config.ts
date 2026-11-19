import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import dictionary from '../backend/config/module3/dictionary-schema.json' with { type: 'json' }

// Share the frozen dictionary with the API; bundle only labels, not its audit data.
// This also supports a running API whose older projection includes only codes.
const skillTable = dictionary.tables.find(table => table.name === 'skill') as
  { rows: Array<{skill_code: string; skill_name: string}> } | undefined
const skillNames = Object.fromEntries((skillTable?.rows ?? []).map(row => [row.skill_code, row.skill_name]))

// 开发端口固定 5173：后端 CORS 只放行 localhost:5173 与 127.0.0.1:5173。
// 端口被占用时直接报错，避免 Vite 自动换端口导致跨域失败。
export default defineConfig({
  plugins: [react()],
  define: { __M3_SKILL_NAMES__: JSON.stringify(skillNames) },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    // .cache 下是 npm 缓存与本地验证用的临时浏览器数据，不要让 Vite 触发页面重载。
    watch: {
      ignored: ['**/.cache/**'],
    },
  },
})
