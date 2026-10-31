// 管理后台接口（6/7/8 号 PRD 最小 demo）。

import { request } from '@/shared/api/client'

export interface DashboardSummary {
  user_total: number
  today_image_count: number
  total_image_count: number
  today_token_total: number
}

export interface TokenStatsItem {
  date: string
  user_id: number | null
  username: string | null
  display_name: string | null
  agent_code: string
  agent_name: string
  model_name: string | null
  call_count: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export interface TokenStatsResponse {
  summary: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    call_count: number
  }
  items: TokenStatsItem[]
  total: number
  page: number
  page_size: number
}

export function getDashboardSummary(): Promise<DashboardSummary> {
  return request<DashboardSummary>('/admin/dashboard/summary')
}

export function getTokenStats(params: {
  start_date?: string
  end_date?: string
  user?: string
  agent_codes?: string
  model?: string
  page?: number
}): Promise<TokenStatsResponse> {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  })
  return request<TokenStatsResponse>(`/admin/tokens/stats?${qs.toString()}`)
}
