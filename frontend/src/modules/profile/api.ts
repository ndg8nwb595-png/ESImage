// 个人中心接口（9 号 PRD §5.7）。

import { request } from '@/shared/api/client'

export interface Profile {
  username: string
  display_name: string
  email: string | null
  avatar_url: string | null
}

export function getProfile(): Promise<Profile> {
  return request<Profile>('/profile')
}

export function updateProfile(payload: { display_name: string; email: string | null }): Promise<Profile> {
  return request<Profile>('/profile', { method: 'PATCH', body: JSON.stringify(payload) })
}

export function changePassword(payload: { old_password: string; new_password: string }): Promise<null> {
  return request<null>('/auth/password', { method: 'PUT', body: JSON.stringify(payload) })
}
