// 登录、当前用户、退出登录（1 号 PRD 最小 demo）。

import { request } from '@/shared/api/client'
import type { LoginResponse, MeResponse } from '@/shared/types'

export interface LoginPayload {
  username: string
  password: string
  remember_me: boolean
}

export function login(payload: LoginPayload): Promise<LoginResponse> {
  return request<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function me(): Promise<MeResponse> {
  return request<MeResponse>('/auth/me')
}

export function logout(): Promise<null> {
  return request<null>('/auth/logout', { method: 'POST' })
}
