import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuthStore } from '@/shared/store/authStore'

/** 未登录访问受保护页：跳登录页并带回跳地址。 */
export function RequireAuth() {
  const token = useAuthStore((s) => s.token)
  const location = useLocation()
  if (!token) {
    const redirect = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?redirect=${redirect}`} replace />
  }
  return <Outlet />
}

/** 无权限访问：跳 403，不清除登录态（接口文档 §5.2）。 */
export function RequirePermission({ permission, children }: { permission: string; children: ReactNode }) {
  const permissions = useAuthStore((s) => s.permissions)
  if (!permissions.includes(permission)) {
    return <Navigate to="/403" replace />
  }
  return <>{children}</>
}
