import { useEffect } from 'react'
import { App as AntdApp, ConfigProvider, Spin } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { RouterProvider } from 'react-router-dom'

import * as authApi from '@/modules/auth/api'
import { useAuthStore } from '@/shared/store/authStore'
import { themeConfig } from '@/styles/theme'
import { router } from './router'

function FullScreenLoading() {
  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Spin size="large" />
    </div>
  )
}

export default function App() {
  const initialized = useAuthStore((s) => s.initialized)

  // 启动时用本地 token 恢复登录态（03 号 issue：登录态恢复）。
  useEffect(() => {
    const state = useAuthStore.getState()
    if (!state.token || state.user) {
      state.markInitialized()
      return
    }
    authApi
      .me()
      .then(({ user, roles, permissions }) => state.setUser(user, roles, permissions))
      .catch(() => state.clear())
  }, [])

  return (
    <ConfigProvider locale={zhCN} theme={themeConfig}>
      <AntdApp>{initialized ? <RouterProvider router={router} /> : <FullScreenLoading />}</AntdApp>
    </ConfigProvider>
  )
}
