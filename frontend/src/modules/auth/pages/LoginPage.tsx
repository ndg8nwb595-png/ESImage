import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Checkbox, Form, Input } from 'antd'
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import * as authApi from '@/modules/auth/api'
import { ApiError } from '@/shared/api/client'
import { useAuthStore } from '@/shared/store/authStore'
import { colors } from '@/styles/theme'
import { defaultLandingPath, parseSafeRedirect } from '@/shared/utils/redirect'

interface FormValues {
  username: string
  password: string
  remember_me: boolean
}

export default function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onFinish = async (values: FormValues) => {
    setLoading(true)
    setError(null)
    try {
      const data = await authApi.login({
        username: values.username,
        password: values.password,
        remember_me: values.remember_me ?? false,
      })
      setAuth(data.token, data.user, data.user.roles, data.user.permissions)
      const target =
        parseSafeRedirect(searchParams.get('redirect')) ?? defaultLandingPath(data.user.roles)
      navigate(target, { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message)
      } else {
        setError('网络异常，请稍后重试')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: colors.background,
      }}
    >
      <Card style={{ width: 400 }} styles={{ body: { padding: 32 } }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div style={{ fontSize: 26, fontWeight: 700, color: colors.primary }}>ESImage</div>
          <div style={{ color: '#6b7280', marginTop: 4 }}>电商主图 / 详情图 AIGC 生成</div>
        </div>

        {error && (
          <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />
        )}

        <Form<FormValues> onFinish={onFinish} size="large" initialValues={{ remember_me: false }}>
          <Form.Item
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
              autoComplete="current-password"
            />
          </Form.Item>
          <Form.Item name="remember_me" valuePropName="checked">
            <Checkbox>记住我（7 天）</Checkbox>
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" block loading={loading}>
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
