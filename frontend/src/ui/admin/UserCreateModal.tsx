import { Alert, Form, Input, Modal, Select } from 'antd'
import { useState } from 'react'
import { createUser } from '../../api/admin/users'
import type { UserDto } from '../../api/admin/types'
import { ApiError } from '../../api/api-error'
import { showError, showSuccess } from '../../ui/message'
import {
  validateNickname,
  validatePassword,
  validateUsername,
} from '../../utils/passwordRules'

interface Props {
  open: boolean
  onClose: () => void
  onCreated: (user: UserDto) => void
}

interface FormValues {
  username: string
  password: string
  nickname?: string
  role: 'admin' | 'student'
}

export default function UserCreateModal({ open, onClose, onCreated }: Props) {
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
    setSubmitting(true)
    setServerError(null)
    try {
      const user = await createUser({
        username: values.username.trim(),
        password: values.password,
        nickname: (values.nickname ?? '').trim(),
        role: values.role,
      })
      showSuccess('创建成功')
      form.resetFields()
      onCreated(user)
    } catch (error) {
      if (error instanceof ApiError) {
        setServerError(error.message)
      } else {
        showError('创建失败，结果未确认，请刷新核实')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      title="创建用户"
      okText="创建"
      cancelText="取消"
      confirmLoading={submitting}
      onOk={() => void submit()}
      onCancel={close}
      destroyOnHidden
    >
      {serverError && (
        <Alert
          type="error"
          showIcon
          title={serverError}
          style={{ marginBottom: 16 }}
        />
      )}
      <Form
        form={form}
        layout="vertical"
        initialValues={{ role: 'student', nickname: '' }}
        preserve={false}
      >
        <Form.Item
          name="username"
          label="用户名"
          rules={[
            {
              validator: (_, value: string) => {
                const message = validateUsername(value ?? '')
                return message ? Promise.reject(new Error(message)) : Promise.resolve()
              },
            },
          ]}
        >
          <Input maxLength={50} placeholder="3—50 位字母、数字或下划线" />
        </Form.Item>
        <Form.Item
          name="password"
          label="初始密码"
          rules={[
            {
              validator: (_, value: string) => {
                const message = validatePassword(value ?? '')
                return message ? Promise.reject(new Error(message)) : Promise.resolve()
              },
            },
          ]}
        >
          <Input.Password placeholder="10—64 字符，含字母与数字" />
        </Form.Item>
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
          <Input maxLength={50} placeholder="可留空" />
        </Form.Item>
        <Form.Item name="role" label="角色">
          <Select
            options={[
              { value: 'student', label: '学生' },
              { value: 'admin', label: '管理员' },
            ]}
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}
