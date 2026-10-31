// Agent 配置接口（9 号 §6.5）。

import { request } from '@/shared/api/client'

export interface ModelConfig {
  id: number
  provider: string
  base_url: string
  api_key: string | null
  text_model: string
  image_model: string
  vision_model: string | null
  temperature: number
  timeout_seconds: number
  concurrency: number
  retry_count: number
  max_context_tokens: number | null
  is_active: boolean
  updated_at: string
}

export interface PromptListItem {
  agent_code: string
  name: string
  current_version: number
  is_active: boolean
  updated_at: string
}

export interface PromptDetail {
  agent_code: string
  name: string
  content: string
  current_version: number
  is_active: boolean
  updated_at: string
  versions: { version: number; content: string; created_at: string }[]
}

export const getModelConfig = () => request<ModelConfig | null>('/admin/model-config')
export const saveModelConfig = (payload: Partial<ModelConfig> & { api_key?: string }) =>
  request<ModelConfig>('/admin/model-config', { method: 'PUT', body: JSON.stringify(payload) })
export const listPrompts = () => request<{ items: PromptListItem[] }>('/admin/prompts')
export const getPrompt = (agentCode: string) => request<PromptDetail>(`/admin/prompts/${agentCode}`)
export const savePrompt = (agentCode: string, content: string) =>
  request<{ agent_code: string; current_version: number }>(`/admin/prompts/${agentCode}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
export const activatePromptVersion = (agentCode: string, version: number) =>
  request<{ agent_code: string; current_version: number }>(
    `/admin/prompts/${agentCode}/versions/${version}/activate`,
    { method: 'POST' },
  )
