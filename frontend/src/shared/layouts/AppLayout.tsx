import { LogoutOutlined, UserOutlined } from '@ant-design/icons'
import { Avatar, Dropdown, Layout, Space } from 'antd'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'

import * as authApi from '@/modules/auth/api'
import { useAuthStore } from '@/shared/store/authStore'
import { colors } from '@/styles/theme'

interface NavItem {
  path: string
  label: string
}

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, permissions, clear } = useAuthStore()

  const navItems: NavItem[] = []
  if (permissions.includes('user.workspace')) navItems.push({ path: '/workspace', label: '创作工作台' })
  if (permissions.includes('user.history')) navItems.push({ path: '/history', label: '历史作品' })
  if (permissions.includes('user.profile')) navItems.push({ path: '/profile', label: '个人中心' })
  if (permissions.includes('admin.dashboard.view')) navItems.push({ path: '/admin/dashboard', label: '管理后台' })

  const onLogout = async () => {
    try {
      await authApi.logout()
    } catch {
      // 无论接口结果如何都清除本地登录态
    }
    clear()
    navigate('/login', { replace: true })
  }

  const isActive = (path: string) => location.pathname.startsWith(path)

  return (
    <Layout style={{ height: '100%' }}>
      <Layout.Header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: '#fff',
          borderBottom: `1px solid ${colors.border}`,
          paddingInline: 24,
          height: 56,
          lineHeight: '56px',
        }}
      >
        <Space size={32}>
          <Link to="/workspace" style={{ color: colors.primary, fontWeight: 700, fontSize: 18 }}>
            ESImage
          </Link>
          <Space size={8}>
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                style={{
                  color: isActive(item.path) ? colors.primary : colors.foreground,
                  fontWeight: isActive(item.path) ? 600 : 400,
                  padding: '4px 10px',
                  borderRadius: 6,
                  background: isActive(item.path) ? colors.muted : 'transparent',
                }}
              >
                {item.label}
              </Link>
            ))}
          </Space>
        </Space>

        <Dropdown
          menu={{
            items: [
              {
                key: 'logout',
                icon: <LogoutOutlined />,
                label: '退出登录',
                onClick: onLogout,
              },
            ],
          }}
        >
          <Space style={{ cursor: 'pointer' }}>
            <Avatar size="small" icon={<UserOutlined />} style={{ background: colors.primary }} />
            <span>{user?.display_name ?? user?.username}</span>
          </Space>
        </Dropdown>
      </Layout.Header>

      <Layout.Content style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <Outlet />
      </Layout.Content>
    </Layout>
  )
}
