import { Alert, Button, Space } from 'antd'

export interface SubmitResultAction {
  key: string
  label: string
  onClick: () => void
  primary?: boolean
}

export interface SubmitResultAlertProps {
  type: 'success' | 'info' | 'warning' | 'error'
  message: string
  description?: string
  actions?: SubmitResultAction[]
}

/** P-13：提交结果唯一反馈位；不显示 HTTP 码/错误常量/payload。 */
export default function SubmitResultAlert({
  type,
  message,
  description,
  actions = [],
}: SubmitResultAlertProps) {
  return (
    <Alert
      type={type}
      showIcon
      message={message}
      description={description}
      action={
        actions.length > 0 ? (
          <Space size={8} wrap>
            {actions.map((action) => (
              <Button
                key={action.key}
                size="small"
                type={action.primary ? 'primary' : 'default'}
                onClick={action.onClick}
              >
                {action.label}
              </Button>
            ))}
          </Space>
        ) : undefined
      }
    />
  )
}
