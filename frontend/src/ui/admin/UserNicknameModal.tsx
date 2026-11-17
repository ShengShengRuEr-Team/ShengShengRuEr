import { Alert, Form, Input, Modal } from 'antd'
import { useState } from 'react'
import { updateUserNickname } from '../../api/admin/users'
import type { UserDto } from '../../api/admin/types'
import { ApiError } from '../../api/api-error'
import { showError, showSuccess } from '../../ui/message'
import { validateNickname } from '../../utils/passwordRules'

interface Props {
  user: UserDto | null
  onClose: () => void
  onSaved: (user: UserDto) => void
}

export default function UserNicknameModal({ user, onClose, onSaved }: Props) {
  const [form] = Form.useForm<{ nickname: string }>()
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
      const updated = await updateUserNickname(user.id, values.nickname.trim())
      showSuccess('昵称已保存')
      onSaved(updated)
    } catch (error) {
      if (error instanceof ApiError && error.status === 400) {
        setServerError(error.message)
      } else {
        showError('保存失败，结果未确认，请刷新核实')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={Boolean(user)}
      title={user ? `修改昵称：${user.username}` : '修改昵称'}
      okText="保存"
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
        initialValues={{ nickname: user?.nickname ?? '' }}
      >
        <Form.Item
          name="nickname"
          label="昵称"
          rules={[
            {
              validator: (_, value: string) => {
                const message = validateNickname(value ?? '')
                return message ? Promise.reject(new Error(message)) : Promise.resolve()
              },
            },
          ]}
        >
          <Input maxLength={50} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
