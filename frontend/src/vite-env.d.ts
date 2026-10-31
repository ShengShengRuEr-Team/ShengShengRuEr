/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 后端基础地址；未配置时代码内回退到 http://127.0.0.1:8000。 */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
