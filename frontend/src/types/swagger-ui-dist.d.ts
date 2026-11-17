declare module 'swagger-ui-dist/swagger-ui-es-bundle.js' {
  const SwaggerUIBundle: {
    (config: Record<string, unknown>): unknown
    presets: { apis: unknown }
    plugins: Record<string, unknown>
  }
  export default SwaggerUIBundle
}

declare module 'swagger-ui-dist/swagger-ui.css'
