import { Alert, Button, Card, Form, Input, Space, Tag, Typography } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  changeMyPassword,
  fetchMe,
  updateMyNickname,
} from '../../api/admin/users'
import type { UserDto } from '../../api/admin/types'
import { ApiError } from '../../api/api-error'
import { useAuth } from '../../auth/useAuth'
import { ROUTES } from '../../constants/routes'
import {
  ACCOUNT_STATUS_LABELS,
  PERM_SELF_PASSWORD,
  PERM_SELF_UPDATE,
  ROLE_LABELS,
} from '../../generated/adminConstants'
import Can from '../../ui/Can'
import { showError, showSuccess } from '../../ui/message'
import { labelOf } from '../../utils/adminLabels'
import { validateNickname, validatePassword } from '../../utils/passwordRules'

interface PasswordFormValues {
  old_password: string
  new_password: string
}

export default function ProfilePage() {
  const { clearLocalSession } = useAuth()
  const navigate = useNavigate()

  const [me, setMe] = useState<UserDto | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nicknameForm] = Form.useForm<{ nickname: string }>()
  const [passwordForm] = Form.useForm<PasswordFormValues>()
  const [savingNickname, setSavingNickname] = useState(false)
  const [changingPassword, setChangingPassword] = useState(false)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [passwordInfo, setPasswordInfo] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const profile = await fetchMe()
      setMe(profile)
      nicknameForm.setFieldsValue({ nickname: profile.nickname })
    } catch (cause) {
      setMe(null)
      setError(cause instanceof ApiError ? cause.message : '加载个人资料失败')
    } finally {
      setLoading(false)
    }
  }, [nicknameForm])

  useEffect(() => {
    void load()
  }, [load])

  const saveNickname = async () => {
    let values
    try {
      values = await nicknameForm.validateFields()
    } catch {
      return
    }
    setSavingNickname(true)
    try {
      const updated = await updateMyNickname(values.nickname.trim())
      setMe(updated)
      showSuccess('昵称已保存')
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 400) {
        showError(cause.message)
      } else {
        showError('保存失败，结果未确认，请刷新核实')
      }
    } finally {
      setSavingNickname(false)
    }
  }

  const submitPassword = async () => {
    let values
    try {
      values = await passwordForm.validateFields()
    } catch {
      return
    }
    setChangingPassword(true)
    setPasswordError(null)
    setPasswordInfo(null)
    try {
      await changeMyPassword({
        old_password: values.old_password,
        new_password: values.new_password,
      })
      showSuccess('密码已修改，请重新登录')
      clearLocalSession()
      navigate(ROUTES.LOGIN, { replace: true })
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 400) {
        setPasswordError(cause.message)
        // 失败只清新密码字段，保留旧密码方便重试。
        passwordForm.setFieldValue('new_password', '')
      } else {
        setPasswordInfo('结果未确认，请刷新核实；不要重复提交')
      }
    } finally {
      setChangingPassword(false)
    }
  }

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Card title="个人中心" loading={loading}>
        {error && (
          <Space orientation="vertical" size="small" style={{ width: '100%' }}>
            <Alert type="error" showIcon title={error} />
            <Button onClick={() => void load()}>重试</Button>
          </Space>
        )}
        {me && !error && (
          <Space size="large" wrap>
            <Typography.Text>用户名：{me.username}</Typography.Text>
            <Typography.Text>
              角色：{me.role ? labelOf(ROLE_LABELS, me.role) : '未知'}
            </Typography.Text>
            <Typography.Text>
              状态：
              <Tag color={me.status === 'active' ? 'green' : 'red'}>
                {labelOf(ACCOUNT_STATUS_LABELS, me.status)}
              </Tag>
            </Typography.Text>
          </Space>
        )}
      </Card>

      <Card title="修改昵称">
        <Can code={PERM_SELF_UPDATE} fallback={<Typography.Text>没有修改昵称的权限</Typography.Text>}>
          <Form form={nicknameForm} layout="inline" preserve={false}>
            <Form.Item
              name="nickname"
              label="昵称"
              rules={[
                {
                  validator: (_, value: string) => {
                    const message = validateNickname(value ?? '')
                    return message
                      ? Promise.reject(new Error(message))
                      : Promise.resolve()
                  },
                },
              ]}
            >
              <Input maxLength={50} style={{ width: 240 }} />
            </Form.Item>
            <Button
              type="primary"
              loading={savingNickname}
              onClick={() => void saveNickname()}
            >
              保存
            </Button>
          </Form>
        </Can>
      </Card>

      <Card title="修改密码">
        <Can code={PERM_SELF_PASSWORD} fallback={<Typography.Text>没有修改密码的权限</Typography.Text>}>
          {passwordError && (
            <Alert
              type="error"
              showIcon
              title={passwordError}
              style={{ marginBottom: 16 }}
            />
          )}
          {passwordInfo && (
            <Alert
              type="warning"
              showIcon
              title={passwordInfo}
              style={{ marginBottom: 16 }}
            />
          )}
          <Form form={passwordForm} layout="vertical" preserve={false}>
            <Form.Item
              name="old_password"
              label="旧密码"
              rules={[{ required: true, message: '请输入旧密码' }]}
            >
              <Input.Password autoComplete="current-password" />
            </Form.Item>
            <Form.Item
              name="new_password"
              label="新密码"
              rules={[
                {
                  validator: (_, value: string) => {
                    const message = validatePassword(value ?? '')
                    return message
                      ? Promise.reject(new Error(message))
                      : Promise.resolve()
                  },
                },
              ]}
            >
              <Input.Password autoComplete="new-password" />
            </Form.Item>
            <Button
              type="primary"
              loading={changingPassword}
              onClick={() => void submitPassword()}
            >
              修改密码
            </Button>
          </Form>
        </Can>
      </Card>
    </Space>
  )
}
