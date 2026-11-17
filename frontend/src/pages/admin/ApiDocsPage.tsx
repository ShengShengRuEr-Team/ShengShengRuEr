import { ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Space, Switch, Typography } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import 'swagger-ui-dist/swagger-ui.css'
import { fetchOpenapiSchema } from '../../api/admin/docs'
import type { OpenapiSchema } from '../../api/admin/docs'
import { ApiError } from '../../api/api-error'
import { usePermission } from '../../auth/usePermission'
import { getAccessToken } from '../../auth/storage'
import { PERM_DOCS_DEBUG } from '../../generated/adminConstants'
import { isAllowedDebugRequest } from '../../utils/docsDebug'

export default function ApiDocsPage() {
  const canDebug = usePermission(PERM_DOCS_DEBUG)
  const [schema, setSchema] = useState<OpenapiSchema | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [debugEnabled, setDebugEnabled] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const loadSchema = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const next = await fetchOpenapiSchema()
      setSchema(next)
    } catch (cause) {
      setSchema(null)
      setError(cause instanceof ApiError ? cause.message : '加载接口文档失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSchema()
  }, [loadSchema])

  useEffect(() => {
    if (!schema || !containerRef.current) {
      return
    }
    let cancelled = false
    const container = containerRef.current

    const mount = async () => {
      const module = await import('swagger-ui-dist/swagger-ui-es-bundle.js')
      if (cancelled) {
        return
      }
      const SwaggerUIBundle = module.default
      const allowlist = Array.isArray(schema['x-admin-debug-allowlist'])
        ? schema['x-admin-debug-allowlist']
        : []
      container.innerHTML = ''
      SwaggerUIBundle({
        spec: schema,
        domNode: container,
        deepLinking: false,
        // 凭证不持久化，调试开关默认关闭。
        persistAuthorization: false,
        validatorUrl: null,
        supportedSubmitMethods: debugEnabled ? ['get'] : [],
        tryItOutEnabled: false,
        withCredentials: false,
        displayRequestDuration: true,
        requestInterceptor: (request: Record<string, unknown>) => {
          if (!debugEnabled) {
            throw new Error('调试未启用')
          }
          const method = String(request.method ?? 'GET')
          const url = String(request.url ?? '')
          if (
            !isAllowedDebugRequest(
              allowlist,
              method,
              url,
              window.location.origin,
            )
          ) {
            throw new Error('该请求不在调试白名单内')
          }
          const token = getAccessToken()
          if (!token) {
            throw new Error('未登录')
          }
          request.headers = {
            ...(request.headers as Record<string, string>),
            Authorization: `Bearer ${token}`,
            'X-Admin-Docs-Debug': '1',
          }
          return request
        },
        presets: [SwaggerUIBundle.presets.apis],
      })
    }

    void mount()
    return () => {
      cancelled = true
      // Swagger UI 没有 destroy API：清空容器并解除引用，避免残留 DOM/凭证。
      container.innerHTML = ''
    }
  }, [schema, debugEnabled])

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Card
        title="接口文档"
        extra={
          <Space>
            {canDebug && (
              <Space size="small">
                <Typography.Text>启用调试（仅 GET）</Typography.Text>
                <Switch
                  checked={debugEnabled}
                  onChange={setDebugEnabled}
                  aria-label="启用调试"
                />
              </Space>
            )}
            <Button
              icon={<ReloadOutlined />}
              loading={loading}
              onClick={() => void loadSchema()}
            >
              刷新 schema
            </Button>
          </Space>
        }
      >
        {error && (
          <Space orientation="vertical" size="small" style={{ width: '100%' }}>
            <Alert type="error" showIcon title={error} />
            <Button onClick={() => void loadSchema()}>重试</Button>
          </Space>
        )}
        {!canDebug && (
          <Typography.Text type="secondary">
            当前账号没有启用调试的权限，只能查看接口文档。
          </Typography.Text>
        )}
        <div ref={containerRef} data-testid="swagger-ui" />
      </Card>
    </Space>
  )
}
