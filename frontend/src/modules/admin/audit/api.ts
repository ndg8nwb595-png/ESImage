// 操作日志接口（6 号 PRD 最小 demo，仅超管）。

import { request } from '@/shared/api/client'

export interface AuditLog {
  id: number
  user_id: number | null
  username_snapshot: string | null
  action: string
  target_type: string | null
  target_id: string | null
  result: string
  ip: string | null
  user_agent: string | null
  detail: Record<string, unknown> | null
  created_at: string
}

export interface AuditLogList {
  items: AuditLog[]
  total: number
  page: number
  page_size: number
}

export function listAuditLogs(params: {
  keyword?: string
  action?: string
  result?: string
  created_from?: string
  created_to?: string
  page?: number
  page_size?: number
}): Promise<AuditLogList> {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => v != null && v !== '' && qs.set(k, String(v)))
  return request(`/admin/audit-logs?${qs.toString()}`)
}

export function getAuditLog(id: number): Promise<AuditLog> {
  return request(`/admin/audit-logs/${id}`)
}
