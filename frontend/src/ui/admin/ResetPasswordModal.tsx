import { Alert, Form, Input, Modal } from 'antd'
import { useState } from 'react'
import { resetUserPassword } from '../../api/admin/users'
import type { UserDto } from '../../api/admin/types'
import { ApiError } from '../../api/api-error'
import { showError, showSuccess } from '../../ui/message'
import { validatePassword, validateReason } from '../../utils/passwordRules'

interface Props {
  user: UserDto | null
  onClose: () => void
  onChanged: () => void
}

interface FormValues {
  new_password: string
  reason: string
}

export default function ResetPasswordModal({ user, onClose, onChanged }: Props) {
  const [form] = Form.useForm<FormValues>()
  const [submitting, setSubmitting] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  const close = () => {
    form.resetFields()
    setServerError(null)
    onClose()
  }

  const submit = async () => {
    let values
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    if (!user) {
      return
    }
    setSubmitting(true)
    setServerError(null)
    try {
      const result = await resetUserPassword(user.id, {
        new_password: values.new_password,
        reason: values.reason.trim(),
      })
      showSuccess(
        `密码已重置，${result.revoked_session_count} 个会话已失效，该用户需重新登录`,
      )
      form.resetFields()
      onChanged()
    } catch (error) {
      if (error instanceof ApiError && error.status === 400) {
        setServerError(error.message)
      } else {
        showError('重置失败，结果未确认，请刷新核实')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={Boolean(user)}
      title={user ? `重置密码：${user.username}` : '重置密码'}
      okText="重置"
      cancelText="取消"
      confirmLoading={submitting}
      onOk={() => void submit()}
      onCancel={close}
      destroyOnHidden
    >
      {serverError && (
        <Alert type="error" showIcon title={serverError} style={{ marginBottom: 16 }} />
      )}
      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item
          name="new_password"
          label="新密码"
          rules={[
            {
              validator: (_, value: string) => {
                const message = validatePassword(value ?? '')
                return message ? Promise.reject(new Error(message)) : Promise.resolve()
              },
            },
          ]}
        >
          <Input.Password placeholder="10—64 字符，含字母与数字" autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="reason"
          label="操作理由"
          rules={[
            {
              validator: (_, value: string) => {
                const message = validateReason(value ?? '')
                return message ? Promise.reject(new Error(message)) : Promise.resolve()
              },
            },
          ]}
        >
          <Input.TextArea maxLength={200} showCount rows={3} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
