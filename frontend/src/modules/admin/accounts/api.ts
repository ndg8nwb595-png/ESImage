// 账号与权限接口（6 号 PRD 最小 demo）。

import { request } from '@/shared/api/client'

export interface RoleRef {
  code: string
  name: string
}

export interface UserStats {
  image_count: number
  session_count: number
  token_total: number
  failed_task_count: number
  stats_available: boolean
}

export interface AdminUser {
  user_id: number
  username: string
  display_name: string
  roles: RoleRef[]
  status: string
  stats: UserStats
  last_login_at: string | null
  created_at: string
  updated_at: string
  deleted_at: string | null
}

export interface AdminUserListResponse {
  items: AdminUser[]
  total: number
  page: number
  page_size: number
}

export interface PermissionItem {
  code: string
  name: string
  type: string
  group_name: string | null
  is_super_only: boolean
}

export interface RoleItem {
  code: string
  name: string
  editable: boolean
  permissions: string[]
}

export interface RolesResponse {
  roles: RoleItem[]
  permissions: PermissionItem[]
}

export function listUsers(params: {
  keyword?: string
  role?: string
  status?: string
  page?: number
  page_size?: number
}): Promise<AdminUserListResponse> {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  })
  return request<AdminUserListResponse>(`/admin/users?${qs.toString()}`)
}

export function createUser(payload: {
  username: string
  display_name: string
  password: string
  roles: string[]
  status: string
}): Promise<AdminUser> {
  return request<AdminUser>('/admin/users', { method: 'POST', body: JSON.stringify(payload) })
}

export function updateUser(
  userId: number,
  payload: { display_name?: string; roles?: string[]; status?: string },
): Promise<AdminUser> {
  return request<AdminUser>(`/admin/users/${userId}`, { method: 'PATCH', body: JSON.stringify(payload) })
}

export function resetPassword(userId: number, newPassword: string): Promise<null> {
  return request<null>(`/admin/users/${userId}/reset-password`, {
    method: 'POST',
    body: JSON.stringify({ new_password: newPassword }),
  })
}

export function disableUser(userId: number): Promise<AdminUser> {
  return request<AdminUser>(`/admin/users/${userId}/disable`, { method: 'POST' })
}

export function enableUser(userId: number): Promise<AdminUser> {
  return request<AdminUser>(`/admin/users/${userId}/enable`, { method: 'POST' })
}

export function deleteUser(userId: number): Promise<null> {
  return request<null>(`/admin/users/${userId}`, { method: 'DELETE' })
}

export function restoreUser(userId: number): Promise<AdminUser> {
  return request<AdminUser>(`/admin/users/${userId}/restore`, { method: 'POST' })
}

export function listRoles(): Promise<RolesResponse> {
  return request<RolesResponse>('/admin/roles')
}

export function updateRolePermissions(code: string, permissions: string[]): Promise<null> {
  return request<null>(`/admin/roles/${code}/permissions`, {
    method: 'PUT',
    body: JSON.stringify({ permissions }),
  })
}
