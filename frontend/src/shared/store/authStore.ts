// 全局登录态：token 持久化到 localStorage，用户/角色/权限放在内存。
// 登录与 /auth/me 两处返回结构不同，这里统一归一化为同一份全局状态。

import { create } from 'zustand'

import { getToken, setToken } from '@/shared/api/token'
import type { User } from '@/shared/types'

interface AuthState {
  token: string | null
  user: User | null
  roles: string[]
  permissions: string[]
  /** 是否已尝试从 token 恢复登录态（避免路由守卫重复请求 /auth/me）。 */
  initialized: boolean
  setAuth: (token: string, user: User, roles: string[], permissions: string[]) => void
  setUser: (user: User, roles: string[], permissions: string[]) => void
  markInitialized: () => void
  clear: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token: getToken(),
  user: null,
  roles: [],
  permissions: [],
  initialized: false,
  setAuth: (token, user, roles, permissions) => {
    setToken(token)
    set({ token, user, roles, permissions, initialized: true })
  },
  setUser: (user, roles, permissions) => {
    set({ user, roles, permissions, initialized: true })
  },
  markInitialized: () => set({ initialized: true }),
  clear: () => {
    setToken(null)
    set({ token: null, user: null, roles: [], permissions: [], initialized: true })
  },
}))
