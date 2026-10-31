// 内容追溯与聊天记录接口（7/8 号 PRD 最小 demo）。

import { request } from '@/shared/api/client'

export interface ContentUser {
  user_id: number
  username: string
  display_name: string
  status: string
  last_generated_at: string | null
  batch_count: number
}

export interface ContentSession {
  session_id: number
  title: string
  status: string
  last_message_at: string | null
  batch_count: number
  latest_batch_at: string | null
  created_at: string
}

export interface ContentBatch {
  batch_id: number
  batch_type: string
  status: string
  product_name: string
  style_text: string | null
  width: number
  height: number
  template_name: string | null
  total_count: number
  completed_count: number
  composition: { main: number; detail: number }
  created_at: string
  finished_at: string | null
}

export interface ContentImage {
  image_id: number
  index_no: number
  attempt_no: number
  image_role: string
  status: string
  width: number | null
  height: number | null
  thumbnail_url: string | null
  archived_at: string | null
  is_history_visible: boolean
  created_at: string
}

export interface ImageDetail {
  image_id: number
  batch_id: number
  batch_type: string | null
  batch_status: string | null
  session_id: number
  session_title: string | null
  user_id: number
  username: string | null
  display_name: string | null
  index_no: number
  attempt_no: number
  image_type: string
  image_role: string
  status: string
  product_name: string | null
  style_text: string | null
  width: number | null
  height: number | null
  template_name: string | null
  prompt: string | null
  negative_prompt: string | null
  model_name: string | null
  latency_ms: number | null
  prompt_tokens: number
  completion_tokens: number
  error_message: string | null
  created_at: string
  file_path: string | null
  is_history_visible: boolean
  archived_at: string | null
  thumbnail_url: string | null
  preview_url: string | null
  download_url: string | null
}

export interface Paged<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export function contentUsers(params: { keyword?: string; page?: number; page_size?: number }): Promise<Paged<ContentUser>> {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => v != null && v !== '' && qs.set(k, String(v)))
  return request(`/admin/content/users?${qs.toString()}`)
}

export function contentSessions(userId: number, page = 1): Promise<Paged<ContentSession>> {
  return request(`/admin/content/users/${userId}/sessions?page=${page}&page_size=20`)
}

export function contentBatches(sessionId: number, page = 1): Promise<Paged<ContentBatch>> {
  return request(`/admin/content/sessions/${sessionId}/batches?page=${page}&page_size=20`)
}

export function contentImages(batchId: number, page = 1): Promise<Paged<ContentImage>> {
  return request(`/admin/content/batches/${batchId}/images?page=${page}&page_size=50`)
}

export function imageDetail(imageId: number): Promise<ImageDetail> {
  return request(`/admin/content/images/${imageId}`)
}

// 聊天记录
export interface ChatSessionItem {
  session_id: number
  user: { user_id: number; username: string; display_name: string } | null
  title: string
  status: string
  message_count: number
  last_message_at: string | null
  token_usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
  batch_count: number
  created_at: string
  updated_at: string
}

export interface ChatMessageItem {
  message_id: number
  role: string
  agent_code: string | null
  agent_name: string | null
  content: string
  content_type: string
  token_in: number
  token_out: number
  status: string
  created_at: string
  agent_runs: {
    run_id: number
    agent_code: string
    agent_name: string
    status: string
    latency_ms: number | null
    prompt_tokens: number
    completion_tokens: number
    model_name: string | null
  }[]
  related_batches: {
    batch_id: number
    batch_type: string
    status: string
    product_name: string
    created_at: string
  }[]
}

export interface ChatSessionDetail {
  session: ChatSessionItem
  messages: ChatMessageItem[]
  has_older: boolean
  has_newer: boolean
  anchor_message_id: number | null
}

export function chatSessions(params: {
  user_keyword?: string
  title_keyword?: string
  status?: string
  page?: number
  page_size?: number
}): Promise<Paged<ChatSessionItem>> {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => v != null && v !== '' && qs.set(k, String(v)))
  return request(`/admin/chat/sessions?${qs.toString()}`)
}

export function chatSessionDetail(sessionId: number, opts?: { before_id?: number; around_id?: number; limit?: number }): Promise<ChatSessionDetail> {
  const qs = new URLSearchParams()
  if (opts) Object.entries(opts).forEach(([k, v]) => v != null && qs.set(k, String(v)))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return request(`/admin/chat/sessions/${sessionId}${suffix}`)
}
