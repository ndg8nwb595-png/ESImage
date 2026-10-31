import { App, Button, Card, Form, Input, Skeleton } from 'antd'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuthStore } from '@/shared/store/authStore'
import * as api from '../api'

/** 个人中心：查看/修改显示名与邮箱、修改登录密码。 */
export default function ProfilePage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const clear = useAuthStore((s) => s.clear)

  const [loading, setLoading] = useState(true)
  const [savingProfile, setSavingProfile] = useState(false)
  const [savingPwd, setSavingPwd] = useState(false)
  const [form] = Form.useForm()
  const [pwdForm] = Form.useForm()

  useEffect(() => {
    api
      .getProfile()
      .then((p) => {
        form.setFieldsValue(p)
      })
      .catch(() => message.error('加载失败，请重试'))
      .finally(() => setLoading(false))
  }, [form, message])

  const onSaveProfile = async (values: { display_name: string; email: string }) => {
    setSavingProfile(true)
    try {
      const updated = await api.updateProfile({
        display_name: values.display_name,
        email: values.email || null,
      })
      const st = useAuthStore.getState()
      if (st.user) {
        st.setUser({ ...st.user, display_name: updated.display_name }, st.roles, st.permissions)
      }
      message.success('资料已保存')
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败，请重试')
    } finally {
      setSavingProfile(false)
    }
  }

  const onChangePassword = async (values: { old_password: string; new_password: string }) => {
    setSavingPwd(true)
    try {
      await api.changePassword({ old_password: values.old_password, new_password: values.new_password })
      message.success('密码已修改，请重新登录')
      clear()
      navigate('/login', { replace: true })
    } catch (err) {
      message.error(err instanceof Error ? err.message : '修改失败，请重试')
    } finally {
      setSavingPwd(false)
    }
  }

  if (loading) {
    return (
      <div style={{ padding: 24, maxWidth: 640 }}>
        <Skeleton active paragraph={{ rows: 6 }} />
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
      <div style={{ maxWidth: 640, margin: '0 auto' }}>
        <Card title="基本资料" style={{ marginBottom: 16 }}>
          <Form form={form} layout="vertical" onFinish={onSaveProfile}>
            <Form.Item label="用户名" name="username">
              <Input disabled />
            </Form.Item>
            <Form.Item
              label="显示名"
              name="display_name"
              rules={[{ required: true, message: '请输入显示名' }, { max: 30, message: '不能超过 30 个字符' }]}
            >
              <Input maxLength={30} />
            </Form.Item>
            <Form.Item
              label="邮箱（选填）"
              name="email"
              rules={[{ type: 'email', message: '邮箱格式错误' }]}
            >
              <Input maxLength={255} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={savingProfile}>
              保存
            </Button>
          </Form>
        </Card>

        <Card title="修改密码">
          <Form form={pwdForm} layout="vertical" onFinish={onChangePassword}>
            <Form.Item
              label="旧密码"
              name="old_password"
              rules={[{ required: true, message: '请输入旧密码' }]}
            >
              <Input.Password autoComplete="current-password" />
            </Form.Item>
            <Form.Item
              label="新密码"
              name="new_password"
              rules={[
                { required: true, message: '请输入新密码' },
                { min: 8, max: 32, message: '密码长度需为 8~32 位' },
              ]}
            >
              <Input.Password autoComplete="new-password" />
            </Form.Item>
            <Form.Item
              label="确认新密码"
              name="confirm_password"
              dependencies={['new_password']}
              rules={[
                { required: true, message: '请再次输入新密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('new_password') === value) return Promise.resolve()
                    return Promise.reject(new Error('两次输入的密码不一致'))
                  },
                }),
              ]}
            >
              <Input.Password autoComplete="new-password" />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={savingPwd}>
              修改密码
            </Button>
          </Form>
        </Card>
      </div>
    </div>
  )
}
