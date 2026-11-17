import { Alert, Form, Input, Modal, Radio } from 'antd'
import { useState } from 'react'
import { changeUserStatus } from '../../api/admin/users'
import type { UserDto } from '../../api/admin/types'
import { ApiError } from '../../api/api-error'
import { showError, showSuccess } from '../../ui/message'
import { validateReason } from '../../utils/passwordRules'

interface Props {
  user: UserDto | null
  onClose: () => void
  onChanged: () => void
}

interface FormValues {
  status: 'active' | 'disabled'
  reason: string
}

export default function UserStatusModal({ user, onClose, onChanged }: Props) {
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
      const result = await changeUserStatus(user.id, {
        status: values.status,
        reason: values.reason.trim(),
      })
      if (!result.changed) {
        showSuccess('状态未变化')
      } else {
        const action = result.status === 'disabled' ? '停用' : '启用'
        showSuccess(`${action}成功，已撤销 ${result.revoked_session_count} 个会话`)
      }
      onChanged()
    } catch (error) {
      if (error instanceof ApiError && error.status === 400) {
        setServerError(error.message)
      } else {
        showError('操作失败，结果未确认，请刷新核实')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={Boolean(user)}
      title={user ? `修改状态：${user.username}` : '修改状态'}
      okText="提交"
      cancelText="取消"
      confirmLoading={submitting}
      onOk={() => void submit()}
      onCancel={close}
      destroyOnHidden
    >
      {serverError && (
        <Alert type="error" showIcon title={serverError} style={{ marginBottom: 16 }} />
      )}
      <Form
        form={form}
        layout="vertical"
        preserve={false}
        initialValues={{ status: user?.status ?? 'active', reason: '' }}
      >
        <Form.Item name="status" label="状态">
          <Radio.Group>
            <Radio value="active">启用</Radio>
            <Radio value="disabled">停用</Radio>
          </Radio.Group>
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
